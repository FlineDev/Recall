#!/bin/bash
# pre-compact.sh — Runs on PreCompact to generate the recall transcript.
# Parses the session transcript and condenses if too large (single Sonnet call).
# Writes to both /tmp/ (for manual /recall) and .claude/recall-context.md
# (for automatic injection via CLAUDE.md @-reference after compaction).
#
# Output targets 15-20K tokens (~10% of Claude Code's 200K context window).
#
# Hook input (stdin JSON): { "session_id": "...", "cwd": "...", "trigger": "auto|manual", ... }
# Hook output: None (PreCompact stdout is not injected into context).

# Recursion guard: if claude -p is called for condensation, it might trigger
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

# Step 2: Condense if needed (>20K tokens)
# Keeps ~15K tokens of recent exchanges verbatim, summarizes older context
# with a single claude -p --model sonnet call into ~2.5K tokens.
CONDENSE_EXIT=0
python3 "${SCRIPT_DIR}/condense-tail.py" split "$OUTPUT_FILE" "$SESSION_ID" 2>>/tmp/recall-precompact.log || CONDENSE_EXIT=$?

if [ "$CONDENSE_EXIT" -eq 0 ]; then
   SID_PREFIX="${SESSION_ID:0:8}"

   # Must unset CLAUDECODE to allow claude -p from within Claude Code
   unset CLAUDECODE

   cat "/tmp/recall-older-${SID_PREFIX}.md" | \
     claude -p --model sonnet --no-session-persistence \
       "$(cat /tmp/recall-prompt-${SID_PREFIX}.txt)" \
       > "/tmp/recall-summary-${SID_PREFIX}.md" 2>>/tmp/recall-precompact.log

   python3 "${SCRIPT_DIR}/condense-tail.py" combine "$OUTPUT_FILE" "$SESSION_ID" 2>>/tmp/recall-precompact.log
fi

# Step 3: Write to $CWD/.claude/recall-context.md for automatic injection.
# After compaction, Claude Code re-reads CLAUDE.md from disk. If the project's
# CLAUDE.md (or AGENTS.md) contains @.claude/recall-context.md, the recall content
# is pulled into context automatically — no SessionStart stdout needed.
if [ -n "$CWD" ] && [ -d "$CWD/.claude" ]; then
   CONTEXT_FILE="$CWD/.claude/recall-context.md"

   # Build the context file with instructions header
   cat > "$CONTEXT_FILE" << 'HEADER'
<!-- Recall: Pre-compaction transcript. This file is auto-generated and auto-cleaned. -->

IMPORTANT: This is the COMPLETE conversation from before compaction. It contains every
user message, assistant response, and tool call — far more detailed than the compaction
summary. After reading this, do ALL of the following:

1. UNDERSTAND the conversation arc and identify the last pending task
2. RE-READ files needed for pending work (check FILES TOUCHED section)
3. RE-LOAD skills from the SKILLS LOADED section if needed
4. CONTINUE working on the pending task seamlessly — do NOT present a formal summary

If no work is pending, briefly summarize what was accomplished and ask what to do next.

---

HEADER
   cat "$OUTPUT_FILE" >> "$CONTEXT_FILE"
fi

exit 0
