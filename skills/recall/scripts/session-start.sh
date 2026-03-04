#!/bin/bash
# session-start.sh — Runs on SessionStart after compaction.
# Outputs instructions for Claude to read the recall transcript file.
#
# Strategy: PreCompact already created the file. We output plain text telling
# Claude to read it. We also try additionalContext JSON (currently broken for
# "compact" source — see github.com/anthropics/claude-code/issues/28305).
# When the bug is fixed, the JSON path gives instant injection without a Read call.
#
# Hook input (stdin JSON): { "session_id": "...", "cwd": "...", "source": "compact", ... }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INPUT=$(cat)

SESSION_ID=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
CWD=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null)

if [ -z "$SESSION_ID" ]; then
   exit 0
fi

OUTPUT_FILE="/tmp/recall-${SESSION_ID}.md"

# Fallback: if PreCompact didn't run (e.g., first install), generate the file now
if [ ! -f "$OUTPUT_FILE" ] || [ ! -s "$OUTPUT_FILE" ]; then
   python3 "${SCRIPT_DIR}/parse-transcript.py" "$SESSION_ID" --cwd "$CWD" > "$OUTPUT_FILE" 2>/dev/null

   # If still >25K tokens, run summarization (blocks but necessary)
   if [ -f "$OUTPUT_FILE" ] && [ -s "$OUTPUT_FILE" ]; then
      TOKENS=$(grep "Estimated tokens:" "$OUTPUT_FILE" | head -1 | sed 's/.*~\([0-9,]*\).*/\1/')
      TOKENS_NUM=$(echo "$TOKENS" | tr -d ',')
      if [ -n "$TOKENS_NUM" ] && [ "$TOKENS_NUM" -gt 25000 ]; then
         export RECALL_HOOK_ACTIVE=1
         bash "${SCRIPT_DIR}/summarize.sh" "$OUTPUT_FILE" "$SESSION_ID" 2>/dev/null
      fi
   fi
fi

# Final check: file must exist and be non-empty
if [ ! -f "$OUTPUT_FILE" ] || [ ! -s "$OUTPUT_FILE" ]; then
   exit 0
fi

# Output plain text instructions for Claude to read the file.
# This appears as hook output in Claude's context after compaction.
cat << RECALL_EOF
OVERRIDE — MANDATORY ACTION REQUIRED (from Recall plugin):

A detailed pre-compaction transcript has been prepared at:
${OUTPUT_FILE}

This file contains the COMPLETE conversation from before compaction — every user message,
every assistant response, every tool call, every file touched. It is FAR more detailed
than the compaction summary above.

You MUST use the Read tool to read this file IN FULL before doing anything else.
Then do ALL of the following:
(1) UNDERSTAND the conversation: What was the main goal? What was the last pending task?
(2) RE-READ relevant files needed for pending work (from the FILES TOUCHED section).
(3) RE-LOAD skills from the === SKILLS LOADED === section if needed.
(4) CONTINUE working on the pending task seamlessly. Do NOT present a formal summary.
RECALL_EOF

exit 0
