# Recall Plugin Development

## Project Structure

```
Recall/
├── skills/recall/
│   └── scripts/           # Core scripts
│       ├── parse-transcript.py   # JSONL → markdown parser (main script)
│       ├── extract-longest.py    # Iterative partitioning for message selection
│       ├── apply-summaries.py    # Patches summaries back into markdown
│       ├── pre-compact.sh        # PreCompact hook entry point
│       ├── session-start.sh      # SessionStart hook entry point
│       └── summarize.sh          # Orchestrates parallel claude -p summarization
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
│   ├── test_extract_entries.py
│   ├── test_extract_select.py
│   ├── test_apply_summaries.py
│   └── test_pipeline_e2e.py
├── hooks/                 # Plugin system hook definitions
├── APPROACH.md            # Design decisions and architecture
└── README.md              # User-facing documentation
```

## Running Tests

```bash
cd /Users/jeehut/Developer/Indie/Plugins/Recall
python3 -m pytest tests/ -v
```

All 183 tests should pass. If pytest is not installed: `pipx install pytest`.

## When to Run Tests

- **After ANY change** to scripts in `skills/recall/scripts/` — run the full suite
- **After modifying test fixtures** — regenerate with `python3 tests/generate_fixtures.py` then run tests
- **Before committing** — always verify all tests pass

## When to Write New Tests

- **New script functionality** — add tests covering the new behavior
- **Bug fixes** — add a regression test that reproduces the bug before fixing it
- **New tool type support** in `summarize_tool_call()` — add parametrized test cases in `test_parse_tool_calls.py`
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
- Token estimation: `len(text.encode('utf-8')) / 2.2`
- `summarize.sh` calls `claude -p` (external binary) — not unit-testable, tested indirectly via the e2e pipeline with mock summaries
