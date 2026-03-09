# Recall Plugin Development

## Project Structure

```
Recall/
├── skills/recall/
│   └── scripts/           # Core scripts
│       ├── parse-transcript.py   # JSONL → markdown parser (main script)
│       ├── condense-tail.py      # Split + combine for large transcripts (>20K tokens)
│       ├── pre-compact.sh        # PreCompact hook entry point
│       └── session-start.sh      # SessionStart hook entry point
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
│   └── setup.md           # /recall:init — per-project configuration
├── hooks/                 # Plugin system hook definitions
├── APPROACH.md            # Design decisions and architecture
└── README.md              # User-facing documentation
```

## Running Tests

```bash
pytest tests/ -v
```

All 170 tests should pass. If pytest is not installed: `pipx install pytest`.

## When to Run Tests

- **After ANY change** to scripts in `skills/recall/scripts/` — run the full suite
- **After modifying test fixtures** — regenerate with `python3 tests/generate_fixtures.py` then run tests
- **Before committing** — always verify all tests pass

## When to Write New Tests

- **New script functionality** — add tests covering the new behavior
- **Bug fixes** — add a regression test that reproduces the bug before fixing it
- **New tool type support** in `summarize_tool_call()` — add parametrized test cases in `test_parse_tool_calls.py`
- **Changes to split/combine logic** — add tests in `test_condense_tail.py`
- **Changed JSONL parsing** — add or update fixture variants in `generate_fixtures.py`

## Test Fixture Conventions

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
