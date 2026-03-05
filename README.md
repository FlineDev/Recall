# Recall

**Never lose context in Claude Code again** — a plugin for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) that recovers rich session context after compaction and across sessions.

## The Problem

When Claude Code auto-compacts your conversation, it generates a brief summary — but loses critical details: the exact wording of your requests, which files were touched and why, what approaches were tried and failed, and what work was still pending. You end up repeating yourself, and Claude forgets decisions you already made.

Recall solves this by parsing the raw session transcript (the JSONL file Claude Code stores locally) and producing a detailed, structured markdown file that preserves:

- **Every user message** — verbatim, exactly as you typed it
- **Every assistant response** — verbatim, including reasoning and decisions
- **Tool call summaries** — which tools were called with what parameters
- **Compaction markers** — so you can see where context was previously lost
- **Loaded skills** — so they can be re-loaded after compaction

All while achieving **99%+ compression** by stripping tool results, thinking blocks, system reminders, and other redundant data.

## Two Use Cases

### Use Case 1: Automatic Recovery After Compaction

This is the primary, "set it and forget it" mode. Two hooks + a CLAUDE.md reference work together:

1. **PreCompact hook** — fires before compaction, parses the full transcript and writes it to `.claude/recall-context.md` in your project. For very large sessions (>25K tokens), it launches parallel `claude -p --model haiku` calls to intelligently compress the biggest messages while preserving key details.

2. **CLAUDE.md `@`-reference** — your project's CLAUDE.md includes `@.claude/recall-context.md`. After compaction, Claude Code re-reads CLAUDE.md from disk and automatically pulls in the recall content.

3. **SessionStart hook** — fires after compaction (and on new sessions), cleans up the recall file to prevent stale content from persisting.

**You do nothing.** Claude seamlessly continues your work with full context — no repeated explanations, no lost decisions.

**Setup requirement:** Add `@.claude/recall-context.md` as the first line of your project's `CLAUDE.md`, and add `.claude/recall-context.md` to your `.gitignore`.

### Use Case 2: Manual Session Recall

When you exit Claude Code, it prints a session ID. Copy it, start a new session (or a different project), and run:

```
/recall <session-id>
```

Claude reads the full transcript from that session and presents a structured summary of what was accomplished, what's pending, and which files matter. Use this to:

- **Continue yesterday's work** — pick up exactly where you left off
- **Resume after a rate limit** — don't lose context when you hit the 5-hour window
- **Brief yourself** — quickly review what happened in a long session

## Installation

### Via Marketplace (Recommended)

Start Claude Code (`claude`), then run these commands inside it:

```
/plugin marketplace add FlineDev/Marketplace
```

```
/plugin install recall
```

Both hooks (PreCompact + SessionStart) are registered automatically. No manual configuration needed.

### Manual

```
/plugin install https://github.com/FlineDev/Recall.git
```

### Without Plugin System

If you prefer not to use the plugin system, you can configure the hooks manually in your project's `.claude/settings.json` or global `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreCompact": [
      {
        "matcher": "auto|manual",
        "hooks": [
          {
            "type": "command",
            "command": "<path-to>/recall/scripts/pre-compact.sh",
            "timeout": 300
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "compact",
        "hooks": [
          {
            "type": "command",
            "command": "<path-to>/recall/scripts/session-start.sh"
          }
        ]
      }
    ]
  }
}
```

Replace `<path-to>` with the absolute path to the `skills` directory.

## How It Works

### The Pipeline

Two hooks coordinate the recovery:

| Hook | When | What it does |
|------|------|-------------|
| `pre-compact.sh` | Before compaction | Parses transcript, summarizes if >25K tokens |
| `session-start.sh` | After compaction | Injects prepared content into Claude's context |

### Summarization Pipeline (for large sessions)

When the transcript exceeds 25K tokens, `summarize.sh` runs automatically:

| Script | Purpose |
|--------|---------|
| `extract-longest.py` | Identifies large messages using iterative partitioning |
| `claude -p --model haiku` | Summarizes each message (up to 5 in parallel) |
| `apply-summaries.py` | Patches summaries back into the transcript |

### What's Preserved vs. Stripped

| Preserved | Stripped |
|-----------|---------|
| All user messages (verbatim) | Tool result contents (large, redundant) |
| All assistant responses (verbatim) | Thinking blocks |
| Tool call summaries (name + key params) | System reminders |
| Compaction markers with token counts | Progress events |
| Loaded skills list | Compaction summaries (we keep more detail) |

### Adaptive Summarization

For very long sessions, Recall uses an iterative partitioning algorithm:

1. **Freeze** the last exchange (most recent user message + response) — always kept verbatim
2. **Calculate** the remaining token budget (target: 15K tokens total)
3. **Partition** messages iteratively: freeze short messages (below average), keep large ones as candidates
4. **Summarize** candidates using parallel `claude -p --model haiku` calls with proportional word targets
5. **Patch** the summaries back into the transcript

This ensures the most recent context is always complete while compressing older, larger messages proportionally.

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (v2.0.76+ recommended)
- Python 3 (pre-installed on macOS)

## Technical Details

- **Transcript location:** `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`
- **Output location:** `/tmp/recall-<session-id>.md`
- **Message cap:** Sessions exceeding 100 messages (50 exchanges) are truncated to the most recent 100
- **Token estimation:** `byte_count / 2.2` — calibrated from empirical data (~2.35 bytes/token for technical markdown + code, using 2.2 to conservatively overestimate by ~7%)
- **Session ID safety:** Always passed explicitly (via user argument or hook stdin), never guessed from filesystem timestamps
- **Parallel summarization:** Up to 5 concurrent `claude -p` calls, using existing Claude Code authentication
