# Recall

**Keep the full conversation when starting a new Claude Code session.**

Claude Code's built-in compaction has improved a lot over time — it captures the main topics, key decisions, and important files. But a summary is still a summary. It can't preserve every detail from a long session: the exact wording of your instructions, the specific approaches that were tried and rejected, or the subtle preferences you expressed along the way. Sometimes these are exactly the details that matter when continuing the work.

Recall takes a different approach: instead of summarizing, it preserves your actual conversation — every user message and every assistant response in full. Only the noise is stripped (tool result contents, thinking blocks, system reminders). The result is a ~15-20K token transcript that fits comfortably into a fresh 200K context window, giving Claude the full conversation arc to pick up where you left off.

## Why Recall Exists

Claude Code's compaction does a reasonable job of preserving what was discussed, but any summary will lose some detail. The longer and more nuanced the session, the more gets compressed away:

| What a summary may lose | Why it can matter |
|---|---|
| Exact phrasing of user instructions | Claude may interpret your intent slightly differently |
| Failed approaches & why they were abandoned | Claude might revisit something you already ruled out |
| Nuanced architecture decisions | The rationale behind a choice gets flattened |
| Intermediate debugging context | A related issue may need that context later |
| File edit patterns & frequency | Less awareness of what was already changed |
| Specific feedback & corrections | Your preferences may not carry over fully |

None of this means compaction is bad — it works well for many sessions. But when you need the full context, a summary isn't enough.

### What Recall preserves

Recall parses the **complete session transcript** — including context from before any previous compactions in the same session. 99%+ of noise is stripped while keeping:

- Every user message — verbatim
- Every assistant response — verbatim
- Tool call summaries — which tools were called with what parameters
- Compaction markers — so you can see where context was previously compressed
- Loaded skills — so they can be re-loaded after compaction

Recall is most valuable when starting a fresh session to continue complex work — whether after compaction, after hitting a rate limit, or when resuming the next day.

### See the difference

Both examples below show the same fictional session — adding recurring tasks to a Swift app:

- **[Compaction summary](examples/compaction-summary.md)** (~3,500 tokens) — Claude Code's built-in summary. Captures the topic and key files well, but compresses details like the UTC vs. local-time debate, the weekday/weekend preset additions, and a scheduling bug caused by computing from `Date()` instead of `scheduledDate`.

- **[Recall transcript](examples/recall-transcript.md)** (~15,000 tokens) — What Recall produces. Every user message verbatim, every assistant response, every tool call summarized. The full conversation with all decisions, bugs, fixes, and rationale intact.

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
/recall:init
```

This does four things:
1. Creates `.claude/recall-context.md` (auto-populated by the hook)
2. Adds `@.claude/recall-context.md` as the first line of your `CLAUDE.md`
3. Adds `.claude/recall-context.md` to `.gitignore`
4. Adds the Recall hooks to `.claude/settings.json`

**That's it.** Compaction recovery is now automatic. You'll never need to think about it again.

### Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (v2.0.76+ recommended)
- Python 3 (pre-installed on macOS)

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

This is the mode Recall was designed for. Turn off auto-compaction via `/config` and use **100% of your 200K context window** — no more leaving the last 15% unused out of fear that compaction will erase your progress.

When the context fills up, you run `/exit` and Claude Code prints your session ID:

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
| Older context | Up to 85K tokens | Summarized by Sonnet (automatic: `claude -p` call, manual `/recall`: subagent) |

The result is always between 15-18K tokens on average, capped below 20K (~10% of Claude Code's 200K context window). For shorter sessions (<20K tokens), the full transcript is kept as-is with no summarization call.

### Where Files Live

- **Raw transcripts:** `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` — Claude Code's append-only session log
- **Recall output:** `/tmp/recall-<session-id>.md` — persists until reboot, useful for manual `/recall` across sessions
- **Auto-injection:** `.claude/recall-context.md` — written by PreCompact, read via CLAUDE.md `@`-reference, cleaned by SessionStart
