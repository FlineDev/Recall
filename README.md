# Recall

**Get the most out of Claude Code's 200K context window** — without paying for the 1M token tier.

Claude Code's 200K context sounds like a lot, but ~20-25% goes to system overhead (tools, prompts, CLAUDE.md), and auto-compaction triggers at ~85%. That leaves roughly 120-130K usable tokens — and the 1M tier isn't 5x more, it's effectively **~8x** the usable context (since overhead is fixed). Recall bridges this gap by making the 200K window renewable: when context runs out, start a new session and restore everything that matters in seconds.

Without Recall, compaction compresses your entire conversation into a ~3,500-token summary — less than 1% of your original context. Recall restores **4-5x more detail** (15-18K tokens), giving Claude the full conversation arc to continue where you left off.

## Why Recall Exists

Claude Code's built-in compaction summary preserves the topic, but loses the details that matter:

| Lost after compaction | Why it matters |
|---|---|
| Exact user instructions | Claude re-asks questions you already answered |
| Failed approaches & why they failed | Claude retries things that didn't work |
| Architecture decisions & rationale | Claude makes different choices than what you agreed on |
| Intermediate debugging steps | Bugs get re-investigated from scratch |
| File edit history & frequency | Claude doesn't know which files it already changed |
| Code review feedback & corrections | Your preferences are forgotten |

### What Recall preserves

Recall parses the **complete session transcript** — including context from before any previous compactions in the same session. Even after multiple compactions, nothing is permanently lost. 99%+ of noise is stripped (tool results, thinking blocks, system reminders) while keeping:

- Every user message — verbatim
- Every assistant response — verbatim
- Tool call summaries — which tools were called with what parameters
- Compaction markers — so you can see where context was previously lost
- Loaded skills — so they can be re-loaded after compaction

### See the difference

Both examples below show the same fictional session — adding recurring tasks to a Swift app:

- **[Compaction summary](examples/compaction-summary.md)** (~3,500 tokens) — What Claude Code produces by default. Preserves the topic and key files, but not the details: that you debated UTC vs. local-time storage and chose UTC, that weekday/weekend presets were added, or that a scheduling bug was caused by computing from `Date()` instead of `scheduledDate`.

- **[Recall transcript](examples/recall-transcript.md)** (~15,000 tokens) — What Recall produces. Every user message verbatim, every assistant response, every tool call summarized. The full conversation arc with decisions, bugs, fixes, and rationale.

## Installation

### Step 1: Install the plugin

Start Claude Code, then run:

```
/plugin marketplace add FlineDev/Marketplace
```

```
/plugin install recall
```

If you're in an active session, run `/reload-plugins` to activate immediately.

The plugin installs at user scope (available in all projects). It registers two hooks automatically (PreCompact + SessionStart).

### Automatic Updates (Optional, Recommended)

By default, third-party plugins don't auto-update. To receive new features and fixes automatically:

1. Type `/plugin` and press Enter
2. Switch to the **Marketplaces** tab
3. Navigate to **FlineDev** and press Enter
4. Press Enter on **Enable auto-update** (it flips to "Disable auto-update" when enabled)

With this enabled, Claude Code checks for plugin updates on startup and notifies you when a new version is available.

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

### Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (v2.0.76+ recommended)
- Python 3 (pre-installed on macOS)

<details>
<summary>Alternative: Manual setup (without plugin system)</summary>

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

## Usage

Recall covers both ways people use Claude Code:

### With auto-compaction (default)

This is the "set it and forget it" mode. You don't change anything about how you work. When auto-compaction triggers — or when you manually run `/compact` — Recall kicks in automatically.

**You do nothing.** Claude gets both its built-in compaction summary (~3,500 tokens) *and* Recall's detailed transcript (15-18K tokens) — 4-5x more context than compaction alone. Claude prints a stats line and continues where it left off:

```
Recall loaded: ~16,440 tokens (25% verbatim, 72% summarized)
Full transcript: recall-943494ae.md
```

### Without auto-compaction (power mode)

This is the mode Recall was designed for. Turn off auto-compaction in Claude Code settings and use **100% of your 200K context window** — no more leaving the last 15% unused out of fear that compaction will erase your progress.

When the context fills up, Claude Code exits and prints your session ID:

```
Resume this session with:
claude --resume a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Instead of `--resume` (which just replays the compressed summary), start a fresh session and use Recall:

```
/recall a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

The session ID is printed right above where your new `claude` session starts — just copy it. Within seconds, Claude has the full conversation history and continues exactly where you left off. Technically a new session, but with all the context that matters.

In power mode you benefit even more: there's no compaction summary at all, so Claude's only context is Recall's 15-18K token transcript — every token spent on detail, none wasted on a lossy summary. The output is always capped below 20K tokens, using only ~10% of your fresh context window.

## How It Works

### Transcript Parsing

Recall hooks into Claude Code's lifecycle via a **PreCompact hook** that fires before every compaction (auto or manual). It reads the raw JSONL session transcript — the complete, append-only log that Claude Code maintains at `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. This means Recall always has access to the **full session history**, even after multiple compactions in the same session.

The parser strips 99% of noise (tool result contents, thinking blocks, system reminders, progress events) and produces a structured markdown transcript. The result is written to both `/tmp/recall-<session-id>.md` (persistent reference) and `.claude/recall-context.md` (for automatic injection via CLAUDE.md `@`-reference).

A **SessionStart hook** cleans up `.claude/recall-context.md` on every new session start, preventing stale content from leaking into the next session.

### Condensation (for large sessions)

When the parsed transcript exceeds 20K tokens, `condense-tail.py` splits it:

| Part | Size | Treatment |
|------|------|-----------|
| Recent exchanges | ~15K tokens | Kept verbatim (most recent context matters most) |
| Older context | Up to 85K tokens | Summarized by a single `claude -p --model sonnet` call (~30-40s) |

The result is always between 15-18K tokens on average, capped below 20K (~10% of Claude Code's 200K context window). For shorter sessions (<20K tokens), the full transcript is kept as-is with no API call. The Sonnet call uses your existing Claude Code authentication — no additional API keys needed.

### Where Files Live

- **Raw transcripts:** `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` — Claude Code's append-only session log
- **Recall output:** `/tmp/recall-<session-id>.md` — persists until reboot, useful for manual `/recall` across sessions
- **Auto-injection:** `.claude/recall-context.md` — written by PreCompact, read via CLAUDE.md `@`-reference, cleaned by SessionStart
