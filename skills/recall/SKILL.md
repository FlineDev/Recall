---
name: recall
description: "Recall a previous session with full context from its transcript. Use when user provides a session ID to continue work from a previous chat, or automatically after compaction to restore lost detail."
metadata:
  keywords: "recall, session, resume, continue, transcript, context, compaction, restore"
argument-hint: "<session-id>"
---

# Recall

Recall a previous Claude Code session with much richer context than auto-compaction provides. Keeps ALL user messages and assistant responses verbatim while achieving 99%+ compression.

## Background

Two hooks handle automatic recovery (no action needed):
- **PreCompact** parses the transcript and writes to `.claude/recall-context.md`
- **SessionStart** cleans up the recall file to prevent stale content

This skill handles **manual recall** — when the user runs `/recall <session-id>` in a new session.

## Execution Steps

### Step 1: Parse the transcript

The "Base directory for this skill" is provided above in the skill metadata. Use it directly:

```bash
python3 <BASE_DIRECTORY>/scripts/parse-transcript.py <SESSION_ID> --cwd "$(pwd)" > /tmp/recall-<SESSION_ID>.md 2>/dev/null
```

Replace `<SESSION_ID>` with the value from `{{args}}`.

### Step 2: Condense if needed

```bash
python3 <BASE_DIRECTORY>/scripts/condense-tail.py split /tmp/recall-<SESSION_ID>.md <SESSION_ID>
```

- **Exit code 2:** Transcript is ≤20K tokens — no condensation needed. Skip to Step 3.
- **Exit code 0:** Condensation needed. Three files were created:
  - `/tmp/recall-older-<SID_PREFIX>.md` — older context that needs summarizing
  - `/tmp/recall-tail-<SID_PREFIX>.md` — recent exchanges (kept verbatim)
  - `/tmp/recall-prompt-<SID_PREFIX>.txt` — summarization prompt

  Where `<SID_PREFIX>` is the first 8 characters of the session ID.

  **Summarize with a subagent:** Launch an Agent (subagent_type: "general-purpose", model: sonnet) with a fresh context. Pass the following prompt to the subagent:

  > Read the file `/tmp/recall-older-<SID_PREFIX>.md` in full. If the file is too large for a single Read call (over 2000 lines), use multiple Read calls with offset/limit to read it completely — do NOT skip any part. You must have the entire file in context before summarizing.
  >
  > Once you have read the full file, summarize it following these instructions:
  >
  > Summarize this older portion of a Claude Code conversation transcript. The recent conversation is preserved verbatim elsewhere — focus only on the earlier context here. Your summary will be injected into a future Claude session to restore lost context after compaction. Write for an AI reader who needs to continue the work seamlessly.
  >
  > PRIORITIES (in order):
  > 1. User's intentions and goals — the "why" behind each request
  > 2. Decisions and their rationale — especially alternatives that were considered and rejected
  > 3. File paths modified, created, or deleted — exact paths matter
  > 4. Problems encountered and solutions — especially bugs and their root causes
  > 5. Architectural patterns established — naming conventions, key abstractions, data flow
  > 6. User preferences and constraints stated during the conversation
  > 7. Current state — what's done, what's in progress, what's blocked
  >
  > SKIP OR MINIMIZE:
  > - File contents (just note path + purpose)
  > - Tool output details (just note outcomes)
  > - Reads that didn't lead to action
  >
  > FORMAT: Chronological narrative with bold paths and bullet lists. Start with a one-line session overview. End with precise state description.
  >
  > LENGTH: Be thorough but not verbose. Capture every important decision and file change without reproducing conversations verbatim. Think of it as detailed meeting notes — nothing critical missing, nothing unnecessary included.
  >
  > Write your summary to `/tmp/recall-summary-<SID_PREFIX>.md`. Do NOT output the summary as text — only write it to the file.

  **Important:** Do NOT read the older context file in the main conversation — it can be up to 85K tokens and would fill the context window, defeating the purpose of summarization. The subagent handles this in its own isolated 200K context (85K fits comfortably).

  After the subagent finishes, combine the results:

  ```bash
  python3 <BASE_DIRECTORY>/scripts/condense-tail.py combine /tmp/recall-<SESSION_ID>.md <SESSION_ID>
  ```

### Step 3: Read and analyze the transcript

Read `/tmp/recall-<SESSION_ID>.md` — this is the final condensed transcript. From the full conversation history, understand:

1. **The conversation arc** — What topics were discussed? What was the user's main goal?
2. **The last unanswered question** — The session likely ended due to rate limit, context limit, or manual exit. What was pending?
3. **Which files matter right now** — What work is still in progress vs. already completed?

### Step 4: Re-read relevant files

Based on the transcript, re-read files needed to continue the pending work. Think about what a developer would need open in their editor.

**Re-read:**
- Code files actively being worked on (edited but not yet finished)
- Configuration or data files needed for the pending task
- Skills from the `## Skills Loaded` section — re-load with `/skillname` if they provided domain-specific context

**Skip:**
- Files read once for completed tasks
- Files already in context (CLAUDE.md, AGENTS.md load automatically)
- Subagent results (summarized in assistant messages)
- Plan files from `~/.claude/plans/` (content is in assistant messages)

### Step 5: Present summary

```
## Session Resumed: <brief topic>

### What we were working on
<1-3 sentences about the main task/goal>

### What was accomplished
<Bullet list of completed work>

### Pending / Next steps
<Depends on how the previous session ended:>
<- If the session was interrupted mid-task (rate limit, context limit, crash): Describe what was in progress and offer to continue, e.g. "Shall I continue with [specific task]?">
<- If the session ended naturally (user's last request was fulfilled): Describe what the last exchange was about and what logical next steps might be, e.g. "We finished X. Next up could be Y or Z.">
<- If unclear: State the last user message and assistant response so the user knows exactly where things stand.>

### Context loaded
<List of files re-read and why each was needed>

### Files skipped
<Brief list of files from the session that were NOT re-read, so user can correct if needed>
```

## Technical Details

- **Transcript location:** `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`
- **Preserved:** ALL user messages verbatim, ALL assistant text responses verbatim, tool call summaries (name + key params), compaction markers
- **Stripped:** Compaction summaries, system reminders, tool result contents, thinking blocks, progress events
- **Adaptive condensation:** If output exceeds 20K tokens, recent ~15K tokens kept verbatim, older context summarized by subagent. Output targets 15-20K tokens.
- **Token estimation:** Byte count / 3.0
