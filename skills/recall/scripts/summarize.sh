#!/bin/bash
# summarize.sh — Parallel summarization of large recall transcripts using claude -p.
# Replaces the Haiku subagent approach with direct CLI calls.
#
# Usage: summarize.sh <transcript.md> <session-id>
#
# Steps:
# 1. Run extract-longest.py to identify messages needing summarization
# 2. Launch parallel claude -p --model haiku calls (max 5 concurrent)
# 3. Run apply-summaries.py to patch summaries back into the transcript

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TRANSCRIPT="$1"
SESSION_ID="$2"
MAX_PARALLEL=5

if [ -z "$TRANSCRIPT" ] || [ -z "$SESSION_ID" ]; then
   echo "Usage: summarize.sh <transcript.md> <session-id>" >&2
   exit 1
fi

ENTRIES_DIR="/tmp/recall-entries-${SESSION_ID:0:8}"

# Step 1: Extract messages that need summarization
python3 "${SCRIPT_DIR}/extract-longest.py" "$TRANSCRIPT" "$ENTRIES_DIR" 2>&1 | head -5 >&2

if [ ! -d "$ENTRIES_DIR" ] || [ -z "$(ls -A "$ENTRIES_DIR" 2>/dev/null)" ]; then
   echo "No entries to summarize." >&2
   exit 0
fi

# Step 2: Summarize each entry file in parallel using claude -p
RUNNING=0
TOTAL=0
DONE=0

for ENTRY_FILE in "$ENTRIES_DIR"/*.md; do
   [ -f "$ENTRY_FILE" ] || continue
   TOTAL=$((TOTAL + 1))

   # Extract target_words from YAML frontmatter
   TARGET_WORDS=$(grep "^target_words:" "$ENTRY_FILE" | awk '{print $2}')
   if [ -z "$TARGET_WORDS" ]; then
      TARGET_WORDS=50
   fi

   # Extract content (everything after the closing --- of frontmatter)
   CONTENT=$(python3 -c "
import sys
text = open('${ENTRY_FILE}').read()
if text.startswith('---\n'):
   idx = text.index('\n---\n', 4)
   print(text[idx+5:].strip())
else:
   print(text)
" 2>/dev/null)

   if [ -z "$CONTENT" ]; then
      continue
   fi

   # Launch claude -p in background
   (
      PROMPT="You are summarizing a section of a Claude Code conversation transcript.
Your summary will replace the original content to reduce token count.

RULES:
- Maximum length: ${TARGET_WORDS} words. This is a HARD LIMIT. Count your words.
- Never produce an empty summary.

WHAT TO PRESERVE (high value):
- Tool/command names and what they did (e.g., \"Ran Bash: git status\", \"Used Read on config.yaml\")
- File paths that were created, modified, or read
- Function/class/variable names that were defined or discussed
- Key decisions made and their rationale
- Error messages and how they were resolved
- Final outcomes and results

WHAT TO CUT (low value):
- Full file contents (just note the file path and what it contained)
- Verbose tool output (just note the result)
- Code blocks (describe what the code does in one sentence)
- Repetitive explanations or reasoning
- Intermediate failed attempts (just note \"tried X, failed because Y\")
- System reminders and boilerplate

STYLE:
- Use telegraphic style: \"Created utils.py with parse_config() — reads YAML, returns dict\"
- One line per action or decision
- Prefix tool usage with the tool name: \"Bash: ran tests, 3 passed 1 failed\"
- Keep file paths absolute when they appear

Summarize this transcript section:"

      # Use claude -p with haiku model, pipe content via stdin
      SUMMARY=$(echo "$CONTENT" | claude -p --model haiku --no-session-persistence "$PROMPT" 2>/dev/null)

      if [ -n "$SUMMARY" ]; then
         # Reconstruct the entry file: preserve frontmatter, replace content with summary
         python3 -c "
import sys
text = open('${ENTRY_FILE}').read()
if text.startswith('---\n'):
   idx = text.index('\n---\n', 4)
   frontmatter = text[:idx+5]
   with open('${ENTRY_FILE}', 'w') as f:
      f.write(frontmatter + sys.stdin.read().strip() + '\n')
" <<< "$SUMMARY"
      fi
   ) &

   RUNNING=$((RUNNING + 1))

   # Throttle: wait for one to finish when we hit the limit
   if [ "$RUNNING" -ge "$MAX_PARALLEL" ]; then
      wait -n 2>/dev/null || true
      RUNNING=$((RUNNING - 1))
      DONE=$((DONE + 1))
      echo "Summarized $DONE/$TOTAL entries..." >&2
   fi
done

# Wait for remaining background jobs
wait 2>/dev/null
echo "Summarized $TOTAL entries." >&2

# Step 3: Apply summaries back into the transcript
python3 "${SCRIPT_DIR}/apply-summaries.py" "$TRANSCRIPT" "$ENTRIES_DIR" 2>&1 | head -3 >&2

# Step 4: Report new size
NEW_TOKENS=$(python3 -c "f=open('${TRANSCRIPT}','rb');b=f.read();print(f'~{int(len(b)/2.2):,}')" 2>/dev/null)
echo "Final transcript size: ${NEW_TOKENS} tokens" >&2

# Clean up entries directory
rm -rf "$ENTRIES_DIR"

exit 0
