# Recall

**Never lose context in Claude Code again** — a plugin that recovers rich session context after compaction and across sessions.

## What You'll See

After compaction, Claude automatically prints:

```
Recall loaded: ~16,440 tokens (25% verbatim, 72% summarized)
Full transcript: recall-943494ae.md
```

Then it seamlessly continues your work — no repeated explanations, no lost decisions, no "where were we?"

Without Recall, compaction produces a brief summary that loses: the exact wording of your requests, which files were touched and why, what approaches were tried and failed, and what work was still pending.

With Recall, **99%+ of the noise is stripped** (tool results, thinking blocks, system reminders) while preserving:

- Every user message — verbatim
- Every assistant response — verbatim
- Tool call summaries — which tools were called with what parameters
- Compaction markers — so you can see where context was previously lost
- Loaded skills — so they can be re-loaded after compaction

## Installation

### Step 1: Install the plugin

Start Claude Code, then run:

```
/plugin marketplace add FlineDev/Marketplace
```

```
/plugin install recall
```

This registers two hooks automatically (PreCompact + SessionStart). Nothing else to configure globally.

### Step 2: Set up each project

In every project where you want automatic recovery, run:

```
/recall:setup
```

This does three things:
1. Creates `.claude/recall-context.md` (auto-populated by the hook)
2. Adds `@.claude/recall-context.md` as the first line of your `CLAUDE.md`
3. Adds `.claude/recall-context.md` to `.gitignore`

**That's it.** Compaction recovery is now automatic. You'll never need to think about it again.

### Alternative: Install without Marketplace

```
/plugin install https://github.com/FlineDev/Recall.git
```

Then run `/recall:setup` in each project.

### Alternative: Manual setup (without plugin system)

<details>
<summary>Click to expand manual configuration</summary>

Add these hooks to your `.claude/settings.json` (project or global):

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
        "matcher": "",
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

Then manually:
1. Create `.claude/recall-context.md` with any placeholder content
2. Add `@.claude/recall-context.md` as the first line of your `CLAUDE.md`
3. Add `.claude/recall-context.md` to your `.gitignore`

</details>

## Two Modes

### Automatic (after compaction)

This is the primary, "set it and forget it" mode. When compaction happens — whether automatic or via `/compact` — Recall:

1. **PreCompact hook** parses the full transcript and writes it to `.claude/recall-context.md`
2. **CLAUDE.md `@`-reference** pulls the recall content into Claude's context after compaction
3. **SessionStart hook** cleans up the file to prevent stale content

**You do nothing.** Claude prints the stats line and continues where it left off.

### Manual (across sessions)

When you exit Claude Code, it prints a session ID. Copy it, start a new session, and run:

```
/recall <session-id>
```

Claude reads the full transcript from that session and presents a structured summary. Use this to:

- **Continue yesterday's work** — pick up exactly where you left off
- **Resume after a rate limit** — don't lose context when you hit the 5-hour window
- **Brief yourself** — quickly review what happened in a long session

## How It Works

### Condensation (for large sessions)

When the parsed transcript exceeds 20K tokens, `condense-tail.py` splits it:

| Part | Size | Treatment |
|------|------|-----------|
| Recent exchanges | ~15K tokens | Kept verbatim (most recent context matters most) |
| Older context | Up to 85K tokens | Summarized by a single `claude -p --model sonnet` call (~30-40s) |

The result targets 15-20K tokens (~10% of Claude Code's 200K context window). For shorter sessions (<20K tokens), the full transcript is kept as-is with no API call.

### What's Preserved vs. Stripped

| Preserved | Stripped |
|-----------|---------|
| All user messages (verbatim) | Tool result contents (large, redundant) |
| All assistant responses (verbatim) | Thinking blocks |
| Tool call summaries (name + key params) | System reminders |
| Compaction markers with token counts | Progress events |
| Loaded skills list | Compaction summaries (we keep more detail) |

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (v2.0.76+ recommended)
- Python 3 (pre-installed on macOS)

## Technical Details

- **Transcript location:** `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`
- **Output location:** `/tmp/recall-<session-id>.md` (persists until reboot)
- **No message cap:** All exchanges are preserved; `condense-tail.py` handles sizing
- **Token estimation:** `byte_count / 2.2` (conservatively overestimates by ~7%)
- **Session ID safety:** Always passed explicitly (via user argument or hook stdin), never guessed from filesystem timestamps
- **Condensation:** Single `claude -p --model sonnet` call (~30-40 seconds), using existing Claude Code authentication
