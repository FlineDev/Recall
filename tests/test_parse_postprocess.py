"""Tests for merge_consecutive_tools(), collect_skills_loaded(),
collect_file_operations(), and format_output()."""

import pytest


# ── merge_consecutive_tools ──────────────────────────────────────────────────

class TestMergeConsecutiveTools:
   def test_two_tool_only_entries_merge(self, parse_mod):
      entries = [
         {
            "role": "assistant",
            "texts": [],
            "tool_calls": [{"name": "Read", "summary": "Read: foo.rs", "file_path": "foo.rs"}],
         },
         {
            "role": "assistant",
            "texts": [],
            "tool_calls": [{"name": "Edit", "summary": "Edit: foo.rs", "file_path": "foo.rs"}],
         },
      ]
      merged = parse_mod.merge_consecutive_tools(entries)
      assert len(merged) == 1
      assert len(merged[0]["tool_calls"]) == 2

   def test_entry_with_text_stops_merging(self, parse_mod):
      entries = [
         {
            "role": "assistant",
            "texts": [],
            "tool_calls": [{"name": "Read", "summary": "Read: a.rs", "file_path": "a.rs"}],
         },
         {
            "role": "assistant",
            "texts": ["I found the issue."],
            "tool_calls": [{"name": "Edit", "summary": "Edit: a.rs", "file_path": "a.rs"}],
         },
      ]
      merged = parse_mod.merge_consecutive_tools(entries)
      assert len(merged) == 2

   def test_single_entry_unchanged(self, parse_mod):
      entries = [
         {
            "role": "assistant",
            "texts": ["Hello"],
            "tool_calls": [{"name": "Bash", "summary": "Bash: ls", "file_path": ""}],
         },
      ]
      merged = parse_mod.merge_consecutive_tools(entries)
      assert len(merged) == 1
      assert merged[0]["texts"] == ["Hello"]

   def test_empty_list(self, parse_mod):
      merged = parse_mod.merge_consecutive_tools([])
      assert merged == []

   def test_user_entry_between_tools_prevents_merge(self, parse_mod):
      entries = [
         {
            "role": "assistant",
            "texts": [],
            "tool_calls": [{"name": "Read", "summary": "Read: a.rs", "file_path": "a.rs"}],
         },
         {
            "role": "user",
            "texts": ["Continue"],
            "timestamp": "",
         },
         {
            "role": "assistant",
            "texts": [],
            "tool_calls": [{"name": "Read", "summary": "Read: b.rs", "file_path": "b.rs"}],
         },
      ]
      merged = parse_mod.merge_consecutive_tools(entries)
      assert len(merged) == 3

   def test_three_consecutive_tool_entries_merge(self, parse_mod):
      entries = [
         {
            "role": "assistant",
            "texts": [],
            "tool_calls": [{"name": "Read", "summary": "Read: a", "file_path": "a"}],
         },
         {
            "role": "assistant",
            "texts": [],
            "tool_calls": [{"name": "Read", "summary": "Read: b", "file_path": "b"}],
         },
         {
            "role": "assistant",
            "texts": [],
            "tool_calls": [{"name": "Read", "summary": "Read: c", "file_path": "c"}],
         },
      ]
      merged = parse_mod.merge_consecutive_tools(entries)
      assert len(merged) == 1
      assert len(merged[0]["tool_calls"]) == 3


# ── collect_skills_loaded ────────────────────────────────────────────────────

