---
name: recall
description: "Recall a previous session with full context from its transcript. Use when user provides a session ID to continue work from a previous chat, or automatically after compaction to restore lost detail."
metadata:
  keywords: "recall, session, resume, continue, transcript, context, compaction, restore"
argument-hint: "<session-id>"
---

# Recall

Recall a previous Claude Code session with much richer context than auto-compaction provides. Keeps ALL user messages and assistant responses verbatim while achieving 99%+ compression.

## Two Use Cases

### Use Case 1: New Session (manual)

When exiting Claude Code, the session ID is printed. User copies it, starts a new session, runs `/recall <id>`.

### Use Case 2: After Compaction (automatic via hook)

A `SessionStart` hook with `compact` matcher fires after every compaction. It runs the parser automatically and tells Claude to read the detailed transcript. See **Hook Setup** below.

## Execution Steps

### Step 1: Run the parser

**If the user provided a session ID** (Use Case 1):

The "Base directory for this skill" is provided above in the skill metadata. Use it directly — symlinks are followed automatically, no need for `readlink` or `find`:

```bash
python3 <BASE_DIRECTORY>/scripts/parse-transcript.py <SESSION_ID> --cwd "$(pwd)" > /tmp/recall-<SESSION_ID>.md 2>/dev/null
```

Replace `<SESSION_ID>` with the value from `{{args}}`.

**If triggered by the post-compact hook** (Use Case 2):

The hook already ran the parser and told you the file path.

### Step 1b: Summarize if needed (large sessions only)

Check if the output file ends with a `=== NEEDS SUMMARIZATION ===` section (read the last 40 lines using the Read tool with an offset). If this section exists, the file exceeds 25K tokens and can't be read in one go.

**Follow the instructions in that section:** Launch a **Haiku subagent** with the prompt provided there (replace `{FILE_PATH}` placeholders with the actual file path). The subagent will:
1. Run `extract-longest.py` to identify messages needing summarization
2. Read/summarize/write entry files in batches of 5
3. Run `apply-summaries.py` to patch the transcript

After the subagent finishes, the file will be small enough to read in full. If no `=== NEEDS SUMMARIZATION ===` section exists, the file is already small enough — read it directly in one single read.

**Fallback — if the Read tool rejects the file as too large:** Read the file in chunks of 500 lines (using `offset` and `limit` parameters) until you've read the entire file. Do NOT skip the file or fall back to the compaction summary — the recall transcript is always more detailed.

### Step 2: Analyze the condensed transcript

Read the full output carefully. From the complete conversation history (all user messages, assistant responses, and tool call summaries), understand:

1. **The conversation arc** — What topics were discussed? What was the user's main goal?
2. **The last unanswered question** — The session likely ended due to rate limit, context limit, or manual exit. What was pending?
3. **Which files matter right now** — Use your judgment based on the full conversation, not mechanical heuristics. Consider:
   - What work is still in progress vs. already completed?
   - Which files were central to the ongoing task vs. read once for reference?
   - What context do you need to continue the pending work intelligently?

### Step 3: Re-read relevant files

**Use your judgment.** Based on your understanding of the full conversation, re-read files that you need in order to continue the pending work. Think about what a developer would need open in their editor to pick up where they left off.

**Typical candidates for re-reading:**
- Code files that are actively being worked on (edited but work not yet finished)
- Configuration or data files needed for the pending task
- Documentation files that provide essential context — but ONLY if NOT already loaded by CLAUDE.md / AGENTS.md (those load automatically at session start)
- **Skills from the previous session** — Check the `=== SKILLS LOADED ===` section. If any skills provided domain-specific context needed for the pending work (e.g. build tools, API workflows, coding guidelines), re-load them with `/skillname`. Skills already listed in the system-reminder don't need re-loading — they're available automatically.

**Typically skip:**
- Files that were read once for a completed task (the work is done)
- Files that are already in the current context (compaction or system may have already loaded them — check before re-reading)
- Subagent results (their findings are summarized in assistant messages in the transcript)
- Plan files from `~/.claude/plans/` (plan content is quoted in assistant messages)

**Be smart about it:** Some important files may have been read early in the session, not recently. If they're essential context for the pending work, re-read them. Conversely, recently-touched files may not need re-reading if that work is already complete.

### Step 4: Resume or present summary

**After compaction (Use Case 2):** Do NOT present a formal summary. Seamlessly continue working on the pending task. If nothing is pending, briefly summarize what was accomplished and ask the user what to do next.

**Manual recall (Use Case 1):** Present a brief summary to the user:

```
## Session Resumed: <brief topic>

### What we were working on
<1-3 sentences about the main task/goal>

### What was accomplished
<Bullet list of completed work>

### Pending / Unanswered
<What the user last asked that wasn't addressed>

### Context loaded
<List of files re-read and why each was needed>

### Files skipped
<Brief list of files from the session that were NOT re-read, so user can correct if needed>
```

## Hook Setup (Recommended)

Add this to your project's `.claude/settings.json` or global `~/.claude/settings.json` to automatically generate a detailed transcript after every compaction:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "compact",
        "hooks": [
          {
            "type": "command",
            "command": "<absolute-path-to>/recall/scripts/post-compact-hook.sh"
          }
        ]
      }
    ]
  }
}
```

Replace `<absolute-path-to>` with the resolved path to this skill's directory (follow symlinks). The hook script uses `SCRIPT_DIR` relative to itself, so it finds `parse-transcript.py` automatically.

The hook:
1. Receives `session_id` from Claude Code via stdin (100% reliable, even with parallel sessions)
2. Runs the parser on the current session's transcript
3. Outputs a message telling Claude to read the detailed file

## Terminology

- **Entry**: A single block in the transcript (`--- USER ---`, `--- TOOLS ---`, or `--- ASSISTANT ---`)
- **Message**: Either a "user message" (1 USER entry) or a "bot message" (all TOOLS/ASSISTANT entries following a user message). The algorithm operates on messages.
- **Exchange**: 1 user message + 1 bot message = 2 messages

## Technical Details

- **Transcript location:** `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`
- **Preserved:** ALL user messages verbatim, ALL assistant text responses verbatim, tool call summaries (name + key params), compaction markers with token counts
- **Stripped:** Compaction summaries (redundant — we keep more detail), system reminders, tool result contents, thinking blocks, progress events
- **Message cap:** Sessions exceeding 100 messages (50 exchanges) are truncated to the most recent 100 messages
- **Adaptive summarization:** If output exceeds 25K tokens, a `=== NEEDS SUMMARIZATION ===` section is appended with a Haiku subagent prompt. The iterative partitioning algorithm freezes the last exchange and short messages, then selects large messages for summarization with proportional `target_words` guidance. Bot messages in the frozen tail exceeding 3K tokens are also summarized (to ~1.5K).
- **Token estimation:** Byte count / 2.2 (calibrated from empirical data: ~2.35 bytes/token for technical markdown + code, using 2.2 to conservatively overestimate by ~7%)
- **Session ID safety:** Always passed explicitly (via user argument or hook stdin). Never guessed from filesystem timestamps.
