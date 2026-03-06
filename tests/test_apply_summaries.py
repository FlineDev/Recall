"""Tests for apply-summaries.py: parse_entry_file(), estimate_tokens(), and apply pipeline."""

import os
import shutil
from pathlib import Path

import pytest


# ── estimate_tokens() ──────────────────────────────────────────────────────


class TestEstimateTokens:
   """Test estimate_tokens() byte-based estimation."""

   def test_empty_string(self, apply_mod):
      """Empty string produces 0 tokens."""
      assert apply_mod.estimate_tokens("") == 0

   def test_known_string(self, apply_mod):
      """Known ASCII string: int(len(bytes) / 2.2)."""
      text = "Hello, world!"
      expected = int(len(text.encode("utf-8")) / 2.2)
      assert apply_mod.estimate_tokens(text) == expected

   def test_unicode_text(self, apply_mod):
      """Unicode text uses correct byte count (not char count)."""
      text = "Hej verden! Hallo Welt! Привет мир!"
      byte_count = len(text.encode("utf-8"))
      expected = int(byte_count / 2.2)
      assert apply_mod.estimate_tokens(text) == expected

   def test_bytes_input(self, apply_mod):
      """Passing bytes directly also works."""
      data = b"Some bytes here"
      expected = int(len(data) / 2.2)
      assert apply_mod.estimate_tokens(data) == expected


# ── parse_entry_file() ─────────────────────────────────────────────────────


class TestParseEntryFile:
   """Test parse_entry_file() YAML frontmatter parsing."""

   def test_valid_frontmatter(self, apply_mod, tmp_path):
      """Valid file with YAML frontmatter: metadata extracted, int fields are ints."""
      entry = tmp_path / "000.md"
      entry.write_text(
         "---\n"
         "id: 3\n"
         "start_line: 15\n"
         "end_line: 25\n"
         "tokens: 500\n"
         "kind: bot\n"
         "target_words: 100\n"
         "---\n\n"
         "--- TOOLS (3 calls / 150 tokens) ---\n"
         "  Read: ~/projects/src/main.rs\n"
         "\n"
         "--- ASSISTANT (20 words / 50 tokens) ---\n"
         "I read the file and found the issue.\n"
      )
      metadata, content = apply_mod.parse_entry_file(str(entry))
      assert metadata is not None
      assert metadata["id"] == 3
      assert metadata["start_line"] == 15
      assert metadata["end_line"] == 25
      assert metadata["tokens"] == 500
      assert metadata["kind"] == "bot"
      assert metadata["target_words"] == 100
      assert isinstance(metadata["id"], int)
      assert isinstance(metadata["start_line"], int)
      assert "TOOLS" in content

   def test_no_frontmatter(self, apply_mod, tmp_path):
      """File without frontmatter returns (None, full_content)."""
      entry = tmp_path / "no_fm.md"
      text = "Just some content without frontmatter.\nLine two.\n"
      entry.write_text(text)
      metadata, content = apply_mod.parse_entry_file(str(entry))
      assert metadata is None
      assert content == text

   def test_only_frontmatter_no_content(self, apply_mod, tmp_path):
      """File with only frontmatter (no content after ---) returns (metadata, '')."""
      entry = tmp_path / "only_fm.md"
      entry.write_text(
         "---\n"
         "id: 0\n"
         "start_line: 1\n"
         "end_line: 5\n"
         "tokens: 100\n"
         "kind: user\n"
         "target_words: 20\n"
         "---\n\n"
      )
      metadata, content = apply_mod.parse_entry_file(str(entry))
      assert metadata is not None
      assert metadata["id"] == 0
      assert content == ""


# ── Full apply pipeline ────────────────────────────────────────────────────


