---
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# Recall Setup

You are configuring the Recall plugin for the current project. This sets up automatic context recovery after compaction. Follow these steps exactly:

## Step 1: Ensure .claude directory exists

```bash
mkdir -p "$(pwd)/.claude"
```

## Step 2: Create the recall context file

Create `.claude/recall-context.md` with an empty placeholder. This file is populated by the PreCompact hook and read via CLAUDE.md `@`-reference:

```bash
echo '<!-- No recall context available. This file is populated by the PreCompact hook. -->' > "$(pwd)/.claude/recall-context.md"
```

## Step 3: Add @-reference to CLAUDE.md

Read the project's `CLAUDE.md` file (create it if it doesn't exist). Add `@.claude/recall-context.md` as the **very first line** of the file — before any other content. This ensures the recall content is loaded even if CLAUDE.md is long.

**If CLAUDE.md doesn't exist**, create it with:

```
@.claude/recall-context.md
```

**If CLAUDE.md already exists**, check if it already contains `@.claude/recall-context.md` (on any line). If not, prepend it as the first line. If it's already there, don't add it again.

## Step 4: Add to .gitignore

Read the project's `.gitignore` file (create it if it doesn't exist). Add `.claude/recall-context.md` if it's not already present. This prevents the auto-generated recall file from being committed.

Append this line (if not already present):

```
.claude/recall-context.md
```

## Step 5: Confirm

Tell the user:

**Recall is configured for this project.** Here's what happens now:

- **Automatic recovery**: When compaction happens (auto or via `/compact`), Recall parses the full conversation transcript and loads it back into context via the `@.claude/recall-context.md` reference. You'll see a status line like:
  ```
  Recall loaded: ~17K tokens (54% verbatim, 46% summarized)
  ```
- **Manual recall**: Run `/recall <session-id>` in any new session to load a previous session's transcript. The session ID is printed when you exit Claude Code.
- **Nothing else to configure.** The hooks (PreCompact + SessionStart) are registered automatically by the plugin system. The `.claude/recall-context.md` file is auto-generated, auto-cleaned, and gitignored.

**Tip:** To test it right now, run `/compact` — you should see the Recall status line appear after compaction completes.
