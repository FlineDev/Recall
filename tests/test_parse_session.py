"""Tests for parse_session() with JSONL fixtures and inline-constructed data."""

import pytest


# ── Fixture-based tests ──────────────────────────────────────────────────────

class TestTinySession:
   def test_entry_count(self, parse_mod, jsonl_fixture):
      entries, metadata, total_bytes, total_lines = parse_mod.parse_session(
         jsonl_fixture("tiny_session.jsonl")
      )
      # tiny_session has 2 user messages and 2 assistant messages
      user_entries = [e for e in entries if e["role"] == "user"]
      assistant_entries = [e for e in entries if e["role"] == "assistant"]
      assert len(user_entries) == 2
      assert len(assistant_entries) == 2

   def test_metadata_cwd(self, parse_mod, jsonl_fixture):
      _, metadata, _, _ = parse_mod.parse_session(
         jsonl_fixture("tiny_session.jsonl")
      )
      assert metadata["cwd"] == "/home/alex/projects/tasktracker"

   def test_metadata_branch(self, parse_mod, jsonl_fixture):
      _, metadata, _, _ = parse_mod.parse_session(
         jsonl_fixture("tiny_session.jsonl")
      )
      assert metadata["branch"] == "main"

   def test_metadata_timestamps(self, parse_mod, jsonl_fixture):
      _, metadata, _, _ = parse_mod.parse_session(
         jsonl_fixture("tiny_session.jsonl")
      )
      assert metadata["start_time"].startswith("2026-01-15")
      assert metadata["last_time"].startswith("2026-01-15")

   def test_total_bytes_positive(self, parse_mod, jsonl_fixture):
      _, _, total_bytes, _ = parse_mod.parse_session(
         jsonl_fixture("tiny_session.jsonl")
      )
      assert total_bytes > 0

   def test_total_lines(self, parse_mod, jsonl_fixture):
      _, _, _, total_lines = parse_mod.parse_session(
         jsonl_fixture("tiny_session.jsonl")
      )
      assert total_lines > 0


class TestShortSession:
   def test_tool_calls_extracted(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("short_session.jsonl")
      )
      assistant_entries = [e for e in entries if e["role"] == "assistant"]
      # short_session has assistant entries with tool_use blocks
      all_tool_calls = []
      for e in assistant_entries:
         all_tool_calls.extend(e.get("tool_calls", []))
      assert len(all_tool_calls) > 0
      tool_names = {tc["name"] for tc in all_tool_calls}
      # short_session has Grep, Read, Edit, Bash tools
      assert "Grep" in tool_names or "Edit" in tool_names or "Read" in tool_names


class TestMultiCompaction:
   def test_compaction_entries_created(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("multi_compaction.jsonl")
      )
      compaction_entries = [e for e in entries if e.get("role") == "compaction"]
      # multi_compaction has 3 compact_boundary entries
      assert len(compaction_entries) == 3

   def test_compaction_count_in_metadata(self, parse_mod, jsonl_fixture):
      _, metadata, _, _ = parse_mod.parse_session(
         jsonl_fixture("multi_compaction.jsonl")
      )
      assert metadata["compaction_count"] == 3

   def test_summary_messages_stripped(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("multi_compaction.jsonl")
      )
      # Summary messages (starting with COMPACT_SUMMARY_PREFIX) should be stripped
      for entry in entries:
         if entry.get("role") == "user":
            for text in entry.get("texts", []):
               assert not text.startswith(
                  "This session is being continued from a previous conversation"
               )

   def test_compaction_has_trigger_and_pretokens(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("multi_compaction.jsonl")
      )
      compaction_entries = [e for e in entries if e.get("role") == "compaction"]
      for ce in compaction_entries:
         assert "trigger" in ce
         assert "pre_tokens" in ce
         assert "kind" in ce
         assert ce["kind"] == "compact"


class TestWithSkills:
   def test_skill_injections_condensed(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("with_skills.jsonl")
      )
      # Skill injection messages should be condensed to "[Skill loaded: ...]"
      found_skill = False
      for entry in entries:
         if entry.get("role") == "user":
            for text in entry.get("texts", []):
               if text.startswith("[Skill loaded:"):
                  found_skill = True
      assert found_skill, "Expected at least one condensed skill injection"

   def test_no_raw_skill_content(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("with_skills.jsonl")
      )
      # The full skill content should NOT appear in entries
      for entry in entries:
         if entry.get("role") == "user":
            for text in entry.get("texts", []):
               assert not text.startswith("Base directory for this skill:")


class TestWithImages:
   def test_image_markers(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("with_images.jsonl")
      )
      found_image = False
      for entry in entries:
         if entry.get("role") == "user":
            for text in entry.get("texts", []):
               if text.startswith("[Image: image/png]"):
                  found_image = True
      assert found_image, "Expected [Image: image/png] markers"


