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

if [ -z "$CWD" ]; then
   exit 0
fi

# Always clean up, regardless of source (startup, compact, resume, clear).
# After compaction: CLAUDE.md was already re-read (content consumed), so cleaning is safe.
# Cleaning after compact is important for parallel sessions in the same project —
# stale content from one session's compaction must not leak into another session.
# On fresh starts: prevents leftover content from a previous session (e.g., user exited
# mid-compaction) from being injected into the new session's context.

CONTEXT_FILE="$CWD/.claude/recall-context.md"

# Empty the file if it exists (write a blank placeholder so the @-reference doesn't error)
if [ -f "$CONTEXT_FILE" ]; then
   echo "<!-- No recall context available. This file is populated by the PreCompact hook. -->" > "$CONTEXT_FILE"
fi

exit 0
