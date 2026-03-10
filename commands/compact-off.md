---
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# Disable Compaction Integration

You are removing Recall's compaction integration from the current project. Follow these steps exactly:

## Step 1: Remove hooks from project settings

Read `.claude/settings.json`. Remove all Recall-related hook entries:

- In `PreCompact`: remove any entry where the command path contains `recall`
- In `SessionStart`: remove any entries where the command path contains `recall`
- If `PreCompact` or `SessionStart` arrays become empty after removal, remove the entire key
- If the `hooks` object becomes empty, remove it entirely

**Important:** Preserve all other keys and non-Recall hooks.

## Step 2: Remove @-reference from CLAUDE.md

Read `CLAUDE.md`. Remove the line `@.claude/recall-context.md` if present. Do not remove any other lines.

## Step 3: Delete the recall context file

```bash
rm -f "$(pwd)/.claude/recall-context.md"
```

## Step 4: Remove from .gitignore

Read `.gitignore`. Remove the line `.claude/recall-context.md` if present. Do not remove any other lines. If `.gitignore` becomes empty, delete it.

## Step 5: Confirm

Tell the user:

**Compaction integration disabled.** Recall hooks have been removed from this project. You can still use `/recall:session <session-id>` manually in any session. To re-enable, run `/recall:compact-on`.