class TestCollectSkillsLoaded:
   def test_finds_skill_entries(self, parse_mod):
      entries = [
         {
            "role": "user",
            "texts": ["[Skill loaded: rust-helper (~50 words / ~100 tokens)]"],
         },
         {
            "role": "user",
            "texts": ["[Skill loaded: bench-runner (~30 words / ~60 tokens)]"],
         },
      ]
      skills = parse_mod.collect_skills_loaded(entries)
      assert len(skills) == 2
      assert skills[0] == ("rust-helper", None)
      assert skills[1] == ("bench-runner", None)

   def test_finds_skill_with_args(self, parse_mod):
      entries = [
         {
            "role": "user",
            "texts": [
               "[Skill loaded: rust-helper (~50 words / ~100 tokens)]\n"
               "[Skill arguments: src/storage/mod.rs]"
            ],
         },
      ]
      skills = parse_mod.collect_skills_loaded(entries)
      assert len(skills) == 1
      assert skills[0] == ("rust-helper", "src/storage/mod.rs")

   def test_deduplicates(self, parse_mod):
      entries = [
         {
            "role": "user",
            "texts": ["[Skill loaded: commit (~20 words / ~40 tokens)]"],
         },
         {
            "role": "user",
            "texts": ["[Skill loaded: commit (~20 words / ~40 tokens)]"],
         },
      ]
      skills = parse_mod.collect_skills_loaded(entries)
      assert len(skills) == 1

   def test_same_skill_different_args_not_deduped(self, parse_mod):
      entries = [
         {
            "role": "user",
            "texts": [
               "[Skill loaded: analyze (~50 words / ~100 tokens)]\n"
               "[Skill arguments: file-a.rs]"
            ],
         },
         {
            "role": "user",
            "texts": [
               "[Skill loaded: analyze (~50 words / ~100 tokens)]\n"
               "[Skill arguments: file-b.rs]"
            ],
         },
      ]
      skills = parse_mod.collect_skills_loaded(entries)
      assert len(skills) == 2

   def test_empty_entries(self, parse_mod):
      skills = parse_mod.collect_skills_loaded([])
      assert skills == []

   def test_ignores_assistant_entries(self, parse_mod):
      entries = [
         {
            "role": "assistant",
            "texts": ["[Skill loaded: not-real (~10 words / ~20 tokens)]"],
            "tool_calls": [],
         },
      ]
      skills = parse_mod.collect_skills_loaded(entries)
      assert skills == []


# ── collect_file_operations ──────────────────────────────────────────────────

class TestCollectFileOperations:
   def test_counts_reads_edits_writes(self, parse_mod):
      entries = [
         {
            "role": "assistant",
            "texts": [],
            "tool_calls": [
               {"name": "Read", "summary": "Read: a.rs", "file_path": "/src/a.rs"},
               {"name": "Read", "summary": "Read: a.rs", "file_path": "/src/a.rs"},
               {"name": "Edit", "summary": "Edit: a.rs", "file_path": "/src/a.rs"},
               {"name": "Write", "summary": "Write: b.rs", "file_path": "/src/b.rs"},
            ],
         },
      ]
      files = parse_mod.collect_file_operations(entries)
      assert files["/src/a.rs"]["reads"] == 2
      assert files["/src/a.rs"]["edits"] == 1
      assert files["/src/a.rs"]["writes"] == 0
      assert files["/src/b.rs"]["writes"] == 1

   def test_ignores_entries_without_file_path(self, parse_mod):
      entries = [
         {
            "role": "assistant",
            "texts": [],
            "tool_calls": [
               {"name": "Bash", "summary": "Bash: ls", "file_path": ""},
               {"name": "Glob", "summary": "Glob: *.rs", "file_path": ""},
            ],
         },
      ]
      files = parse_mod.collect_file_operations(entries)
      assert len(files) == 0

   def test_ignores_user_entries(self, parse_mod):
      entries = [
         {
            "role": "user",
            "texts": ["Read this file"],
         },
      ]
      files = parse_mod.collect_file_operations(entries)
      assert len(files) == 0

   def test_empty_entries(self, parse_mod):
      files = parse_mod.collect_file_operations([])
      assert files == {}


# ── format_output ────────────────────────────────────────────────────────────

