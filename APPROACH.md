# Recall: Design Decisions

## Core Approach: PreCompact writes, CLAUDE.md reads, SessionStart cleans

Claude Code's SessionStart hook stdout is silently dropped (bug: github.com/anthropics/claude-code/issues/28305).
However, CLAUDE.md IS re-read from disk after every compaction, and `@file` references are resolved during that re-read.

### Flow

1. **PreCompact hook** (runs before compaction):
   - Parses transcript → generates recall content
   - If >20K tokens: condenses with a single `claude -p --model sonnet` call (~30-40s)
   - Writes result to `.claude/recall-context.md` in the project directory
   - Also writes to `/tmp/recall-<session-id>.md` as a persistent copy

2. **Compaction happens**:
   - Claude Code re-reads CLAUDE.md from disk
   - CLAUDE.md contains `@.claude/recall-context.md` (first line)
   - The recall content is pulled into Claude's context automatically

3. **SessionStart(compact) hook** (runs after compaction):
   - Outputs a short stdout reminder to Claude to act on the recall transcript
   - Reinforces the instructions in `recall-context.md`

4. **SessionStart hook** (runs on every session start, including after compaction):
   - Empties `.claude/recall-context.md` (writes placeholder comment)
   - Matcher `""` matches ALL sources (startup, compact, resume, clear)
   - After compaction: safe because CLAUDE.md was already re-read (content consumed)
   - Essential for parallel sessions — stale content from one session must not leak into another
   - On fresh starts: catches leftovers from interrupted compactions

### Why this works

- CLAUDE.md is read BEFORE hooks fire (confirmed by research)
- PreCompact runs BEFORE compaction → file has content when CLAUDE.md is re-read
- SessionStart runs AFTER CLAUDE.md is read → cleaning up doesn't affect current read

### Edge cases

- **Multiple sessions same project**: PreCompact overwrites the file (last writer wins).
  SessionStart always cleans up after compaction, so parallel sessions don't see stale content.
- **Interrupted compaction**: If the user exits mid-compaction, the file may still have content.
  SessionStart on the next fresh session cleans it up.

## Condensation Strategy

Instead of per-message summarization (the old approach with 48 parallel Haiku calls that took 5 minutes
and was effectively a no-op due to a token mismatch bug), we use a simple tail-preservation approach:

- **≤20K tokens**: Keep the full transcript as-is, no API call
- **>20K tokens**: Keep last ~15K tokens verbatim (snapping to exchange boundaries),
  summarize up to 85K of older context with a single Sonnet call

This takes ~30-40 seconds and produces a ~17.5K token output (within the 15-20K target range,
~10% of Claude Code's 200K context window).

## Per-Project Setup

Each project needs four things (configured by `/recall:init`):
1. `@.claude/recall-context.md` as the first line of CLAUDE.md
2. `.claude/recall-context.md` file (placeholder, auto-populated by hook)
3. `.claude/recall-context.md` in `.gitignore`
4. Recall hooks in `.claude/settings.json` (plugin hooks are unreliable, so init writes them directly)