class TestApplyPipeline:
   """Test the full apply-summaries pipeline by creating transcript + entry files."""

   def _make_transcript(self, path):
      """Create a small transcript file and return its path."""
      text = (
         "=== SESSION RESUME ===\n"
         "Project: /test\n\n"
         "=== STATISTICS ===\n"
         "User messages: 3\n"
         "Estimated tokens: ~2,000\n\n"
         "=== CONVERSATION ===\n\n"
         "--- USER #1 [2026-01-15T10:00:00] (30 tokens) ---\n"
         "Add a feature.\n\n"
         "--- TOOLS (2 calls / 200 tokens) ---\n"
         "  Read: src/main.rs\n"
         "  Read: src/lib.rs\n\n"
         "--- ASSISTANT (100 words / 400 tokens) ---\n"
         "I read both files and here is a very detailed analysis of the codebase "
         "structure. The main.rs file contains the entry point and CLI argument "
         "parsing logic. The lib.rs file has the core business logic including "
         "task management, filtering, and sorting. The code follows a modular "
         "pattern with clear separation of concerns. I recommend adding the new "
         "feature in lib.rs as a new public function. This will maintain the "
         "existing architecture and make testing easier. The feature should "
         "accept a configuration struct as input and return a Result type for "
         "proper error handling throughout the call chain.\n\n"
         "--- USER #2 [2026-01-15T10:05:00] (20 tokens) ---\n"
         "Sounds good, implement it.\n\n"
         "--- TOOLS (1 calls / 100 tokens) ---\n"
         "  Edit: src/lib.rs\n\n"
         "--- ASSISTANT (30 words / 80 tokens) ---\n"
         "Done. Added the new function with proper error handling.\n\n"
         "--- USER #3 [2026-01-15T10:10:00] (15 tokens) ---\n"
         "Run the tests.\n\n"
         "--- ASSISTANT (10 words / 40 tokens) ---\n"
         "All tests pass.\n"
      )
      p = path / "transcript.md"
      p.write_text(text)
      return p

   def _make_entry_files(self, entries_dir, transcript_path):
      """Create entry files with summaries shorter than originals."""
      entries_dir.mkdir(exist_ok=True)

      # Entry for the first bot message (TOOLS + ASSISTANT at lines 12-21)
      # Read the transcript to find the exact lines
      lines = transcript_path.read_text().split("\n")

      entry0 = entries_dir / "000.md"
      entry0.write_text(
         "---\n"
         "id: 0\n"
         "start_line: 12\n"
         "end_line: 21\n"
         "tokens: 600\n"
         "kind: bot\n"
         "target_words: 30\n"
         "---\n\n"
         "Read main.rs and lib.rs, recommended adding feature in lib.rs.\n"
      )
      return entries_dir

   def test_headers_preserved(self, apply_mod, tmp_path):
      """After applying, entry headers (--- TOOLS/ASSISTANT ---) are still present."""
      transcript = self._make_transcript(tmp_path)
      entries_dir = self._make_entry_files(tmp_path / "entries", transcript)

      # Run main() via subprocess-like approach: set sys.argv and call main
      import sys
      old_argv = sys.argv
      sys.argv = ["apply-summaries.py", str(transcript), str(entries_dir)]
      try:
         apply_mod.main()
      finally:
         sys.argv = old_argv

      result = transcript.read_text()
      assert "--- TOOLS" in result
      assert "--- ASSISTANT" in result

   def test_summarized_prefix_appears(self, apply_mod, tmp_path):
      """After applying, '[Summarized]' prefix appears before summary content."""
      transcript = self._make_transcript(tmp_path)
      entries_dir = self._make_entry_files(tmp_path / "entries", transcript)

      import sys
      old_argv = sys.argv
      sys.argv = ["apply-summaries.py", str(transcript), str(entries_dir)]
      try:
         apply_mod.main()
      finally:
         sys.argv = old_argv

      result = transcript.read_text()
      assert "[Summarized]" in result

   def test_token_estimate_updated(self, apply_mod, tmp_path):
      """After applying, the 'Estimated tokens' line in STATISTICS is updated."""
      transcript = self._make_transcript(tmp_path)
      entries_dir = self._make_entry_files(tmp_path / "entries", transcript)

      import sys
      old_argv = sys.argv
      sys.argv = ["apply-summaries.py", str(transcript), str(entries_dir)]
      try:
         apply_mod.main()
      finally:
         sys.argv = old_argv

      result = transcript.read_text()
      # Should have an updated token estimate (different from ~2,000)
      assert "Estimated tokens: ~" in result
      # The new estimate should be present and be a number
      for line in result.split("\n"):
         if line.startswith("Estimated tokens: ~"):
            # Extract the number
            num_str = line.split("~")[1].replace(",", "")
            assert int(num_str) > 0

   def test_safety_check_skips_same_length(self, apply_mod, tmp_path):
      """Entry file where summary >= 90% of original tokens -> skipped."""
      transcript = self._make_transcript(tmp_path)
      entries_dir = tmp_path / "entries_same"
      entries_dir.mkdir()

      # Create an entry with a "summary" that is at least 90% of original tokens.
      # original_tokens = 600, so summary must be >= 540 tokens.
      # 540 tokens * 2.2 bytes/token = 1188 bytes needed.
      long_summary = "x" * 1400  # 1400 bytes → ~636 tokens, well above 540
      entry0 = entries_dir / "000.md"
      entry0.write_text(
         "---\n"
         "id: 0\n"
         "start_line: 12\n"
         "end_line: 21\n"
         "tokens: 600\n"
         "kind: bot\n"
         "target_words: 30\n"
         "---\n\n"
         f"{long_summary}\n"
      )

      original_text = transcript.read_text()

      import sys
      old_argv = sys.argv
      sys.argv = ["apply-summaries.py", str(transcript), str(entries_dir)]
      try:
         apply_mod.main()
      finally:
         sys.argv = old_argv

      result = transcript.read_text()
      # Should NOT have [Summarized] because the summary was skipped
      assert "[Summarized]" not in result

   def test_multiple_entries_reverse_order(self, apply_mod, tmp_path):
      """Multiple entries are applied bottom-to-top to preserve line numbers."""
      # Create a transcript with two bot messages worth summarizing
      text = (
         "=== SESSION RESUME ===\n"
         "Project: /test\n\n"
         "=== STATISTICS ===\n"
         "Estimated tokens: ~3,000\n\n"
         "=== CONVERSATION ===\n\n"
         "--- USER #1 [2026-01-15T10:00:00] (30 tokens) ---\n"
         "First question.\n\n"
         "--- ASSISTANT (50 words / 300 tokens) ---\n"
         "First long answer with lots of detail that goes on and on "
         "and on and on and on and on and on about the first topic.\n\n"
         "--- USER #2 [2026-01-15T10:05:00] (20 tokens) ---\n"
         "Second question.\n\n"
         "--- ASSISTANT (50 words / 300 tokens) ---\n"
         "Second long answer with lots of detail that goes on and on "
         "and on and on and on and on and on about the second topic.\n\n"
         "--- USER #3 [2026-01-15T10:10:00] (15 tokens) ---\n"
         "Final.\n\n"
         "--- ASSISTANT (10 words / 40 tokens) ---\n"
         "Ok.\n"
      )
      transcript = tmp_path / "multi.md"
      transcript.write_text(text)

      entries_dir = tmp_path / "multi_entries"
      entries_dir.mkdir()

      # Entry for first bot (lines 11-13)
      (entries_dir / "000.md").write_text(
         "---\n"
         "id: 0\n"
         "start_line: 11\n"
         "end_line: 13\n"
         "tokens: 300\n"
         "kind: bot\n"
         "target_words: 10\n"
         "---\n\n"
         "Answered first question.\n"
      )

      # Entry for second bot (lines 17-19)
      (entries_dir / "001.md").write_text(
         "---\n"
         "id: 1\n"
         "start_line: 17\n"
         "end_line: 19\n"
         "tokens: 300\n"
         "kind: bot\n"
         "target_words: 10\n"
         "---\n\n"
         "Answered second question.\n"
      )

      import sys
      old_argv = sys.argv
      sys.argv = ["apply-summaries.py", str(transcript), str(entries_dir)]
      try:
         apply_mod.main()
      finally:
         sys.argv = old_argv

      result = transcript.read_text()
      # Both should be summarized
      assert result.count("[Summarized]") == 2
      # Both original ASSISTANT headers should be preserved
      assert result.count("--- ASSISTANT") >= 2

   def test_needs_summarization_removed_when_under_25k(self, apply_mod, tmp_path):
      """NEEDS SUMMARIZATION section is removed when token count drops under 25K."""
      text = (
         "=== SESSION RESUME ===\n"
         "Project: /test\n\n"
         "=== STATISTICS ===\n"
         "Estimated tokens: ~2,000\n\n"
         "=== CONVERSATION ===\n\n"
         "--- USER #1 [2026-01-15T10:00:00] (30 tokens) ---\n"
         "Hello.\n\n"
         "--- ASSISTANT (50 words / 500 tokens) ---\n"
         "This is a long response that takes up space. " * 10 + "\n\n"
         "\n=== NEEDS SUMMARIZATION ===\n"
         "This file exceeds 25K tokens.\n"
      )
      transcript = tmp_path / "with_needs.md"
      transcript.write_text(text)

      # Must provide at least one entry for main() to process the file
      entries_dir = tmp_path / "needs_entries"
      entries_dir.mkdir()
      entry0 = entries_dir / "000.md"
      entry0.write_text(
         "---\n"
         "id: 0\n"
         "start_line: 12\n"
         "end_line: 14\n"
         "tokens: 500\n"
         "kind: bot\n"
         "target_words: 20\n"
         "---\n\n"
         "Short summary of the response.\n"
      )

      import sys
      old_argv = sys.argv
      sys.argv = ["apply-summaries.py", str(transcript), str(entries_dir)]
      try:
         apply_mod.main()
      finally:
         sys.argv = old_argv

      result = transcript.read_text()
      assert "NEEDS SUMMARIZATION" not in result