class TestFormatOutput:
   def _make_simple_entries(self):
      """Create minimal entries for format_output tests."""
      return [
         {
            "role": "user",
            "texts": ["Hello"],
            "timestamp": "2026-01-15T10:00:00",
            "tool_results_count": 0,
            "tool_results_bytes": 0,
         },
         {
            "role": "assistant",
            "texts": ["Hi there, how can I help?"],
            "tool_calls": [],
         },
      ]

   def _make_metadata(self):
      return {
         "cwd": "/home/alex/projects/test",
         "branch": "main",
         "start_time": "2026-01-15T10:00:00",
         "last_time": "2026-01-15T10:05:00",
         "compaction_count": 0,
         "compaction_summaries_bytes": 0,
         "session_summary": None,
         "unknown_types": {},
      }

   def test_contains_session_resume_header(self, parse_mod):
      output = parse_mod.format_output(
         self._make_simple_entries(),
         self._make_metadata(),
         5000, 20, "/tmp/test.jsonl",
      )
      assert "=== SESSION RESUME ===" in output

   def test_contains_statistics_section(self, parse_mod):
      output = parse_mod.format_output(
         self._make_simple_entries(),
         self._make_metadata(),
         5000, 20, "/tmp/test.jsonl",
      )
      assert "=== STATISTICS ===" in output

   def test_contains_conversation_section(self, parse_mod):
      output = parse_mod.format_output(
         self._make_simple_entries(),
         self._make_metadata(),
         5000, 20, "/tmp/test.jsonl",
      )
      assert "=== CONVERSATION ===" in output

   def test_user_entry_format(self, parse_mod):
      output = parse_mod.format_output(
         self._make_simple_entries(),
         self._make_metadata(),
         5000, 20, "/tmp/test.jsonl",
      )
      # User entries formatted as "--- USER #N [...] (X tokens) ---"
      assert "--- USER #1 [" in output
      assert "tokens) ---" in output

   def test_compaction_entry_format(self, parse_mod):
      entries = [
         {
            "role": "compaction",
            "number": 1,
            "trigger": "auto",
            "pre_tokens": 45000,
            "kind": "compact",
         },
         {
            "role": "user",
            "texts": ["Continue"],
            "timestamp": "2026-01-15T10:05:00",
            "tool_results_count": 0,
            "tool_results_bytes": 0,
         },
      ]
      output = parse_mod.format_output(
         entries, self._make_metadata(), 5000, 20, "/tmp/test.jsonl",
      )
      assert "[=== COMPACTION #1 (auto, 45,000 tokens before) ===]" in output

   def test_microcompaction_entry_format(self, parse_mod):
      entries = [
         {
            "role": "compaction",
            "number": 1,
            "trigger": "micro",
            "pre_tokens": 0,
            "kind": "microcompact",
         },
         {
            "role": "user",
            "texts": ["Continue"],
            "timestamp": "2026-01-15T10:05:00",
            "tool_results_count": 0,
            "tool_results_bytes": 0,
         },
      ]
      output = parse_mod.format_output(
         entries, self._make_metadata(), 5000, 20, "/tmp/test.jsonl",
      )
      assert "[=== MICROCOMPACTION #1 ===]" in output

   def test_tool_entries_formatted_with_count(self, parse_mod):
      entries = [
         {
            "role": "user",
            "texts": ["Fix the bug"],
            "timestamp": "2026-01-15T10:00:00",
            "tool_results_count": 0,
            "tool_results_bytes": 0,
         },
         {
            "role": "assistant",
            "texts": [],
            "tool_calls": [
               {"name": "Read", "summary": "Read: foo.rs", "file_path": "foo.rs"},
               {"name": "Edit", "summary": "Edit: foo.rs", "file_path": "foo.rs"},
            ],
         },
      ]
      output = parse_mod.format_output(
         entries, self._make_metadata(), 5000, 20, "/tmp/test.jsonl",
      )
      assert "--- TOOLS (2 calls" in output

   def test_single_tool_no_plural(self, parse_mod):
      entries = [
         {
            "role": "user",
            "texts": ["Check the file"],
            "timestamp": "2026-01-15T10:00:00",
            "tool_results_count": 0,
            "tool_results_bytes": 0,
         },
         {
            "role": "assistant",
            "texts": [],
            "tool_calls": [
               {"name": "Read", "summary": "Read: foo.rs", "file_path": "foo.rs"},
            ],
         },
      ]
      output = parse_mod.format_output(
         entries, self._make_metadata(), 5000, 20, "/tmp/test.jsonl",
      )
      assert "--- TOOLS (1 call /" in output

   def test_estimated_tokens_line(self, parse_mod):
      output = parse_mod.format_output(
         self._make_simple_entries(),
         self._make_metadata(),
         5000, 20, "/tmp/test.jsonl",
      )
      assert "Estimated tokens:" in output

   def test_home_dir_shortened_in_files_touched(self, parse_mod):
      entries = [
         {
            "role": "user",
            "texts": ["Fix it"],
            "timestamp": "2026-01-15T10:00:00",
            "tool_results_count": 0,
            "tool_results_bytes": 0,
         },
         {
            "role": "assistant",
            "texts": [],
            "tool_calls": [
               {
                  "name": "Edit",
                  "summary": "Edit: ~/projects/file.rs",
                  "file_path": "/home/alex/projects/file.rs",
               },
            ],
         },
      ]
      output = parse_mod.format_output(
         entries, self._make_metadata(), 5000, 20, "/tmp/test.jsonl",
      )
      assert "=== FILES TOUCHED ===" in output
      assert "~/projects/file.rs" in output
      # Full path should NOT appear in the FILES TOUCHED section
      lines = output.split("\n")
      files_section = False
      for line in lines:
         if "=== FILES TOUCHED ===" in line:
            files_section = True
            continue
         if files_section and line.startswith("==="):
            break
         if files_section and "/home/alex/projects/file.rs" in line:
            pytest.fail("Full home path should be shortened in FILES TOUCHED")

   def test_truncated_messages_shown(self, parse_mod):
      metadata = self._make_metadata()
      metadata["truncated_messages"] = 20
      output = parse_mod.format_output(
         self._make_simple_entries(),
         metadata,
         50000, 200, "/tmp/test.jsonl",
      )
      assert "Truncated:" in output
      assert "20 messages omitted" in output


