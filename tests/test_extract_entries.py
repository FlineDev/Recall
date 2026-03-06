"""Tests for extract-longest.py: parse_entries() and group_into_messages()."""

import pytest


# ── parse_entries() ─────────────────────────────────────────────────────────


class TestParseEntries:
   """Test parse_entries() with real fixtures and edge cases."""

   def test_small_transcript_entry_count(self, extract_mod, md_fixture):
      """small_transcript.md has 5 USER + 5 ASSISTANT + 4 TOOLS = 14 entries (no COMPACTION)."""
      entries, lines = extract_mod.parse_entries(md_fixture("small_transcript.md"))
      # 5 users, 4 TOOLS blocks, 5 ASSISTANT blocks = 14
      assert len(entries) == 14
      assert all(k in e for e in entries for k in ("type", "start_line", "end_line", "tokens"))

   def test_entry_types_are_valid(self, extract_mod, md_fixture):
      """All returned entries must have type USER, ASSISTANT, or TOOLS."""
      entries, _ = extract_mod.parse_entries(md_fixture("small_transcript.md"))
      valid_types = {"USER", "ASSISTANT", "TOOLS"}
      for e in entries:
         assert e["type"] in valid_types, f"Unexpected type: {e['type']}"

   def test_tokens_match_header(self, extract_mod, md_fixture):
      """Token counts parsed from headers match the actual header values."""
      entries, _ = extract_mod.parse_entries(md_fixture("small_transcript.md"))
      # First entry is USER #1 with 30 tokens
      user1 = entries[0]
      assert user1["type"] == "USER"
      assert user1["tokens"] == 30

   def test_start_end_lines_1_indexed(self, extract_mod, md_fixture):
      """start_line is 1-indexed, end_line is exclusive."""
      entries, lines = extract_mod.parse_entries(md_fixture("small_transcript.md"))
      for e in entries:
         assert e["start_line"] >= 1
         assert e["end_line"] > e["start_line"]
         assert e["end_line"] <= len(lines)

   def test_header_section_skipped(self, extract_mod, md_fixture):
      """Content before '=== CONVERSATION ===' is not included in entries."""
      entries, lines = extract_mod.parse_entries(md_fixture("small_transcript.md"))
      # The first entry should start after the CONVERSATION header
      conv_line = None
      for i, line in enumerate(lines):
         if line.strip() == "=== CONVERSATION ===":
            conv_line = i + 1  # 1-indexed
            break
      assert conv_line is not None
      assert entries[0]["start_line"] > conv_line

   def test_compaction_entries_skipped(self, extract_mod, tmp_path):
      """COMPACTION markers are not included in the returned entries."""
      md = tmp_path / "with_compaction.md"
      md.write_text(
         "=== SESSION RESUME ===\n"
         "Project: /test\n\n"
         "=== STATISTICS ===\n"
         "Estimated tokens: ~1,000\n\n"
         "=== CONVERSATION ===\n\n"
         "--- USER #1 [2026-01-15T10:00:00] (30 tokens) ---\n"
         "Hello\n\n"
         "[=== COMPACTION #1 (auto, 50000 tokens before) ===]\n"
         "Summary of previous work.\n\n"
         "--- ASSISTANT (10 words / 40 tokens) ---\n"
         "Got it.\n\n"
         "--- USER #2 [2026-01-15T10:05:00] (20 tokens) ---\n"
         "Continue.\n\n"
         "--- ASSISTANT (5 words / 30 tokens) ---\n"
         "Sure.\n"
      )
      entries, _ = extract_mod.parse_entries(str(md))
      types = [e["type"] for e in entries]
      assert "COMPACTION" not in types
      assert set(types) <= {"USER", "ASSISTANT", "TOOLS"}

   def test_large_transcript_entry_count(self, extract_mod, md_fixture):
      """large_transcript.md (~40K tokens, 30 exchanges) has many entries."""
      entries, _ = extract_mod.parse_entries(md_fixture("large_transcript.md"))
      # 30 users + 30 assistants + some tools = a lot
      assert len(entries) >= 60
      user_count = sum(1 for e in entries if e["type"] == "USER")
      assert user_count == 30

   def test_content_at_line_references(self, extract_mod, md_fixture):
      """Lines referenced by start_line/end_line contain actual content."""
      entries, lines = extract_mod.parse_entries(md_fixture("small_transcript.md"))
      for e in entries:
         start_idx = e["start_line"] - 1
         end_idx = e["end_line"]
         chunk = "".join(lines[start_idx:end_idx]).strip()
         assert len(chunk) > 0, f"Empty content for entry at lines {e['start_line']}-{e['end_line']}"


