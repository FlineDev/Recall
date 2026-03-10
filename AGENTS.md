# Recall Plugin

## Project Structure

```
Recall/
├── skills/session/
│   └── scripts/           # Core scripts
│       ├── parse-transcript.py   # JSONL → markdown parser (main script)
│       ├── condense-tail.py      # Split + combine for large transcripts (>20K tokens)
│       ├── pre-compact.sh        # PreCompact hook entry point
│       ├── post-compact.sh       # Post-compaction stdout reminder
│       └── session-start.sh      # SessionStart hook (cleanup)
├── tests/
│   ├── conftest.py               # Shared fixtures, module imports
│   ├── generate_fixtures.py      # Generates synthetic JSONL + markdown fixtures
│   ├── fixtures/                 # Generated test data (fictional "TaskTracker" project)
│   │   ├── jsonl/                # 16 JSONL transcript variants
│   │   └── markdown/             # 5 parsed markdown variants
│   ├── test_parse_tool_calls.py
│   ├── test_parse_condensers.py
│   ├── test_parse_session.py
│   ├── test_parse_postprocess.py
│   └── test_condense_tail.py     # Tests for split/combine logic
├── commands/
│   ├── session.md        # /recall:session — manual session recall
│   ├── compact-on.md     # /recall:compact-on — enable compaction integration
│   └── compact-off.md    # /recall:compact-off — disable compaction integration
└── README.md              # User-facing documentation
```

## Architecture: PreCompact writes, CLAUDE.md reads, SessionStart cleans

Claude Code's SessionStart hook stdout is silently dropped ([bug](https://github.com/anthropics/claude-code/issues/28305)).
However, CLAUDE.md IS re-read from disk after every compaction, and `@file` references are resolved during that re-read.

### Hook Flow

1. **PreCompact hook** (`pre-compact.sh`):
   - Parses transcript → generates recall content
   - If >20K tokens: condenses with a single `claude -p --model sonnet` call (~30-40s)
   - Writes result to `.claude/recall-context.md` in the project directory
   - Also writes to `/tmp/recall-<session-id>.md` as a persistent copy

2. **Compaction happens**:
   - Claude Code re-reads CLAUDE.md from disk
   - CLAUDE.md contains `@.claude/recall-context.md` (first line)
   - The recall content is pulled into Claude's context automatically

3. **SessionStart(compact) hook** (`post-compact.sh`):
   - Outputs a short stdout reminder to Claude to act on the recall transcript

4. **SessionStart hook** (`session-start.sh`):
   - Empties `.claude/recall-context.md` (writes placeholder comment)
   - Matcher `""` matches ALL sources (startup, compact, resume, clear)
   - After compaction: safe because CLAUDE.md was already re-read (content consumed)
   - Essential for parallel sessions — stale content from one session must not leak into another
   - On fresh starts: catches leftovers from interrupted compactions

### Why this ordering works

- CLAUDE.md is read BEFORE hooks fire (confirmed by research)
- PreCompact runs BEFORE compaction → file has content when CLAUDE.md is re-read
- SessionStart runs AFTER CLAUDE.md is read → cleaning up doesn't affect current read

### Edge cases

- **Multiple sessions same project**: PreCompact overwrites the file (last writer wins). SessionStart always cleans up, so parallel sessions don't see stale content.
- **Interrupted compaction**: If the user exits mid-compaction, the file may still have content. SessionStart on the next fresh session cleans it up.

## Condensation Strategy

Tail-preservation approach (replaced the old 48-parallel-Haiku-call approach that took 5 minutes):

- **≤20K tokens**: Keep the full transcript as-is, no API call
- **>20K tokens**: Keep last ~15K tokens verbatim (snapping to exchange boundaries), summarize up to 85K of older context with a single Sonnet call

Produces ~17.5K token output (within the 15-20K target range, ~10% of Claude Code's 200K context window).

## Per-Project Setup

Each project needs four things (configured by `/recall:compact-on`):

1. `@.claude/recall-context.md` as the first line of CLAUDE.md
2. `.claude/recall-context.md` file (placeholder, auto-populated by hook)
3. `.claude/recall-context.md` in `.gitignore`
4. Recall hooks in `.claude/settings.json` (per-project, written by compact-on so users control which projects use it)

## Testing

```bash
pytest tests/ -v
```

All 170 tests should pass. If pytest is not installed: `pipx install pytest`.

### When to Run Tests

- **After ANY change** to scripts in `skills/session/scripts/` — run the full suite
- **After modifying test fixtures** — regenerate with `python3 tests/generate_fixtures.py` then run tests
- **Before committing** — always verify all tests pass

### When to Write New Tests

- **New script functionality** — add tests covering the new behavior
- **Bug fixes** — add a regression test that reproduces the bug before fixing it
- **New tool type support** in `summarize_tool_call()` — add parametrized test cases in `test_parse_tool_calls.py`
- **Changes to split/combine logic** — add tests in `test_condense_tail.py`
- **Changed JSONL parsing** — add or update fixture variants in `generate_fixtures.py`

### Test Fixture Conventions

All fixtures use a fictional **"TaskTracker" Rust CLI project** with user "alex". This is intentional — the Recall repo is public, so test data must contain **zero personal information**. When adding fixtures:

- Use paths like `~/projects/tasktracker/src/...`
- Use commands like `cargo test`, `cargo build`, `git commit`
- Use realistic but generic Rust code snippets
- Never use real usernames, project names, or private content

## Key Technical Details

- Scripts have hyphens in names → imported via `importlib` in conftest.py
- HOME is monkeypatched to `/home/alex` for stable path shortening assertions
- Token estimation: `len(text.encode('utf-8')) / 3.0`
- `condense-tail.py` handles splitting/combining, and `pre-compact.sh` makes a single `claude -p --model sonnet` call when needed
