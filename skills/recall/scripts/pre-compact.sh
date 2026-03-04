#!/bin/bash
# pre-compact.sh — Runs on PreCompact to generate the recall transcript.
# Parses the session transcript and optionally summarizes if too large.
# The resulting file is picked up by session-start.sh after compaction.
#
# Hook input (stdin JSON): { "session_id": "...", "cwd": "...", "trigger": "auto|manual", ... }
# Hook output: None (PreCompact stdout is not injected into context).

# Recursion guard: if claude -p is called for summarization, it might trigger
# its own compaction, which would fire this hook again. Prevent infinite loops.
if [ -n "$RECALL_HOOK_ACTIVE" ]; then
   exit 0
fi
export RECALL_HOOK_ACTIVE=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INPUT=$(cat)

SESSION_ID=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
CWD=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null)

if [ -z "$SESSION_ID" ]; then
   exit 0
fi

OUTPUT_FILE="/tmp/recall-${SESSION_ID}.md"

# Step 1: Run the parser (stderr goes to log, stdout to file)
python3 "${SCRIPT_DIR}/parse-transcript.py" "$SESSION_ID" --cwd "$CWD" > "$OUTPUT_FILE" 2>/tmp/recall-precompact.log

if [ ! -f "$OUTPUT_FILE" ] || [ ! -s "$OUTPUT_FILE" ]; then
   exit 0
fi

# Step 2: Check if summarization is needed
TOKENS=$(grep "Estimated tokens:" "$OUTPUT_FILE" | head -1 | sed 's/.*~\([0-9,]*\).*/\1/')
TOKENS_NUM=$(echo "$TOKENS" | tr -d ',')

if [ -n "$TOKENS_NUM" ] && [ "$TOKENS_NUM" -gt 25000 ]; then
   # Run the summarization pipeline (parallel claude -p calls)
   bash "${SCRIPT_DIR}/summarize.sh" "$OUTPUT_FILE" "$SESSION_ID" 2>>/tmp/recall-precompact.log
fi

# File is now ready for session-start.sh to inject after compaction
exit 0
