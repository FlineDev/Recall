#!/bin/bash
# session-start.sh — Runs on SessionStart after compaction.
# Injects the recall transcript directly into Claude's context via additionalContext JSON.
#
# Hook input (stdin JSON): { "session_id": "...", "cwd": "...", "source": "compact", ... }
# Hook output (stdout): JSON with additionalContext — injected into Claude's context window.

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

# Inject the file content into Claude's context via additionalContext JSON.
# This is the reliable method (fixed in Claude Code v2.0.76+).
# Python handles JSON escaping of the file content properly.
python3 -c "
import json, sys

with open('${OUTPUT_FILE}') as f:
   content = f.read()

# Build the instructions + transcript content
context = '''=== RECALL: FULL PRE-COMPACTION TRANSCRIPT ===

The following is the COMPLETE conversation from before compaction — every user message,
every assistant response, every file touched. This is far more detailed than the
compaction summary above.

After reading this transcript, do ALL of the following before resuming work:
(1) UNDERSTAND the conversation: What was the main goal? What was the last pending task?
(2) RE-READ relevant files: Identify files needed for pending work from the FILES TOUCHED
    section and conversation context. Re-read code/config files being actively worked on.
(3) RE-LOAD skills: Check the === SKILLS LOADED === section. Re-load any skills needed
    for the pending work with /skillname.
(4) CONTINUE working on the pending task. If nothing is pending, briefly summarize what
    was accomplished and ask the user what to do next.
Do NOT present a formal session-resume summary — just seamlessly continue the work.

''' + content

output = {
   'hookSpecificOutput': {
      'hookEventName': 'SessionStart',
      'additionalContext': context
   }
}

json.dump(output, sys.stdout)
" 2>/dev/null

exit 0
