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

- Recall has been configured for this project.
- **Automatic recovery**: After compaction, the full conversation transcript is automatically loaded via the `@.claude/recall-context.md` reference in CLAUDE.md. Claude will print a status line like "Recall loaded: ~17K tokens (54% verbatim, 46% summarized)" to confirm.
- **Manual recall**: Run `/recall <session-id>` in any session to load a previous session's transcript.
- The `.claude/recall-context.md` file has been added to `.gitignore` — it's auto-generated and auto-cleaned, so it should never be committed.
- No further configuration needed. The hooks (PreCompact + SessionStart) are registered automatically by the plugin system.
