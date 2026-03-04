#!/usr/bin/env python3
"""Apply summarized messages back into a recall .md file.

Reads .md files from an entries directory (each with YAML frontmatter containing
start_line/end_line), replaces the original content in the transcript with the
summarized version. Processes in reverse order (last entry first) to preserve
line numbers.

Usage: python3 apply-summaries.py <transcript.md> [entries-dir]
"""

import os
import sys


def estimate_tokens(text):
   """Estimate token count from text using byte count / 2.2.

   Calibrated from empirical data: ~2.35 bytes/token for technical markdown + code.
   Using 2.2 to conservatively overestimate by ~7%.
   """
   byte_count = len(text.encode("utf-8")) if isinstance(text, str) else len(text)
   return int(byte_count / 2.2)


def parse_entry_file(filepath):
   """Parse a .md file with YAML frontmatter. Returns (metadata, content)."""
   with open(filepath) as f:
      text = f.read()

   # Split on YAML frontmatter delimiters
   if not text.startswith("---\n"):
      return None, text

   try:
      end_idx = text.index("\n---\n", 4)
   except ValueError:
      return None, text
   frontmatter = text[4:end_idx]
   content = text[end_idx + 5:].strip()

   metadata = {}
   for line in frontmatter.split("\n"):
      if ": " in line:
         key, val = line.split(": ", 1)
         key = key.strip()
         val = val.strip()
         if key in ("id", "start_line", "end_line", "tokens", "target_words"):
            metadata[key] = int(val)
         else:
            metadata[key] = val

   return metadata, content


def main():
   if len(sys.argv) < 2:
      print(
         "Usage: python3 apply-summaries.py <transcript.md> [entries-dir]",
         file=sys.stderr,
      )
      sys.exit(1)

   md_path = sys.argv[1]
   entries_dir = sys.argv[2] if len(sys.argv) > 2 else "/tmp/recall-entries"

   with open(md_path) as f:
      lines = f.readlines()

   # Read all entry files
   entries = []
   for filename in sorted(os.listdir(entries_dir)):
      if not filename.endswith(".md"):
         continue
      filepath = os.path.join(entries_dir, filename)
      metadata, content = parse_entry_file(filepath)
      if metadata and "start_line" in metadata:
         entries.append((metadata, content))

   if not entries:
      print("No entry files found.", file=sys.stderr)
      return

   # Sort by start_line DESCENDING — replace from bottom to top
   entries.sort(key=lambda e: e[0]["start_line"], reverse=True)

   for metadata, summary in entries:
      start = metadata["start_line"] - 1  # 0-indexed
      end = metadata["end_line"]  # exclusive

      # Collect all entry headers from the range (bot messages may span TOOLS + ASSISTANT)
      headers = []
      for line_idx in range(start, end):
         stripped = lines[line_idx].rstrip("\n")
         if stripped.startswith("--- ") and stripped.endswith(" ---"):
            headers.append(stripped)
      if not headers:
         headers = [lines[start].rstrip("\n")]

      # Build replacement: all headers + [Summarized] summary + blank line
      replacement = "\n".join(headers) + f"\n[Summarized] {summary}\n\n"
      lines[start:end] = [replacement]

   # Update token estimate in STATISTICS section
   full_text = "".join(lines)
   new_tokens = estimate_tokens(full_text)

   updated_lines = []
   for line in full_text.split("\n"):
      if line.startswith("Estimated tokens: ~"):
         updated_lines.append(f"Estimated tokens: ~{new_tokens:,}")
      else:
         updated_lines.append(line)

   # Remove NEEDS SUMMARIZATION section if under 25K
   final_text = "\n".join(updated_lines)
   if new_tokens <= 25000:
      needs_idx = final_text.find("\n=== NEEDS SUMMARIZATION ===")
      if needs_idx >= 0:
         final_text = final_text[:needs_idx] + "\n"

   with open(md_path, "w") as f:
      f.write(final_text)

   print(
      f"Applied {len(entries)} summaries. New token estimate: ~{new_tokens:,}",
      file=sys.stderr,
   )


if __name__ == "__main__":
   main()
