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

1. **PreCompact hook** — fires before compaction, parses the full transcript and writes it to `.claude/recall-context.md` in your project. For very large sessions (>20K tokens), it runs a single `claude -p --model sonnet` call to summarize older context while keeping recent exchanges verbatim.

2. **CLAUDE.md `@`-reference** — your project's CLAUDE.md includes `@.claude/recall-context.md`. After compaction, Claude Code re-reads CLAUDE.md from disk and automatically pulls in the recall content.

3. **SessionStart hook** — fires after compaction (and on new sessions), cleans up the recall file to prevent stale content from persisting.

**You do nothing.** Claude seamlessly continues your work with full context — no repeated explanations, no lost decisions.

**One-time setup per project:** Run `/recall:setup` to configure the CLAUDE.md reference and .gitignore entry (see Installation).

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

Both hooks (PreCompact + SessionStart) are registered automatically.

Then, in each project where you want automatic recovery, run the setup command:

```
/recall:setup
```

This configures the current project by:
- Creating `.claude/recall-context.md` (the auto-generated context file)
- Adding `@.claude/recall-context.md` to the first line of `CLAUDE.md` (creates it if needed)
- Adding `.claude/recall-context.md` to `.gitignore`

You only need to run setup once per project. After that, everything is automatic.

### Manual

```
/plugin install https://github.com/FlineDev/Recall.git
```

Then run `/recall:setup` in each project.

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

Then manually perform the setup steps:
1. Create `.claude/recall-context.md` with placeholder content
2. Add `@.claude/recall-context.md` as the first line of your `CLAUDE.md`
3. Add `.claude/recall-context.md` to your `.gitignore`

## How It Works

### The Pipeline

Two hooks coordinate the recovery:

| Hook | When | What it does |
|------|------|-------------|
| `pre-compact.sh` | Before compaction | Parses transcript, condenses if >20K tokens |
| `session-start.sh` | On session start | Cleans up recall file to prevent stale content |

### Condensation (for large sessions)

When the transcript exceeds 20K tokens, `condense-tail.py` splits the conversation:

| Part | Size | Treatment |
|------|------|-----------|
| Recent exchanges | ~15K tokens | Kept verbatim (most recent context) |
| Older context | Up to 85K tokens | Summarized by a single `claude -p --model sonnet` call (~30-40s) |

The result is a ~17.5K token file: a concise summary of older work followed by the full recent conversation. Output targets 15-20K tokens (~10% of Claude Code's 200K context window). This takes ~30-40 seconds (one API call).

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
- **Output location:** `/tmp/recall-<session-id>.md`
- **No message cap:** All exchanges are preserved; `condense-tail.py` handles sizing (15K tail + up to 85K older)
- **Token estimation:** `byte_count / 2.2` — calibrated from empirical data (~2.35 bytes/token for technical markdown + code, using 2.2 to conservatively overestimate by ~7%)
- **Session ID safety:** Always passed explicitly (via user argument or hook stdin), never guessed from filesystem timestamps
- **Condensation:** Single `claude -p --model sonnet` call (~30-40 seconds), using existing Claude Code authentication