class TestEmptySession:
   def test_empty_entries(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("empty_session.jsonl")
      )
      # Only progress and file-history-snapshot lines, no user/assistant
      user_entries = [e for e in entries if e.get("role") == "user"]
      assert len(user_entries) == 0

   def test_no_crash(self, parse_mod, jsonl_fixture):
      # Should not raise any exceptions
      entries, metadata, total_bytes, total_lines = parse_mod.parse_session(
         jsonl_fixture("empty_session.jsonl")
      )
      assert isinstance(entries, list)
      assert isinstance(metadata, dict)


class TestSingleMessage:
   def test_single_user_entry(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("single_message.jsonl")
      )
      user_entries = [e for e in entries if e.get("role") == "user"]
      assert len(user_entries) == 1

   def test_no_crash(self, parse_mod, jsonl_fixture):
      entries, metadata, total_bytes, total_lines = parse_mod.parse_session(
         jsonl_fixture("single_message.jsonl")
      )
      assert isinstance(entries, list)


class TestMicrocompact:
   def test_microcompaction_entries(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("microcompact.jsonl")
      )
      micro_entries = [
         e for e in entries
         if e.get("role") == "compaction" and e.get("kind") == "microcompact"
      ]
      assert len(micro_entries) >= 1

   def test_microcompaction_kind(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("microcompact.jsonl")
      )
      micro_entries = [
         e for e in entries
         if e.get("role") == "compaction" and e.get("kind") == "microcompact"
      ]
      for me in micro_entries:
         assert me["trigger"] == "micro"
         assert me["pre_tokens"] == 0


class TestUnknownTypes:
   def test_unknown_types_in_metadata(self, parse_mod, jsonl_fixture):
      _, metadata, _, _ = parse_mod.parse_session(
         jsonl_fixture("unknown_types.jsonl")
      )
      assert len(metadata["unknown_types"]) > 0

   def test_unknown_types_counted(self, parse_mod, jsonl_fixture):
      _, metadata, _, _ = parse_mod.parse_session(
         jsonl_fixture("unknown_types.jsonl")
      )
      # The fixture has "new_experimental_feature" and system "analytics_event" types
      unknown = metadata["unknown_types"]
      assert any(count > 0 for count in unknown.values())


class TestMixedContentUser:
   def test_array_content_parsed(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("mixed_content_user.jsonl")
      )
      user_entries = [e for e in entries if e.get("role") == "user"]
      assert len(user_entries) >= 1
      # First user message has text + tool_result + image content blocks
      first_user = user_entries[0]
      assert len(first_user["texts"]) >= 1

   def test_tool_results_counted(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("mixed_content_user.jsonl")
      )
      user_entries = [e for e in entries if e.get("role") == "user"]
      # At least one user message should have tool_results_count > 0
      has_tool_results = any(
         e.get("tool_results_count", 0) > 0 for e in user_entries
      )
      assert has_tool_results

   def test_images_in_mixed_content(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("mixed_content_user.jsonl")
      )
      all_texts = []
      for e in entries:
         if e.get("role") == "user":
            all_texts.extend(e.get("texts", []))
      image_texts = [t for t in all_texts if t.startswith("[Image:")]
      assert len(image_texts) >= 1


class TestWithPlans:
   def test_plan_injection_condensed(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("with_plans.jsonl")
      )
      found_plan = False
      for entry in entries:
         if entry.get("role") == "user":
            for text in entry.get("texts", []):
               if text.startswith("[Plan injected:"):
                  found_plan = True
      assert found_plan, "Expected at least one condensed plan injection"

   def test_no_raw_plan_content(self, parse_mod, jsonl_fixture):
      entries, _, _, _ = parse_mod.parse_session(
         jsonl_fixture("with_plans.jsonl")
      )
      for entry in entries:
         if entry.get("role") == "user":
            for text in entry.get("texts", []):
               assert not text.startswith("Implement the following plan:")


# ── Inline-constructed JSONL tests ───────────────────────────────────────────

class TestSystemRemindersStripped:
   def test_system_reminder_stripped(self, parse_mod, write_jsonl):
      entries_data = [
         {
            "type": "user",
            "message": {
               "role": "user",
               "content": "<system-reminder>You are Claude.</system-reminder>",
            },
            "cwd": "/tmp",
            "timestamp": "2026-01-01T00:00:00",
         },
         {
            "type": "user",
            "message": {
               "role": "user",
               "content": "Real user message here.",
            },
            "cwd": "/tmp",
            "timestamp": "2026-01-01T00:01:00",
         },
      ]
      path = write_jsonl(entries_data)
      entries, _, _, _ = parse_mod.parse_session(path)
      user_entries = [e for e in entries if e.get("role") == "user"]
      # system-reminder message should be skipped (no texts)
      # Only the real user message should appear
      assert len(user_entries) == 1
      assert user_entries[0]["texts"] == ["Real user message here."]

   def test_system_reminder_in_array_content(self, parse_mod, write_jsonl):
      entries_data = [
         {
            "type": "user",
            "message": {
               "role": "user",
               "content": [
                  {"type": "text", "text": "<system-reminder>Hidden</system-reminder>"},
                  {"type": "text", "text": "Visible user text."},
               ],
            },
            "cwd": "/tmp",
            "timestamp": "2026-01-01T00:00:00",
         },
      ]
      path = write_jsonl(entries_data)
      entries, _, _, _ = parse_mod.parse_session(path)
      user_entries = [e for e in entries if e.get("role") == "user"]
      assert len(user_entries) == 1
      assert "Visible user text." in user_entries[0]["texts"]
      # system-reminder text should NOT be in texts
      for text in user_entries[0]["texts"]:
         assert "<system-reminder>" not in text


