#!/usr/bin/env python3
"""Extract messages that need summarization from a recall .md file.

Terminology:
- Entry: A single block in the transcript (one --- USER ---, --- TOOLS ---, or --- ASSISTANT --- section)
- Message: Either a "user message" (exactly 1 USER entry) or a "bot message" (all consecutive
  TOOLS/ASSISTANT entries following a user message, until the next USER entry)
- An exchange = 1 user message + 1 bot message = 2 messages

Uses an iterative partitioning algorithm:
1. Freeze the last user message and its bot response (the last exchange)
2. Calculate token budget (15K - frozen tokens)
3. Iteratively freeze below-average messages until only large ones remain
4. Extract the remaining candidates into individual .md files for summarization

Usage: python3 extract-longest.py <input.md>
Output: Creates /tmp/recall-entries/ with one .md file per message to summarize.
        Prints the directory path to stdout.
"""

import os
import re
import shutil
import sys

# ── Tunable constants ──────────────────────────────────────────────────────
TOKEN_BUDGET = 15_000      # Target token count (lower than 25K to account for summarization overshoot)
MIN_MESSAGE_TOKENS = 200   # Don't summarize messages shorter than this
MAX_SUMMARIZE = 50         # Maximum number of messages to extract for summarization
FROZEN_TAIL_MAX = 3_000    # If the frozen tail bot message exceeds this, summarize it too
FROZEN_TAIL_TARGET = 1_500 # Target token count for an oversized frozen tail bot message
# ───────────────────────────────────────────────────────────────────────────


def parse_entries(filepath):
   """Parse the .md file into a list of entries with line ranges and token counts.

   Reads token counts from the header lines (e.g., '--- USER #1 [...] (123 tokens) ---').
   Falls back to word-count estimation if no token count in header.
   """
   with open(filepath) as f:
      lines = f.readlines()

   entries = []
   current_type = None
   current_start = None
   current_tokens = None
   header_section = True

   # Patterns to extract token counts from headers
   user_pat = re.compile(r"^--- USER #\d+ \[.*?\] \((\d+) tokens\) ---$")
   asst_pat = re.compile(r"^--- ASSISTANT \(\d+ words / (\d+) tokens\) ---$")
   tools_pat = re.compile(r"^--- TOOLS \(\d+ calls? / (\d+) tokens\) ---$")
   compact_pat = re.compile(r"^\[=== (?:MICRO)?COMPACTION")
   summarize_pat = re.compile(r"^=== NEEDS SUMMARIZATION ===$")

   def detect_entry(stripped):
      """Returns (type, tokens_from_header) or None."""
      m = user_pat.match(stripped)
      if m:
         return "USER", int(m.group(1))
      m = asst_pat.match(stripped)
      if m:
         return "ASSISTANT", int(m.group(1))
      m = tools_pat.match(stripped)
      if m:
         return "TOOLS", int(m.group(1))
      if compact_pat.match(stripped):
         return "COMPACTION", 0
      if summarize_pat.match(stripped):
         return "SUMMARIZATION_SECTION", 0
      # Legacy format without token counts
      if stripped.startswith("--- USER #"):
         return "USER", None
      if stripped.startswith("--- ASSISTANT ("):
         return "ASSISTANT", None
      if stripped.startswith("--- TOOLS ("):
         return "TOOLS", None
      return None

   for i, line in enumerate(lines):
      stripped = line.rstrip("\n")

      if header_section:
         if stripped == "=== CONVERSATION ===":
            header_section = False
         continue

      result = detect_entry(stripped)

      if result:
         entry_type, header_tokens = result

         # Save previous entry
         if current_type and current_type not in ("COMPACTION", "SUMMARIZATION_SECTION"):
            if current_tokens is None:
               content = "".join(lines[current_start:i]).strip()
               current_tokens = int(len(content.encode("utf-8")) / 2.2)
            entries.append({
               "type": current_type,
               "start_line": current_start + 1,  # 1-indexed
               "end_line": i,  # exclusive
               "tokens": current_tokens,
            })

         if entry_type == "SUMMARIZATION_SECTION":
            break

         current_type = entry_type
         current_start = i
         current_tokens = header_tokens

   # Last entry
   if current_type and current_type not in ("COMPACTION", "SUMMARIZATION_SECTION"):
      if current_tokens is None:
         content = "".join(lines[current_start:]).strip()
         current_tokens = int(len(content.encode("utf-8")) / 2.2)
      entries.append({
         "type": current_type,
         "start_line": current_start + 1,
         "end_line": len(lines),
         "tokens": current_tokens,
      })

   return entries, lines


