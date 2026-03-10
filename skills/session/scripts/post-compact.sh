#!/bin/bash
# post-compact.sh — Runs on SessionStart(compact) to remind Claude about recall context.
#
# After compaction, .claude/recall-context.md is loaded via CLAUDE.md @-reference.
# This hook outputs a short reminder to stdout, which Claude Code injects as
# additional context — reinforcing that the recall transcript should be acted on.
#
# Hook input (stdin JSON): { "session_id": "...", "cwd": "...", "source": "compact", ... }

INPUT=$(cat)
CWD=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null)

if [ -z "$CWD" ]; then
   exit 0
fi

CONTEXT_FILE="$CWD/.claude/recall-context.md"

# Only output if recall context actually exists and has content
if [ -f "$CONTEXT_FILE" ] && grep -q "## Recall Stats" "$CONTEXT_FILE" 2>/dev/null; then
   echo "Recall plugin: detailed pre-compaction transcript loaded via recall-context.md. Print a short status line (tokens, verbatim %) and continue working."
fi

exit 0
