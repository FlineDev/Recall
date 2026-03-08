#!/usr/bin/env python3
"""Condense large recall transcripts by keeping the tail verbatim and summarizing older context.

Design goal: Output targets 15-20K tokens (~10% of Claude Code's 200K context window).
- If transcript ≤ 20K tokens: keep as-is, no API call needed.
- If > 20K: keep ~15K tokens of recent exchanges verbatim, summarize older context
  with a single claude -p --model sonnet call (~30-40s).

Two subcommands:
  split   — Check if condensation needed, split into older + tail + prompt files
  combine — Reassemble from summary + tail back into the transcript

Usage:
  python3 condense-tail.py split <input.md> <session-id>
  python3 condense-tail.py combine <input.md> <session-id>
"""

import json
import os
import re
import sys

# ── Constants ─────────────────────────────────────────────────────────────
THRESHOLD_TOKENS = 20_000     # Only condense if above this
TAIL_TARGET_TOKENS = 15_000   # Keep ~15K tokens of recent exchanges verbatim
OLDER_CAP_TOKENS = 85_000     # Max tokens of older context to send to Sonnet
# Note: no fixed word count target — the prompt guides the model to choose
# an appropriate length based on session complexity.
# ──────────────────────────────────────────────────────────────────────────

USER_HEADER_RE = re.compile(r"^> \[!NOTE\]$")


def estimate_tokens(text):
   """Estimate token count from text using byte count / 3.0.

   Calibrated against Xenova/claude-tokenizer on 50+ real sessions.
   Old bytes/2.2 overcounted by ~37%. New bytes/3.0: avg error +0.1%.
   """
   byte_count = len(text.encode("utf-8")) if isinstance(text, str) else len(text)
   return int(byte_count / 3.0)


def parse_token_estimate(text):
   """Extract the 'Estimated tokens: ~N,NNN' value from the STATISTICS section."""
   for line in text.split("\n"):
      if "**Estimated tokens:**" in line and "~" in line:
         num_str = line.split("~")[1].replace(",", "").strip()
         return int(num_str)
   return estimate_tokens(text)


def find_conversation_start(lines):
   """Find the line index where '## Conversation' starts.

   Returns the index of the first line AFTER the header, blank line, and --- separator.
   """
   for i, line in enumerate(lines):
      if line.strip() == "## Conversation":
         # Skip the header, blank lines, and --- separator
         j = i + 1
         while j < len(lines) and lines[j].strip() in ("", "---"):
            j += 1
         return j
   return 0


def parse_exchanges(lines):
   """Parse conversation lines into exchanges.

   An exchange = one USER entry + all following non-USER entries (TOOLS, ASSISTANT,
   compaction markers, etc.) until the next USER entry.

   Returns a list of dicts: [{start_idx, end_idx, tokens, lines}]
   where start_idx/end_idx are indices into the input lines list.
   """
   exchanges = []
   current_start = None

   for i, line in enumerate(lines):
      if USER_HEADER_RE.match(line.strip()):
         if current_start is not None:
            # Close previous exchange
            exchange_text = "".join(lines[current_start:i])
            exchanges.append({
               "start_idx": current_start,
               "end_idx": i,
               "tokens": estimate_tokens(exchange_text),
               "lines": lines[current_start:i],
            })
         current_start = i

   # Close the last exchange
   if current_start is not None:
      exchange_text = "".join(lines[current_start:])
      exchanges.append({
         "start_idx": current_start,
         "end_idx": len(lines),
         "tokens": estimate_tokens(exchange_text),
         "lines": lines[current_start:],
      })

   return exchanges


def split_at_exchange_boundary(conversation_lines, target_tail_tokens):
   """Split conversation lines into (older_lines, tail_lines) at exchange boundaries.

   Reads backward from the end, accumulating exchanges until target_tail_tokens
   is reached. The split always happens at an exchange boundary (before a USER line).

   Returns (older_lines, tail_lines) where tail_lines is ~target_tail_tokens.
   If all exchanges fit within target, returns ([], all_lines).
   """
   exchanges = parse_exchanges(conversation_lines)

   if not exchanges:
      return [], conversation_lines

   # Accumulate from the end
   tail_tokens = 0
   split_exchange_idx = len(exchanges)  # Start from "include nothing"

   for i in range(len(exchanges) - 1, -1, -1):
      if tail_tokens + exchanges[i]["tokens"] > target_tail_tokens and tail_tokens > 0:
         # Adding this exchange would exceed target and we already have some content
         break
      tail_tokens += exchanges[i]["tokens"]
      split_exchange_idx = i

   if split_exchange_idx == 0:
      # Everything fits in the tail
      return [], conversation_lines

   # Split at the exchange boundary
   split_line_idx = exchanges[split_exchange_idx]["start_idx"]
   older_lines = conversation_lines[:split_line_idx]
   tail_lines = conversation_lines[split_line_idx:]

   return older_lines, tail_lines


