# 🧠 Recall

**Get the most out of Claude Code's 200K context window** — without paying for the 1M token tier.

Claude Code's 200K context sounds like a lot, but ~20-25% goes to system overhead (tools, prompts, CLAUDE.md), and auto-compaction triggers at ~85%. That leaves roughly 120-130K usable tokens — and the 1M tier isn't 5x more, it's effectively **~8x** the usable context (since overhead is fixed).

> Recall bridges this gap by making the 200K window renewable: when context runs out, start a new session and restore everything that matters in seconds.

Without Recall, compaction compresses your entire conversation into a summary. Recall preserves **far more detail** (15-18K tokens of actual conversation), giving Claude the full conversation arc to continue where you left off.

## Why Recall Exists

Claude Code's built-in compaction has gotten better over time — it captures the main topics, key decisions, and important files. But a summary is inherently lossy. The longer and more nuanced the session, the more detail gets compressed away:

| What a summary loses | Why it matters |
|---|---|
| Exact phrasing of user instructions | Claude may interpret your intent differently than you stated it |
| Failed approaches & why they were abandoned | Claude might revisit something you already ruled out |
| Architecture decisions & rationale | The reasoning behind a choice gets flattened into just the outcome |
| Intermediate debugging steps | A related issue later may need that exact context |
| File edit history & frequency | Claude loses track of what it already changed and how often |
| Code review feedback & corrections | Your specific preferences don't carry over |

Recall keeps the actual conversation instead of a summary — every user message, every assistant response, every tool call. A summary can never fully replace the real thing, and when you're deep in complex work, the details matter.

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

If you're in an active session, run `/reload-plugins` to activate immediately. Recall is part of the [FlineDev Marketplace](https://github.com/FlineDev/Marketplace) — see the full list of available plugins there.

> [!TIP]
> **Automatic Updates:** By default, third-party plugins don't auto-update. To receive new features and fixes:
> 1. Type `/plugin` and press Enter
> 2. Switch to the **Marketplaces** tab
> 3. Navigate to **FlineDev** and press Enter
> 4. Press Enter on **Enable auto-update**

### Step 2: Start using Recall

After installation, `/recall:session` works immediately — no per-project setup needed:

```
/recall:session <session-id>
```

Start a new session, paste the session ID from a previous chat, and Recall restores the full conversation context. That's it.

### Optional: Automatic compaction integration

If you want Recall to **automatically** kick in whenever compaction happens (auto or manual `/compact`), run this once per project:

```
/recall:compact-on
```

This hooks Recall into the compaction lifecycle so recovery happens without you having to do anything. To remove the integration later, run `/recall:compact-off`.

### Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (v2.0.76+ recommended)
- Python 3 (pre-installed on macOS)

## Usage

Recall covers both ways people use Claude Code:

### With auto-compaction (default)

This is the "set it and forget it" mode. You don't change anything about how you work. When auto-compaction triggers — or when you manually run `/compact` — Recall kicks in automatically.

**You do nothing.** Claude gets both its built-in compaction summary *and* Recall's detailed transcript (15-18K tokens) — far more context than compaction alone. If everything works ideally, Claude prints a stats line like:

```
Recall loaded: ~16,440 tokens (25% verbatim, 72% summarized)
Full transcript: recall-943494ae.md
```

Claude doesn't always print this — but don't worry, Recall still did its job. You'll notice the PreCompact hook running before compaction happens, which is where Recall parses and injects the transcript. The full conversation context is there even if Claude doesn't explicitly acknowledge it.

### Without auto-compaction (power mode)

This is the mode Recall was designed for. Turn off auto-compaction via `/config` and use **100% of your 200K context window** — no more leaving the last 15% unused out of fear that compaction will erase your progress.

When the context fills up, you run `/exit` and Claude Code prints your session ID:

```
Resume this session with:
claude --resume a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

Instead of `--resume` (which just replays the compressed summary), start a fresh session and use Recall:

```
/recall:session a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

The session ID is printed right above where your new `claude` session starts — just copy it. Within seconds, Claude has the full conversation history and continues exactly where you left off. Technically a new session, but with all the context that matters.

In power mode you benefit even more: there's no compaction summary at all, so Claude's only context is Recall's 15-18K token transcript — every token spent on detail, none wasted on a lossy summary. The output is always capped below 20K tokens, using only ~10% of your fresh context window.

## How It Works

### The Pipeline

```
┌────────────────────────┐     ┌────────────────────────┐     ┌────────────────────────┐
│  1. Parse              │     │  2. Condense           │     │  3. Inject             │
│                        │────▶│     (if needed)        │────▶│                        │
│  parse-transcript.py   │     │  condense-tail.py      │     │  pre-compact.sh        │
│                        │     │                        │     │  post-compact.sh       │
│  Reads raw JSONL       │     │  >20K tokens?          │     │  session-start.sh      │
│  Strips 99% noise      │     │  Split + summarize     │     │                        │
│  Keeps all messages    │     │  older context         │     │  Writes to project     │
│  verbatim              │     │  ≤20K? Keep as-is      │     │  + cleans up           │
└────────────────────────┘     └────────────────────────┘     └────────────────────────┘
```

### Step 1: Parse ([`parse-transcript.py`](skills/session/scripts/parse-transcript.py))

Reads the raw JSONL session transcript — the complete, append-only log that Claude Code maintains at `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`. This means Recall always has access to the **full session history**, even after multiple compactions in the same session.

The parser strips 99% of noise (tool result contents, thinking blocks, system reminders, progress events) and produces a structured markdown transcript with every user message and assistant response verbatim, plus summarized tool calls.

### Step 2: Condense ([`condense-tail.py`](skills/session/scripts/condense-tail.py))

If the parsed transcript exceeds 20K tokens, it gets split:

| Part | Size | Treatment |
|------|------|-----------|
| Recent exchanges | ~15K tokens | Kept verbatim (most recent context matters most) |
| Older context | Up to 85K tokens | Summarized by Sonnet (automatic: `claude -p` call, manual `/recall`: subagent) |

The result is always between 15-18K tokens on average, capped below 20K (~10% of Claude Code's 200K context window). For shorter sessions (<20K tokens), the full transcript is kept as-is with no summarization call.

### Step 3: Inject (hooks)

Three shell scripts handle the lifecycle:

- **[`pre-compact.sh`](skills/session/scripts/pre-compact.sh)** — Runs before compaction. Orchestrates the parse + condense pipeline and writes the result to both `/tmp/recall-<session-id>.md` (persistent) and `.claude/recall-context.md` (for automatic injection via CLAUDE.md `@`-reference).
- **[`post-compact.sh`](skills/session/scripts/post-compact.sh)** — Runs after compaction. Outputs a short reminder to Claude to act on the loaded recall transcript.
- **[`session-start.sh`](skills/session/scripts/session-start.sh)** — Runs on every session start. Cleans up `.claude/recall-context.md` to prevent stale content from leaking into new sessions or parallel sessions.

### Where Files Live

| File | Path | Purpose |
|------|------|---------|
| Raw transcripts | `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl` | Claude Code's append-only session log |
| Recall output | `/tmp/recall-<session-id>.md` | Persists until reboot, useful for manual `/recall` across sessions |
| Auto-injection | `.claude/recall-context.md` | Written by pre-compact, read via CLAUDE.md `@`-reference, cleaned by session-start |