def group_into_messages(entries):
   """Group entries into messages.

   A "user message" = exactly 1 USER entry.
   A "bot message" = all consecutive non-USER entries (TOOLS, ASSISTANT) following a USER entry.

   Returns list of messages, each a dict with:
     - kind: "user" or "bot"
     - entries: list of entries in this message
     - start_line: first line (1-indexed)
     - end_line: last line (exclusive)
     - tokens: total tokens across all entries
   """
   messages = []
   i = 0

   while i < len(entries):
      entry = entries[i]

      if entry["type"] == "USER":
         # User message: exactly 1 entry
         messages.append({
            "kind": "user",
            "entries": [entry],
            "start_line": entry["start_line"],
            "end_line": entry["end_line"],
            "tokens": entry["tokens"],
         })
         i += 1

         # Bot message: all following non-USER entries
         bot_entries = []
         while i < len(entries) and entries[i]["type"] != "USER":
            bot_entries.append(entries[i])
            i += 1

         if bot_entries:
            messages.append({
               "kind": "bot",
               "entries": bot_entries,
               "start_line": bot_entries[0]["start_line"],
               "end_line": bot_entries[-1]["end_line"],
               "tokens": sum(e["tokens"] for e in bot_entries),
            })
      else:
         # Orphan non-USER entry (shouldn't happen normally)
         messages.append({
            "kind": "bot",
            "entries": [entry],
            "start_line": entry["start_line"],
            "end_line": entry["end_line"],
            "tokens": entry["tokens"],
         })
         i += 1

   return messages


def select_messages_to_summarize(messages):
   """Iterative partitioning algorithm to select messages for summarization.

   1. Freeze the last exchange (last user message + its bot response)
   2. Calculate remaining token budget
   3. Iteratively: compute average tokens per message, freeze all at/below average
   4. Stop when both: all remaining ≥ MIN_MESSAGE_TOKENS and count ≤ MAX_SUMMARIZE
   5. Return the messages to summarize and the remaining budget for target_words
   """
   total = len(messages)

   # Step 1: Freeze the last exchange (last user message + its bot response).
   # Find the last user message and freeze everything from there onward.
   last_user_idx = None
   for i in range(total - 1, -1, -1):
      if messages[i]["kind"] == "user":
         last_user_idx = i
         break

   if last_user_idx is not None:
      frozen_tail = messages[last_user_idx:]
      candidates = list(messages[:last_user_idx])
   else:
      frozen_tail = []
      candidates = list(messages)

   # Check if the frozen tail has an oversized bot message (> FROZEN_TAIL_MAX tokens).
   # If so, include it in the summarization candidates with a fixed target.
   oversized_tail_msg = None
   for m in frozen_tail:
      if m["kind"] == "bot" and m["tokens"] > FROZEN_TAIL_MAX:
         oversized_tail_msg = m
         break

   if oversized_tail_msg:
      # Move the oversized bot message from frozen tail to candidates
      frozen_tail = [m for m in frozen_tail if m is not oversized_tail_msg]
      candidates.append(oversized_tail_msg)
      # tokens → words for summarizer guidance
      # tokens = bytes / 2.2, avg English word ≈ 5.5 bytes → 1 word ≈ 2.5 tokens
      oversized_tail_msg["_force_target_words"] = max(20, round(FROZEN_TAIL_TARGET / 2.5))

   frozen_tokens = sum(m["tokens"] for m in frozen_tail)

   # Step 2: Budget for everything before the frozen tail
   budget = TOKEN_BUDGET - frozen_tokens

   if not candidates:
      return [], 0

   # Step 3: Iterative partitioning
   frozen_set = set()  # indices into candidates that are frozen

   while True:
      active = [
         (i, m) for i, m in enumerate(candidates) if i not in frozen_set
      ]

      if not active:
         break

      avg = budget / len(active)

      # Freeze messages at or below average
      newly_frozen = []
      for i, m in active:
         if m["tokens"] <= avg:
            newly_frozen.append((i, m))

      if not newly_frozen:
         # Convergence: all remaining are above average.
         # Also freeze messages below MIN_MESSAGE_TOKENS (not worth summarizing).
         for i, m in active:
            if m["tokens"] < MIN_MESSAGE_TOKENS:
               frozen_set.add(i)
               budget -= m["tokens"]
         break

      for i, m in newly_frozen:
         frozen_set.add(i)
         budget -= m["tokens"]

      # Check stopping conditions
      remaining = [(i, m) for i, m in enumerate(candidates) if i not in frozen_set]
      if not remaining:
         break

      min_tokens = min(m["tokens"] for _, m in remaining)
      if min_tokens >= MIN_MESSAGE_TOKENS and len(remaining) <= MAX_SUMMARIZE:
         break

   # Collect final candidates (in original order)
   to_summarize = [
      candidates[i] for i in sorted(
         i for i in range(len(candidates)) if i not in frozen_set
      )
   ]

   # Final cap: take the largest if over MAX_SUMMARIZE
   if len(to_summarize) > MAX_SUMMARIZE:
      to_summarize.sort(key=lambda m: m["tokens"], reverse=True)
      to_summarize = to_summarize[:MAX_SUMMARIZE]
      to_summarize.sort(key=lambda m: m["start_line"])

   # Calculate remaining budget for extracted messages (used for target_words)
   remaining_budget = max(budget, 0)

   return to_summarize, remaining_budget