def build_sonnet_prompt():
   """Build the prompt for the single Sonnet summarization call."""
   return """Summarize this older portion of a Claude Code conversation transcript. \
The recent conversation is preserved verbatim elsewhere — focus only on the earlier context here.

Your summary will be injected into a future Claude session to restore lost context after \
compaction. Write for an AI reader who needs to continue the work seamlessly.

PRIORITIES (in order):
1. User's intentions and goals — the "why" behind each request
2. Decisions and their rationale — especially alternatives that were considered and rejected
3. File paths modified, created, or deleted — exact paths matter
4. Problems encountered and solutions — especially bugs and their root causes
5. Architectural patterns established — naming conventions, key abstractions, data flow
6. User preferences and constraints stated during the conversation
7. Current state — what's done, what's in progress, what's blocked

SKIP OR MINIMIZE:
- File contents (just note path + purpose)
- Tool output details (just note outcomes)
- Reads that didn't lead to action

FORMAT: Chronological narrative with bold paths and bullet lists. Start with a one-line \
session overview. End with precise state description.

LENGTH: Be thorough but not verbose. A good summary captures every important decision and \
file change without reproducing conversations verbatim. Think of it as detailed meeting \
notes — nothing critical missing, nothing unnecessary included.

Summarize:"""


def write_stats(prefix, stats):
   """Write stats JSON to /tmp/recall-stats-<prefix>.json."""
   stats_path = f"/tmp/recall-stats-{prefix}.json"
   with open(stats_path, "w") as f:
      json.dump(stats, f, indent=2)
   return stats_path


def cmd_split(input_path, session_id):
   """Check if condensation is needed and split into files.

   Exit codes:
     0 — condensation needed, files written
     2 — no condensation needed (≤ 20K tokens)

   Always writes /tmp/recall-stats-<prefix>.json with stats.
   """
   prefix = session_id[:8]

   with open(input_path) as f:
      text = f.read()

   tokens = parse_token_estimate(text)
   print(f"Transcript tokens: {tokens:,}", file=sys.stderr)

   # Count total exchanges for stats (even when not condensing)
   all_lines = text.split("\n")
   all_lines_nl = [line + "\n" for line in all_lines]
   if text and not text.endswith("\n"):
      all_lines_nl[-1] = all_lines_nl[-1].rstrip("\n")
   conv_start = find_conversation_start(all_lines_nl)
   total_exchanges = len(parse_exchanges(all_lines_nl[conv_start:]))

   if tokens <= THRESHOLD_TOKENS:
      print(f"Under {THRESHOLD_TOKENS:,} tokens — no condensation needed.", file=sys.stderr)
      write_stats(prefix, {
         "condensed": False,
         "original_tokens": tokens,
         "final_tokens": tokens,
         "total_exchanges": total_exchanges,
         "tail_exchanges": total_exchanges,
         "verbatim_pct": 100,
         "summarized_pct": 0,
         "dropped_pct": 0,
      })
      return 2

   lines = all_lines_nl
   conversation_lines = lines[conv_start:]

   older_lines, tail_lines = split_at_exchange_boundary(
      conversation_lines, TAIL_TARGET_TOKENS
   )

   if not older_lines:
      print("All exchanges fit in tail — no condensation needed.", file=sys.stderr)
      write_stats(prefix, {
         "condensed": False,
         "original_tokens": tokens,
         "final_tokens": tokens,
         "total_exchanges": total_exchanges,
         "tail_exchanges": total_exchanges,
         "verbatim_pct": 100,
         "summarized_pct": 0,
         "dropped_pct": 0,
      })
      return 2

   older_text = "".join(older_lines)
   tail_text = "".join(tail_lines)
   older_tokens = estimate_tokens(older_text)
   tail_tokens = estimate_tokens(tail_text)
   tail_exchanges = len(parse_exchanges(tail_lines))
   older_exchanges_list = parse_exchanges(older_lines)
   older_exchange_count = len(older_exchanges_list)
   dropped_tokens = 0

   # Cap older context at OLDER_CAP_TOKENS
   if older_tokens > OLDER_CAP_TOKENS:
      uncapped_older_tokens = older_tokens
      capped_tokens = 0
      cap_idx = len(older_exchanges_list)
      for i in range(len(older_exchanges_list) - 1, -1, -1):
         if capped_tokens + older_exchanges_list[i]["tokens"] > OLDER_CAP_TOKENS:
            break
         capped_tokens += older_exchanges_list[i]["tokens"]
         cap_idx = i
      if cap_idx < len(older_exchanges_list):
         cap_line = older_exchanges_list[cap_idx]["start_idx"]
         older_text = "".join(older_lines[cap_line:])
         older_tokens = estimate_tokens(older_text)
         dropped_tokens = uncapped_older_tokens - older_tokens
         older_exchange_count = len(older_exchanges_list) - cap_idx

   # Calculate percentages based on original token count
   verbatim_pct = round(tail_tokens / tokens * 100)
   summarized_pct = round(older_tokens / tokens * 100)
   dropped_pct = round(dropped_tokens / tokens * 100)

   print(
      f"Split: {older_tokens:,} tokens older context + {tail_tokens:,} tokens verbatim tail",
      file=sys.stderr,
   )

   # Write output files
   older_path = f"/tmp/recall-older-{prefix}.md"
   tail_path = f"/tmp/recall-tail-{prefix}.md"
   prompt_path = f"/tmp/recall-prompt-{prefix}.txt"

   with open(older_path, "w") as f:
      f.write(older_text)
   with open(tail_path, "w") as f:
      f.write(tail_text)
   with open(prompt_path, "w") as f:
      f.write(build_sonnet_prompt())

   write_stats(prefix, {
      "condensed": True,
      "original_tokens": tokens,
      "tail_tokens": tail_tokens,
      "older_tokens": older_tokens,
      "dropped_tokens": dropped_tokens,
      "total_exchanges": total_exchanges,
      "tail_exchanges": tail_exchanges,
      "older_exchanges": older_exchange_count,
      "verbatim_pct": verbatim_pct,
      "summarized_pct": summarized_pct,
      "dropped_pct": dropped_pct,
   })

   print(f"Files written: {older_path}, {tail_path}, {prompt_path}", file=sys.stderr)
   return 0


