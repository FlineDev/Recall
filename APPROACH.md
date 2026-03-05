# Recall: CLAUDE.md @-Reference Approach

## Problem

SessionStart(compact) hook runs scripts reliably, but its stdout is silently dropped
by Claude Code (bug: github.com/anthropics/claude-code/issues/28305). This means we
cannot inject recall content via `additionalContext` JSON or plain text output.

However, CLAUDE.md IS re-read from disk after every compaction. And `@file` references
in CLAUDE.md are resolved during that re-read.

## Solution: PreCompact writes, CLAUDE.md reads, SessionStart cleans

### Flow

1. **PreCompact hook** (runs before compaction):
   - Parses transcript → generates recall content
   - If >25K tokens: runs parallel `claude -p --model haiku` summarization
   - Writes result to `.claude/recall-context.md` in the project directory

2. **Compaction happens**:
   - Claude Code re-reads CLAUDE.md from disk
   - CLAUDE.md contains `@.claude/recall-context.md`
   - The recall content is pulled into Claude's context automatically
   - Claude sees the full pre-compaction transcript as part of its instructions

3. **SessionStart(compact) hook** (runs after compaction):
   - Empties `.claude/recall-context.md` (truncates to 0 bytes or writes empty marker)
   - The script runs reliably — only stdout injection is broken
   - This prevents stale content from being loaded on next compaction or new session

4. **SessionStart(startup) hook** (runs on new session):
   - Also empties `.claude/recall-context.md` as a safety net
   - This matcher works reliably (both script execution AND stdout injection)
   - Prevents new sessions from seeing stale recall content

### Why this works

- CLAUDE.md is read BEFORE hooks fire (confirmed by research)
- PreCompact runs BEFORE compaction → file has content when CLAUDE.md is re-read
- SessionStart runs AFTER CLAUDE.md is read → cleaning up doesn't affect current read
- The file is within the project directory → @-reference resolves reliably

### Edge cases

- **Multiple sessions same project**: Unlikely two compactions happen simultaneously.
  If they do, PreCompact overwrites the file (last writer wins). Not ideal but not
  catastrophic.
- **New session sees stale content**: SessionStart(startup) empties the file, but
  CLAUDE.md was already read before the hook fires. The stale content would be from
  a different session. Mitigation: include session ID in the file so Claude can
  recognize and ignore stale content.
- **Session ID awareness**: Claude does NOT know its own session ID in-context. But
  the recall file contains the session ID it was generated for. If it doesn't match,
  Claude should ignore it (add instruction in CLAUDE.md).

### Changes needed

1. **pre-compact.sh**: Write output to `$CWD/.claude/recall-context.md` instead of
   `/tmp/recall-{session_id}.md` (keep /tmp as backup)
2. **session-start.sh**: Empty `$CWD/.claude/recall-context.md` on both `compact`
   and `startup` matchers (or use a single matcher that covers both)
3. **Each project's CLAUDE.md** (or AGENTS.md): Add `@.claude/recall-context.md`
4. **Each project's .gitignore**: Add `.claude/recall-context.md`
5. **SKILL.md**: Update manual `/recall` to also write to `.claude/recall-context.md`

### Hook configuration

```json
{
  "hooks": {
    "PreCompact": [
      {
        "matcher": "auto|manual",
        "hooks": [
          {
            "type": "command",
            "command": ".../pre-compact.sh",
            "timeout": 300
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": ".../session-start.sh"
          }
        ]
      }
    ]
  }
}
```

Note: Empty matcher `""` matches ALL SessionStart sources (startup, compact, resume,
clear). This ensures the file is always cleaned up regardless of how the session starts.
