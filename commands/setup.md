---
allowed-tools:
  - Bash
  - Read
  - Edit
  - Write
---

# Recall Setup

You are configuring the Recall plugin for the current project. This sets up automatic context recovery after compaction. Follow these steps exactly:

## Step 0: Resolve script paths

The "Base directory for this skill" is provided above in the skill/command metadata. The scripts live at `<BASE_DIRECTORY>/../recall/scripts/`. Resolve the absolute path once:

```bash
RECALL_SCRIPTS="$(cd "<BASE_DIRECTORY>/../recall/scripts" && pwd)"
echo "$RECALL_SCRIPTS"
```

Store this path — you'll need it in Step 5.

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

## Step 5: Add hooks to project settings

Read `.claude/settings.json` (create it with `{}` if it doesn't exist). Add the Recall hooks to the `hooks` key. Use the absolute path from Step 0.

**If a `hooks` key already exists**, merge the Recall hooks into it. Do NOT overwrite existing hooks for other events. If `PreCompact` or `SessionStart` arrays already exist with Recall entries (check if the command path contains `recall`), replace them. Otherwise append.

**If no `hooks` key exists**, add it.

The hooks to add (replace `RECALL_SCRIPTS` with the resolved absolute path):

```json
{
  "hooks": {
    "PreCompact": [
      {
        "matcher": "auto|manual",
        "hooks": [
          {
            "type": "command",
            "command": "RECALL_SCRIPTS/pre-compact.sh",
            "timeout": 300
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "compact",
        "hooks": [
          {
            "type": "command",
            "command": "RECALL_SCRIPTS/post-compact.sh"
          }
        ]
      },
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "RECALL_SCRIPTS/session-start.sh"
          }
        ]
      }
    ]
  }
}
```

**Important:** Preserve all other keys in settings.json (permissions, mcpServers, etc.). Only touch the `hooks` key.

## Step 6: Confirm

Tell the user:

**Recall is configured.** Recovery after compaction is now automatic. Run `/compact` to test it, or use `/recall <session-id>` to load a previous session.