def cmd_combine(input_path, session_id):
   """Combine summary + tail back into the transcript file."""
   prefix = session_id[:8]
   summary_path = f"/tmp/recall-summary-{prefix}.md"
   tail_path = f"/tmp/recall-tail-{prefix}.md"

   if not os.path.exists(summary_path):
      print(f"Summary file not found: {summary_path}", file=sys.stderr)
      return 1
   if not os.path.exists(tail_path):
      print(f"Tail file not found: {tail_path}", file=sys.stderr)
      return 1

   # Read the original file for its header
   with open(input_path) as f:
      original = f.read()

   lines = original.split("\n")
   lines = [line + "\n" for line in lines]
   if original and not original.endswith("\n"):
      lines[-1] = lines[-1].rstrip("\n")

   conv_start = find_conversation_start(lines)
   header_text = "".join(lines[:conv_start])

   # Read summary and tail
   with open(summary_path) as f:
      summary_text = f.read().strip()
   with open(tail_path) as f:
      tail_text = f.read()

   # Build combined output
   output = header_text
   output += "## Summarized Older Context\n\n"
   output += summary_text + "\n\n"
   output += "## Recent Conversation (Verbatim)\n\n"
   output += tail_text

   # Update token estimate
   new_tokens = estimate_tokens(output)
   updated_lines = []
   for line in output.split("\n"):
      if "**Estimated tokens:**" in line and "~" in line:
         updated_lines.append(f"- **Estimated tokens:** ~{new_tokens:,}")
      else:
         updated_lines.append(line)
   output = "\n".join(updated_lines)

   with open(input_path, "w") as f:
      f.write(output)

   # Update stats with final token count
   stats_path = f"/tmp/recall-stats-{prefix}.json"
   if os.path.exists(stats_path):
      with open(stats_path) as f:
         stats = json.load(f)
      stats["final_tokens"] = new_tokens
      with open(stats_path, "w") as f:
         json.dump(stats, f, indent=2)

   print(f"Combined output: ~{new_tokens:,} tokens", file=sys.stderr)

   # Clean up temp files (but keep stats — pre-compact.sh needs it)
   for path in [summary_path, tail_path,
                f"/tmp/recall-older-{prefix}.md",
                f"/tmp/recall-prompt-{prefix}.txt"]:
      if os.path.exists(path):
         os.remove(path)

   return 0


def main():
   if len(sys.argv) < 3:
      print(
         "Usage:\n"
         "  python3 condense-tail.py split <input.md> <session-id>\n"
         "  python3 condense-tail.py combine <input.md> <session-id>",
         file=sys.stderr,
      )
      sys.exit(1)

   command = sys.argv[1]
   input_path = sys.argv[2]
   session_id = sys.argv[3] if len(sys.argv) > 3 else "unknown"

   if command == "split":
      exit_code = cmd_split(input_path, session_id)
      sys.exit(exit_code)
   elif command == "combine":
      exit_code = cmd_combine(input_path, session_id)
      sys.exit(exit_code)
   else:
      print(f"Unknown command: {command}", file=sys.stderr)
      sys.exit(1)


if __name__ == "__main__":
   main()
