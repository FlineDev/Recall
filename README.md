# Recall

**Get the most out of Claude Code's 200K context window** — without paying for the 1M token tier.

Claude Code gives you 200K tokens of context. But ~20-25% is consumed by system context (tools, prompts, CLAUDE.md), and auto-compaction triggers at ~85% — leaving you with roughly 120-130K usable tokens before your entire conversation gets compressed into a ~2,000-word summary. That summary captures the gist, but loses the details: your exact instructions, the approaches that failed, the architecture decisions you agreed on.

Recall changes this. It parses the raw session transcript — stripping 99% of noise (tool results, thinking blocks, system reminders) — and preserves what matters: every user message verbatim, every assistant response, every decision with rationale. After compaction, Claude continues as if nothing happened. No repeated questions, no re-investigating solved bugs, no forgotten corrections.

And if you turn off auto-compaction entirely, Recall lets you use **100% of your context window** without fear. When the session ends, just start a new one and run `/recall <session-id>` — the previous session's full context is restored in seconds. No more leaving 15% of your context unused "just in case."

## Why Recall Exists

Claude Code's built-in compaction summary is ~2,000 words — less than 1% of your original context. It preserves the topic, but loses the details that matter:

| Lost after compaction | Why it matters |
|---|---|
| Exact user instructions | Claude re-asks questions you already answered |
| Failed approaches & why they failed | Claude retries things that didn't work |
| Architecture decisions & rationale | Claude makes different choices than what you agreed on |
| Intermediate debugging steps | Bugs get re-investigated from scratch |
| File edit history & frequency | Claude doesn't know which files it already changed |
| Code review feedback & corrections | Your preferences are forgotten |

### What Recall preserves

**99%+ of noise stripped** (tool results, thinking blocks, system reminders) while keeping:

- Every user message — verbatim
- Every assistant response — verbatim
- Tool call summaries — which tools were called with what parameters
- Compaction markers — so you can see where context was previously lost
- Loaded skills — so they can be re-loaded after compaction

### See the difference

Both examples below show the same fictional session — adding recurring tasks to a Swift app:

- **[Compaction summary](examples/compaction-summary.md)** (~2,000 words) — What Claude Code produces by default. Preserves the topic and key files, but not the details: that you debated UTC vs. local-time storage and chose UTC, that weekday/weekend presets were added, or that a scheduling bug was caused by computing from `Date()` instead of `scheduledDate`.

- **[Recall transcript](examples/recall-transcript.md)** (~18K tokens) — What Recall produces. Every user message verbatim, every assistant response, every tool call summarized. The full conversation arc with decisions, bugs, fixes, and rationale.

## How It Works — Two Modes

Recall covers both ways people use Claude Code:

### With auto-compaction (default)

This is the "set it and forget it" mode. You don't change anything about how you work. When auto-compaction triggers — or when you manually run `/compact` — Recall automatically:

1. Parses the full session transcript before compaction
2. Writes the result to `.claude/recall-context.md`
3. After compaction, Claude re-reads CLAUDE.md which pulls in the recall content via `@`-reference
4. Cleans up the file on next session start (prevents stale content)

**You do nothing.** Claude prints a stats line and continues where it left off.

### Without auto-compaction (power mode)

This is the mode Recall was designed for. Turn off auto-compaction in Claude Code settings and use **100% of your 200K context window** — no more leaving the last 15% unused out of fear that compaction will erase your progress.

When the context fills up, Claude Code exits and prints your session ID:

```
Session ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Start a new session and restore the full context:

```
/recall a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

The session ID is printed right above where your new `claude` session starts — just copy it. Within seconds, Claude has the full conversation history and continues exactly where you left off. Technically a new session, but with all the context that matters.

This also works for:
- **Resuming after a rate limit** — don't lose context when you hit the 5-hour window
- **Continuing yesterday's work** — pick up exactly where you left off
- **Briefing yourself** — quickly review what happened in a long session

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

## Condensation (for large sessions)

When the parsed transcript exceeds 20K tokens, `condense-tail.py` splits it:

| Part | Size | Treatment |
|------|------|-----------|
| Recent exchanges | ~15K tokens | Kept verbatim (most recent context matters most) |
| Older context | Up to 85K tokens | Summarized by a single `claude -p --model sonnet` call (~30-40s) |

The result targets 15-20K tokens (~10% of Claude Code's 200K context window). For shorter sessions (<20K tokens), the full transcript is kept as-is with no API call.

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
