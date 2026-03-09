#!/bin/bash
# session-start.sh — Cleans up .claude/recall-context.md on session start.
#
# After compaction, CLAUDE.md is re-read and pulls in recall-context.md via @-reference.
# This hook empties the file AFTER it's been read, preventing stale content from
# persisting into the next compaction or new session.
#
# Hook input (stdin JSON): { "session_id": "...", "cwd": "...", "source": "...", ... }

INPUT=$(cat)
CWD=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null)
SOURCE=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('source',''))" 2>/dev/null)

if [ -z "$CWD" ]; then
   exit 0
fi

# After compaction, the recall-context.md is still needed (Claude reads it via @-reference).
# Only clean up on fresh session starts, not after compaction.
if [ "$SOURCE" = "compact" ]; then
   exit 0
fi

CONTEXT_FILE="$CWD/.claude/recall-context.md"

# Empty the file if it exists (write a blank placeholder so the @-reference doesn't error)
if [ -f "$CONTEXT_FILE" ]; then
   echo "<!-- No recall context available. This file is populated by the PreCompact hook. -->" > "$CONTEXT_FILE"
fi

exit 0