class TestLocalCommandCaveat:
   def test_caveat_stripped(self, parse_mod, write_jsonl):
      entries_data = [
         {
            "type": "user",
            "message": {
               "role": "user",
               "content": "<local-command-caveat>some caveat</local-command-caveat>",
            },
            "cwd": "/tmp",
            "timestamp": "2026-01-01T00:00:00",
         },
      ]
      path = write_jsonl(entries_data)
      entries, _, _, _ = parse_mod.parse_session(path)
      user_entries = [e for e in entries if e.get("role") == "user"]
      # Caveat messages produce no texts and thus no entry
      assert len(user_entries) == 0


class TestCommandNameTags:
   def test_command_name_converted(self, parse_mod, write_jsonl):
      entries_data = [
         {
            "type": "user",
            "message": {
               "role": "user",
               "content": "<command-name>commit</command-name>",
            },
            "cwd": "/tmp",
            "timestamp": "2026-01-01T00:00:00",
         },
      ]
      path = write_jsonl(entries_data)
      entries, _, _, _ = parse_mod.parse_session(path)
      user_entries = [e for e in entries if e.get("role") == "user"]
      assert len(user_entries) == 1
      assert user_entries[0]["texts"] == ["[User ran: /commit]"]

   def test_command_name_with_slash(self, parse_mod, write_jsonl):
      entries_data = [
         {
            "type": "user",
            "message": {
               "role": "user",
               "content": "<command-name>/review</command-name>",
            },
            "cwd": "/tmp",
            "timestamp": "2026-01-01T00:00:00",
         },
      ]
      path = write_jsonl(entries_data)
      entries, _, _, _ = parse_mod.parse_session(path)
      user_entries = [e for e in entries if e.get("role") == "user"]
      assert user_entries[0]["texts"] == ["[User ran: /review]"]

   def test_command_name_in_array_content(self, parse_mod, write_jsonl):
      entries_data = [
         {
            "type": "user",
            "message": {
               "role": "user",
               "content": [
                  {"type": "text", "text": "<command-name>build</command-name>"},
               ],
            },
            "cwd": "/tmp",
            "timestamp": "2026-01-01T00:00:00",
         },
      ]
      path = write_jsonl(entries_data)
      entries, _, _, _ = parse_mod.parse_session(path)
      user_entries = [e for e in entries if e.get("role") == "user"]
      assert user_entries[0]["texts"] == ["[User ran: /build]"]


class TestLocalCommandStdout:
   def test_stdout_converted(self, parse_mod, write_jsonl):
      entries_data = [
         {
            "type": "user",
            "message": {
               "role": "user",
               "content": "<local-command-stdout>build succeeded\n3 warnings</local-command-stdout>",
            },
            "cwd": "/tmp",
            "timestamp": "2026-01-01T00:00:00",
         },
      ]
      path = write_jsonl(entries_data)
      entries, _, _, _ = parse_mod.parse_session(path)
      user_entries = [e for e in entries if e.get("role") == "user"]
      assert len(user_entries) == 1
      assert user_entries[0]["texts"][0].startswith("[Command output:")
      assert "build succeeded" in user_entries[0]["texts"][0]

   def test_stdout_truncated(self, parse_mod, write_jsonl):
      long_output = "x" * 500
      entries_data = [
         {
            "type": "user",
            "message": {
               "role": "user",
               "content": f"<local-command-stdout>{long_output}</local-command-stdout>",
            },
            "cwd": "/tmp",
            "timestamp": "2026-01-01T00:00:00",
         },
      ]
      path = write_jsonl(entries_data)
      entries, _, _, _ = parse_mod.parse_session(path)
      user_entries = [e for e in entries if e.get("role") == "user"]
      # Output is truncated to 200 chars
      text = user_entries[0]["texts"][0]
      # The format is "[Command output: <truncated>]"
      assert len(text) < 300

   def test_stdout_in_array_content(self, parse_mod, write_jsonl):
      entries_data = [
         {
            "type": "user",
            "message": {
               "role": "user",
               "content": [
                  {"type": "text", "text": "<local-command-stdout>hello world</local-command-stdout>"},
               ],
            },
            "cwd": "/tmp",
            "timestamp": "2026-01-01T00:00:00",
         },
      ]
      path = write_jsonl(entries_data)
      entries, _, _, _ = parse_mod.parse_session(path)
      user_entries = [e for e in entries if e.get("role") == "user"]
      assert "[Command output: hello world]" in user_entries[0]["texts"]