# ── group_into_messages() ──────────────────────────────────────────────────


class TestGroupIntoMessages:
   """Test group_into_messages() with constructed entry lists and real data."""

   def test_user_entries_become_user_messages(self, extract_mod):
      """Each USER entry becomes a kind='user' message."""
      entries = [
         {"type": "USER", "start_line": 1, "end_line": 3, "tokens": 30},
         {"type": "ASSISTANT", "start_line": 3, "end_line": 5, "tokens": 50},
      ]
      messages = extract_mod.group_into_messages(entries)
      assert messages[0]["kind"] == "user"
      assert messages[0]["tokens"] == 30

   def test_consecutive_tools_assistant_grouped(self, extract_mod):
      """Consecutive TOOLS + ASSISTANT entries become a single bot message."""
      entries = [
         {"type": "USER", "start_line": 1, "end_line": 3, "tokens": 20},
         {"type": "TOOLS", "start_line": 3, "end_line": 6, "tokens": 80},
         {"type": "ASSISTANT", "start_line": 6, "end_line": 9, "tokens": 100},
      ]
      messages = extract_mod.group_into_messages(entries)
      assert len(messages) == 2
      bot = messages[1]
      assert bot["kind"] == "bot"
      assert bot["tokens"] == 180  # 80 + 100
      assert len(bot["entries"]) == 2

   def test_alternating_user_bot_pattern(self, extract_mod):
      """Messages alternate between user and bot."""
      entries = [
         {"type": "USER", "start_line": 1, "end_line": 3, "tokens": 20},
         {"type": "TOOLS", "start_line": 3, "end_line": 5, "tokens": 40},
         {"type": "ASSISTANT", "start_line": 5, "end_line": 7, "tokens": 60},
         {"type": "USER", "start_line": 7, "end_line": 9, "tokens": 15},
         {"type": "ASSISTANT", "start_line": 9, "end_line": 11, "tokens": 50},
      ]
      messages = extract_mod.group_into_messages(entries)
      kinds = [m["kind"] for m in messages]
      assert kinds == ["user", "bot", "user", "bot"]

   def test_bot_message_line_range(self, extract_mod):
      """Bot message start_line/end_line spans all its entries."""
      entries = [
         {"type": "USER", "start_line": 1, "end_line": 3, "tokens": 20},
         {"type": "TOOLS", "start_line": 3, "end_line": 6, "tokens": 80},
         {"type": "ASSISTANT", "start_line": 6, "end_line": 10, "tokens": 100},
      ]
      messages = extract_mod.group_into_messages(entries)
      bot = messages[1]
      assert bot["start_line"] == 3
      assert bot["end_line"] == 10

   def test_orphan_non_user_at_start(self, extract_mod):
      """An orphan non-USER entry at the start becomes a bot message."""
      entries = [
         {"type": "ASSISTANT", "start_line": 1, "end_line": 4, "tokens": 50},
         {"type": "USER", "start_line": 4, "end_line": 6, "tokens": 20},
         {"type": "ASSISTANT", "start_line": 6, "end_line": 8, "tokens": 30},
      ]
      messages = extract_mod.group_into_messages(entries)
      assert len(messages) == 3
      assert messages[0]["kind"] == "bot"
      assert messages[0]["tokens"] == 50
      assert messages[1]["kind"] == "user"
      assert messages[2]["kind"] == "bot"

   def test_real_fixture_grouping(self, extract_mod, md_fixture):
      """Grouping small_transcript.md produces alternating user/bot messages."""
      entries, _ = extract_mod.parse_entries(md_fixture("small_transcript.md"))
      messages = extract_mod.group_into_messages(entries)
      kinds = [m["kind"] for m in messages]
      # Should alternate user/bot
      for i in range(0, len(kinds) - 1, 2):
         assert kinds[i] == "user"
         assert kinds[i + 1] == "bot"

   def test_multiple_tools_in_one_bot(self, extract_mod):
      """Multiple TOOLS entries followed by ASSISTANT all belong to one bot message."""
      entries = [
         {"type": "USER", "start_line": 1, "end_line": 3, "tokens": 20},
         {"type": "TOOLS", "start_line": 3, "end_line": 5, "tokens": 40},
         {"type": "TOOLS", "start_line": 5, "end_line": 7, "tokens": 30},
         {"type": "ASSISTANT", "start_line": 7, "end_line": 10, "tokens": 60},
      ]
      messages = extract_mod.group_into_messages(entries)
      assert len(messages) == 2
      bot = messages[1]
      assert bot["kind"] == "bot"
      assert bot["tokens"] == 130  # 40 + 30 + 60
      assert len(bot["entries"]) == 3
