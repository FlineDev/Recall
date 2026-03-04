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

This is the primary, "set it and forget it" mode. A `SessionStart` hook fires after every compaction, automatically:

1. Parses the full session transcript
2. Generates a detailed context file
3. Tells Claude to read it immediately

**You do nothing.** Claude seamlessly continues your work with full context — no repeated explanations, no lost decisions. If the transcript is very large (>25K tokens), an adaptive summarization pipeline automatically compresses the largest messages while preserving the most recent exchange verbatim.

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

### Manual

```
/plugin install https://github.com/FlineDev/Recall.git
```

## Setup

After installation, you need to configure the **compaction hook** for Use Case 1 (automatic recovery). Without it, only the manual `/recall <id>` command works.

Add this to your project's `.claude/settings.json` or global `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "compact",
        "hooks": [
          {
            "type": "command",
            "command": "<plugin-path>/scripts/post-compact-hook.sh"
          }
        ]
      }
    ]
  }
}
```

Replace `<plugin-path>` with the absolute path to the installed plugin. To find it:

```bash
# The plugin is typically installed at:
ls ~/.claude/plugins/recall/
```

The hook script uses `SCRIPT_DIR` relative to itself, so it finds all other scripts automatically.

### What the Hook Does

1. Receives the `session_id` from Claude Code via stdin (reliable even with parallel sessions)
2. Runs the parser on the current session's transcript
3. Outputs a message telling Claude to read the detailed context file
4. If the file exceeds 25K tokens, instructs Claude to run adaptive summarization first

## How It Works

### The Pipeline

Recall uses a 3-script pipeline:

| Script | Purpose |
|--------|---------|
| `parse-transcript.py` | Parses the JSONL transcript into structured markdown |
| `extract-longest.py` | Identifies large messages for summarization (only for >25K token transcripts) |
| `apply-summaries.py` | Patches summarized messages back into the transcript |

### What's Preserved vs. Stripped

| Preserved | Stripped |
|-----------|---------|
| All user messages (verbatim) | Tool result contents (large, redundant) |
| All assistant responses (verbatim) | Thinking blocks |
| Tool call summaries (name + key params) | System reminders |
| Compaction markers with token counts | Progress events |
| Loaded skills list | Compaction summaries (we keep more detail) |

### Adaptive Summarization

For very long sessions (>25K tokens after initial compression), Recall uses an iterative partitioning algorithm:

1. **Freeze** the last exchange (most recent user message + response) — always kept verbatim
2. **Calculate** the remaining token budget (target: 15K tokens total)
3. **Partition** messages iteratively: freeze short messages (below average), keep large ones as candidates
4. **Summarize** candidates using a Haiku subagent with proportional word targets
5. **Patch** the summaries back into the transcript

This ensures the most recent context is always complete while compressing older, larger messages proportionally.

## Requirements

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- Python 3 (pre-installed on macOS)

## Technical Details

- **Transcript location:** `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`
- **Output location:** `/tmp/recall-<session-id>.md`
- **Message cap:** Sessions exceeding 100 messages (50 exchanges) are truncated to the most recent 100
- **Token estimation:** `byte_count / 2.2` — calibrated from empirical data (~2.35 bytes/token for technical markdown + code, using 2.2 to conservatively overestimate by ~7%)
- **Session ID safety:** Always passed explicitly (via user argument or hook stdin), never guessed from filesystem timestamps