# ── Integration tests with fixtures for splitting/capping ────────────────────

class TestLongAutonomousOutput:
   """Test that long autonomous sessions produce continuation markers."""

   def test_continued_autonomous_markers(self, parse_mod, jsonl_fixture):
      entries, metadata, total_bytes, total_lines = parse_mod.parse_session(
         jsonl_fixture("long_autonomous.jsonl")
      )
      entries = parse_mod.merge_consecutive_tools(entries)

      # Simulate the main() splitting logic
      MAX_ENTRIES_PER_MESSAGE = 10
      split_entries = []
      i = 0
      while i < len(entries):
         entry = entries[i]
         if entry.get("role") == "user":
            split_entries.append(entry)
            bot_entries = []
            j = i + 1
            while j < len(entries) and entries[j].get("role") != "user":
               if entries[j].get("role") in ("assistant", "compaction"):
                  bot_entries.append(entries[j])
               j += 1
            if len(bot_entries) > MAX_ENTRIES_PER_MESSAGE:
               for chunk_start in range(0, len(bot_entries), MAX_ENTRIES_PER_MESSAGE):
                  chunk = bot_entries[chunk_start:chunk_start + MAX_ENTRIES_PER_MESSAGE]
                  split_entries.extend(chunk)
                  if chunk_start + MAX_ENTRIES_PER_MESSAGE < len(bot_entries):
                     split_entries.append({
                        "role": "user",
                        "texts": ["[...continued autonomous work...]"],
                        "timestamp": "",
                        "tool_results_count": 0,
                        "tool_results_bytes": 0,
                     })
            else:
               split_entries.extend(bot_entries)
            i = j
         else:
            split_entries.append(entry)
            i += 1

      output = parse_mod.format_output(
         split_entries, metadata, total_bytes, total_lines,
         str(jsonl_fixture("long_autonomous.jsonl")),
      )

      # The long_autonomous fixture has many consecutive assistant entries
      # after a single user message, so splitting should produce markers
      # Count assistant entries after merging
      merged_assistant_count = sum(
         1 for e in entries if e.get("role") == "assistant"
      )
      if merged_assistant_count > MAX_ENTRIES_PER_MESSAGE:
         assert "[...continued autonomous work...]" in output


class TestChattySessionOutput:
   """Test that chatty sessions with many exchanges get truncated."""

   def test_truncation_message(self, parse_mod, jsonl_fixture):
      entries, metadata, total_bytes, total_lines = parse_mod.parse_session(
         jsonl_fixture("chatty_session.jsonl")
      )
      entries = parse_mod.merge_consecutive_tools(entries)

      # Simulate main() capping logic
      MAX_MESSAGES = 100
      max_user_messages = MAX_MESSAGES // 2  # 50
      user_indices = [i for i, e in enumerate(entries) if e.get("role") == "user"]

      if len(user_indices) > max_user_messages:
         cut_index = user_indices[len(user_indices) - max_user_messages]
         truncated_count = len(user_indices) - max_user_messages
         entries = entries[cut_index:]
         metadata["truncated_messages"] = truncated_count * 2

      output = parse_mod.format_output(
         entries, metadata, total_bytes, total_lines,
         str(jsonl_fixture("chatty_session.jsonl")),
      )

      # chatty_session has 60 user messages, which exceeds the 50 limit
      if len(user_indices) > max_user_messages:
         assert "Truncated:" in output
         assert "messages omitted" in output

   def test_chatty_session_parses_without_error(self, parse_mod, jsonl_fixture):
      """Chatty session should parse without any errors."""
      entries, metadata, total_bytes, total_lines = parse_mod.parse_session(
         jsonl_fixture("chatty_session.jsonl")
      )
      assert len(entries) > 0
      assert total_bytes > 0
      user_entries = [e for e in entries if e.get("role") == "user"]
      assert len(user_entries) == 60
