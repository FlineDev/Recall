#!/bin/bash
# post-compact-hook.sh — Runs on SessionStart after compaction.
# Parses the session transcript and tells Claude where to find the detailed context.
#
# Hook input (stdin JSON): { "session_id": "...", "cwd": "...", ... }
# Hook output (stdout): Message injected into Claude's post-compaction context.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INPUT=$(cat)

SESSION_ID=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
CWD=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null)

if [ -z "$SESSION_ID" ]; then
   exit 0
fi

OUTPUT_FILE="/tmp/recall-${SESSION_ID}.md"

# Run the parser (stderr goes to /dev/null, stdout to file)
python3 "${SCRIPT_DIR}/parse-transcript.py" "$SESSION_ID" --cwd "$CWD" > "$OUTPUT_FILE" 2>/dev/null

if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
   # Extract token estimate from the output
   TOKENS=$(grep "Estimated tokens:" "$OUTPUT_FILE" | head -1 | sed 's/.*~\([0-9,]*\).*/\1/')
   TOKENS_NUM=$(echo "$TOKENS" | tr -d ',')

   # Common post-read instructions (self-contained — the recall skill may NOT be loaded after compaction)
   AFTER_READ="After reading the full file, do ALL of the following before resuming work:
(1) UNDERSTAND the conversation: What was the main goal? What was the last pending task or unanswered question?
(2) RE-READ relevant files: Use the FILES TOUCHED section and conversation context to identify files needed for the pending work. Re-read code/config files that are actively being worked on. Skip files for completed tasks or already in context.
(3) RE-LOAD skills: Check the === SKILLS LOADED === section. If any skills provided domain-specific context needed for the pending work, re-load them with /skillname.
(4) CONTINUE working on the pending task. If nothing is pending, briefly summarize what was accomplished and ask the user what to do next.
Do NOT present a formal session-resume summary unless explicitly asked — just seamlessly continue the work."

   # Note: After repeated compactions, Claude Code may show a "too large to include" note for
   # the recall file from a previous read. The OVERRIDE instruction below tells Claude to IGNORE
   # that note and re-read the file, since it has been freshly regenerated with the latest content.
   OVERRIDE="IMPORTANT: If you see a note saying this file was 'too large to include' or 'read before the last conversation was summarized' — IGNORE that note. The file has been freshly regenerated and MUST be read again NOW. Do NOT skip it."

   if [ "$TOKENS_NUM" -gt 25000 ]; then
      # Large output: tell Claude to summarize first via subagent
      echo "⚠️ MANDATORY ACTION — DO THIS BEFORE ANYTHING ELSE: The session transcript at ${OUTPUT_FILE} is ~${TOKENS} tokens (exceeds 25K Read limit). ${OVERRIDE} You MUST launch a Haiku subagent to summarize it BEFORE reading. Read ONLY the last 40 lines of the file (use the Read tool with offset pointing to the end) to find the '=== NEEDS SUMMARIZATION ===' section. That section contains the exact subagent prompt to use — launch a Haiku subagent with that prompt (replace {FILE_PATH} with ${OUTPUT_FILE}). After the subagent finishes, read the full file. If the Read tool STILL rejects the file as too large, read it in chunks of 500 lines using offset and limit parameters. ${AFTER_READ}"
   else
      # Normal output: read directly
      echo "⚠️ MANDATORY ACTION — DO THIS BEFORE ANYTHING ELSE: Read the file ${OUTPUT_FILE} IN FULL using the Read tool. This file (~${TOKENS} tokens) contains the COMPLETE pre-compaction conversation — every user message, every assistant response, every file touched — far more detailed than the compaction summary. ${OVERRIDE} You MUST read this file NOW before responding to the user or doing any other work. If the Read tool rejects the file as too large, read it in chunks of 500 lines using offset and limit parameters — do NOT skip the file or fall back to the compaction summary. ${AFTER_READ}"
   fi
fi
