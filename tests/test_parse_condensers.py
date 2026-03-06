"""Tests for condense_skill_injection(), condense_plan_injection(), and parse_task_notification()."""

import pytest


# ── condense_skill_injection ─────────────────────────────────────────────────

class TestCondenseSkillInjection:
   def test_valid_skill_with_args(self, parse_mod):
      text = (
         "Base directory for this skill: /home/alex/.claude/skills/rust-helper\n"
         "\n"
         "# Rust Helper\n"
         "\n"
         "This skill provides Rust-specific optimizations and best practices.\n"
         "\n"
         "## Capabilities\n"
         "- Identify unnecessary clones and allocations\n"
         "- Suggest iterator chain optimizations\n"
         "\n"
         "ARGUMENTS: src/storage/mod.rs"
      )
      result = parse_mod.condense_skill_injection(text)
      assert result is not None
      assert "[Skill loaded: rust-helper" in result
      assert "words" in result
      assert "tokens" in result
      assert "[Skill arguments: src/storage/mod.rs]" in result

   def test_valid_skill_without_args(self, parse_mod):
      text = (
         "Base directory for this skill: /home/alex/.claude/skills/commit\n"
         "\n"
         "# Commit Helper\n"
         "\n"
         "This skill helps create good commit messages.\n"
      )
      result = parse_mod.condense_skill_injection(text)
      assert result is not None
      assert "[Skill loaded: commit" in result
      assert "Skill arguments" not in result

   def test_not_a_skill_injection(self, parse_mod):
      result = parse_mod.condense_skill_injection("Just regular user text")
      assert result is None

   def test_empty_string(self, parse_mod):
      result = parse_mod.condense_skill_injection("")
      assert result is None

   def test_word_count_and_tokens_present(self, parse_mod):
      text = (
         "Base directory for this skill: /path/to/my-skill\n"
         "\n"
         "Some content here with several words to count.\n"
         "And more content on another line.\n"
      )
      result = parse_mod.condense_skill_injection(text)
      assert result is not None
      # Verify the format includes ~N words / ~M tokens
      assert "~" in result
      assert "words" in result
      assert "tokens" in result

   def test_skill_name_from_path(self, parse_mod):
      text = (
         "Base directory for this skill: /deep/nested/path/to/awesome-skill\n"
         "\n"
         "Content here.\n"
      )
      result = parse_mod.condense_skill_injection(text)
      assert "[Skill loaded: awesome-skill" in result


# ── condense_plan_injection ──────────────────────────────────────────────────

class TestCondensePlanInjection:
   def test_valid_plan_with_files(self, parse_mod):
      text = (
         "Implement the following plan:\n"
         "\n"
         "# Task Export Feature Plan\n"
         "\n"
         "## Context\n"
         "TaskTracker needs an export command.\n"
         "\n"
         "## Steps\n"
         "1. Add Export variant\n"
         "2. Create export.rs\n"
      )
      plan_files = ["/home/alex/.claude/plans/export-plan.md"]
      result = parse_mod.condense_plan_injection(text, plan_files)
      assert result is not None
      assert '"Task Export Feature Plan"' in result
      assert "words" in result
      assert "tokens" in result
      assert "export-plan.md" in result
      assert "note: injected content may differ" in result

   def test_valid_plan_no_files(self, parse_mod):
      text = (
         "Implement the following plan:\n"
         "\n"
         "# Migration Plan\n"
         "\n"
         "Step 1: Backup\n"
         "Step 2: Migrate\n"
      )
      result = parse_mod.condense_plan_injection(text, [])
      assert result is not None
      assert '"Migration Plan"' in result
      assert "plan file" not in result

   def test_not_a_plan_injection(self, parse_mod):
      result = parse_mod.condense_plan_injection("Regular text here", [])
      assert result is None

   def test_empty_string(self, parse_mod):
      result = parse_mod.condense_plan_injection("", [])
      assert result is None

   def test_plan_without_heading(self, parse_mod):
      text = (
         "Implement the following plan:\n"
         "\n"
         "No heading here, just steps.\n"
         "1. Do thing A\n"
         "2. Do thing B\n"
      )
      result = parse_mod.condense_plan_injection(text, [])
      assert result is not None
      assert '"untitled plan"' in result

   def test_multiple_plan_files_uses_last(self, parse_mod):
      text = (
         "Implement the following plan:\n"
         "\n"
         "# Final Plan\n"
         "\n"
         "Steps...\n"
      )
      plan_files = [
         "/home/alex/.claude/plans/draft-v1.md",
         "/home/alex/.claude/plans/draft-v2.md",
         "/home/alex/.claude/plans/final.md",
      ]
      result = parse_mod.condense_plan_injection(text, plan_files)
      assert "final.md" in result
      assert "draft-v1.md" not in result


# ── parse_task_notification ──────────────────────────────────────────────────

class TestParseTaskNotification:
   def test_full_notification(self, parse_mod):
      text = (
         "<task-notification>\n"
         "<summary>Research async patterns</summary>\n"
         "<result>Found 3 patterns: select, join, spawn. "
         "Recommend spawn for I/O-bound work.</result>\n"
         "<status>completed</status>\n"
         "<task-id>task-42</task-id>\n"
         "<tool-use-id>toolu_abc123</tool-use-id>\n"
         "</task-notification>"
      )
      parsed = parse_mod.parse_task_notification(text)
      assert parsed is not None
      line, access_hint, result_words = parsed
      assert "Research async patterns" in line
      assert "completed" in line
      assert "result:" in line  # result words included
      assert "toolu_abc123" in access_hint
      assert result_words > 0

   def test_notification_without_result(self, parse_mod):
      text = (
         "<task-notification>\n"
         "<summary>Run test suite</summary>\n"
         "<status>in_progress</status>\n"
         "<task-id>task-7</task-id>\n"
         "<tool-use-id>toolu_xyz</tool-use-id>\n"
         "</task-notification>"
      )
      parsed = parse_mod.parse_task_notification(text)
      assert parsed is not None
      line, access_hint, result_words = parsed
      assert "Run test suite" in line
      assert "in_progress" in line
      assert result_words == 0
      # No "result:" in line when no result
      assert "result:" not in line

   def test_not_a_notification(self, parse_mod):
      result = parse_mod.parse_task_notification("Just normal text")
      assert result is None

   def test_empty_string(self, parse_mod):
      result = parse_mod.parse_task_notification("")
      assert result is None

   def test_notification_without_tool_use_id(self, parse_mod):
      text = (
         "<task-notification>\n"
         "<summary>Quick check</summary>\n"
         "<status>completed</status>\n"
         "</task-notification>"
      )
      parsed = parse_mod.parse_task_notification(text)
      assert parsed is not None
      line, access_hint, result_words = parsed
      assert "Quick check" in line
      # No access hint without tool-use-id
      assert access_hint == ""

   def test_notification_embedded_in_text(self, parse_mod):
      text = (
         "Some prefix text\n"
         "<task-notification>\n"
         "<summary>Embedded task</summary>\n"
         "<status>completed</status>\n"
         "<tool-use-id>toolu_embed</tool-use-id>\n"
         "</task-notification>\n"
         "Some suffix text"
      )
      parsed = parse_mod.parse_task_notification(text)
      assert parsed is not None
      line, access_hint, _ = parsed
      assert "Embedded task" in line
      assert "toolu_embed" in access_hint