def main():
   if len(sys.argv) < 2:
      print(
         "Usage: python3 extract-longest.py <input.md> [output-dir]",
         file=sys.stderr,
      )
      sys.exit(1)

   filepath = sys.argv[1]
   custom_out_dir = sys.argv[2] if len(sys.argv) > 2 else None
   entries, lines = parse_entries(filepath)
   messages = group_into_messages(entries)

   to_summarize, remaining_budget = select_messages_to_summarize(messages)

   if not to_summarize:
      print("Nothing to summarize.", file=sys.stderr)
      print("/tmp/recall-entries")
      return

   # Calculate target_words for each message (proportional to its size)
   total_extracted_tokens = sum(m["tokens"] for m in to_summarize)
   for m in to_summarize:
      if "_force_target_words" in m:
         # Oversized frozen-tail message: use fixed target
         m["target_words"] = m["_force_target_words"]
      elif total_extracted_tokens > 0 and remaining_budget > 0:
         target_tokens = m["tokens"] * (remaining_budget / total_extracted_tokens)
         # tokens → words for summarizer guidance
         # tokens = bytes / 2.2, avg English word ≈ 5.5 bytes → 1 word ≈ 2.5 tokens
         m["target_words"] = max(20, round(target_tokens / 2.5))
      else:
         m["target_words"] = 20

   # Create output directory
   out_dir = custom_out_dir or "/tmp/recall-entries"
   if os.path.exists(out_dir):
      shutil.rmtree(out_dir)
   os.makedirs(out_dir)

   # Write individual files
   for idx, msg in enumerate(to_summarize):
      filename = f"{idx:03d}.md"
      filepath_out = os.path.join(out_dir, filename)

      # Read actual content from the source file
      start_idx = msg["start_line"] - 1  # 0-indexed
      end_idx = msg["end_line"]
      content = "".join(lines[start_idx:end_idx]).strip()

      frontmatter = (
         f"---\n"
         f"id: {idx}\n"
         f"start_line: {msg['start_line']}\n"
         f"end_line: {msg['end_line']}\n"
         f"tokens: {msg['tokens']}\n"
         f"kind: {msg['kind']}\n"
         f"target_words: {msg['target_words']}\n"
         f"---\n\n"
      )

      with open(filepath_out, "w") as f:
         f.write(frontmatter + content + "\n")

   total_tokens = sum(m["tokens"] for m in to_summarize)
   user_msgs = sum(1 for m in to_summarize if m["kind"] == "user")
   bot_msgs = sum(1 for m in to_summarize if m["kind"] == "bot")
   frozen_count = len(messages) - len(to_summarize)
   print(
      f"Extracted {len(to_summarize)} messages ({user_msgs} user + {bot_msgs} bot, "
      f"{total_tokens:,} tokens) from {len(messages)} total ({frozen_count} frozen) "
      f"into {out_dir}/",
      file=sys.stderr,
   )
   print(
      f"Remaining budget for summaries: {remaining_budget:,} tokens",
      file=sys.stderr,
   )
   print(out_dir)


if __name__ == "__main__":
   main()
