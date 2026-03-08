"""Tests for condense-tail.py: split/combine logic and exchange boundary handling."""

import json
import os
import re
from pathlib import Path

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────


def make_exchange(user_num, user_tokens=50, asst_words=30, asst_tokens=80,
                  tools_calls=1, tools_tokens=40, extra_text=""):
   """Build a single exchange (user + tools + assistant) as markdown lines."""
   lines = []
   user_text = f"User message number {user_num}. " + "x " * (user_tokens // 3)
   lines.append("> [!NOTE]\n")
   lines.append(f"> **User #{user_num}** · 2026-01-15T10:00:00 · {user_tokens} tokens\n")
   lines.append(">\n")
   lines.append(f"> {user_text}\n")
   lines.append("\n")
   lines.append(f"> **Tools** ({tools_calls} call / {tools_tokens} tokens)\n")
   lines.append(f"> Read: `~/projects/tasktracker/src/main.rs`\n")
   lines.append("\n")
   lines.append(f"**Assistant** · {asst_words} words / {asst_tokens} tokens\n")
   lines.append("\n")
   lines.append(f"Assistant response for message {user_num}. " + "y " * (asst_words // 2) + "\n")
   if extra_text:
      lines.append(extra_text + "\n")
   lines.append("\n")
   lines.append("---\n")
   lines.append("\n")
   return lines


def make_transcript(num_exchanges, tokens_per_exchange=500, header_tokens=None):
   """Build a full transcript markdown string with the given number of exchanges.

   Each exchange is padded to approximately tokens_per_exchange tokens.
   """
   header = (
      "## Session Resume\n"
      "\n"
      "- **Project:** /home/alex/projects/tasktracker\n"
      "- **Branch:** main\n"
      "- **Session ID:** test-session-12345678\n"
      "- **Started:** 2026-01-15T09:00:00\n"
      "- **Last activity:** 2026-01-15T18:00:00\n"
      "\n"
      "## Statistics\n"
      "\n"
      f"- **User messages:** {num_exchanges}\n"
      f"- **Assistant responses:** {num_exchanges}\n"
      f"- **Tool calls:** {num_exchanges}\n"
      "- **Subagent calls:** 0\n"
   )

   # Build conversation
   conversation_lines = ["## Conversation\n", "\n", "---\n", "\n"]
   for i in range(1, num_exchanges + 1):
      # Pad each exchange to target size
      padding_chars = max(0, int(tokens_per_exchange * 3.0) - 200)
      extra = "z " * (padding_chars // 2) if padding_chars > 0 else ""
      exchange = make_exchange(i, extra_text=extra)
      conversation_lines.extend(exchange)

   conversation_text = "".join(conversation_lines)

   # Calculate total and set header token estimate
   total_text = header + "- **Estimated tokens:** ~0\n\n" + conversation_text
   est_tokens = int(len(total_text.encode("utf-8")) / 3.0)
   if header_tokens is not None:
      est_tokens = header_tokens

   header += f"- **Estimated tokens:** ~{est_tokens:,}\n"
   header += "\n"

   return header + conversation_text


# ── estimate_tokens ───────────────────────────────────────────────────────


class TestEstimateTokens:
   def test_empty(self, condense_mod):
      assert condense_mod.estimate_tokens("") == 0

   def test_known_string(self, condense_mod):
      text = "Hello, world!"
      assert condense_mod.estimate_tokens(text) == int(len(text.encode("utf-8")) / 3.0)


# ── parse_token_estimate ──────────────────────────────────────────────────


class TestParseTokenEstimate:
   def test_parses_from_statistics(self, condense_mod):
      text = "## Statistics\n\n- **Estimated tokens:** ~27,793\n"
      assert condense_mod.parse_token_estimate(text) == 27793

   def test_parses_no_comma(self, condense_mod):
      text = "- **Estimated tokens:** ~5000\n"
      assert condense_mod.parse_token_estimate(text) == 5000

   def test_fallback_when_missing(self, condense_mod):
      text = "No token line here."
      result = condense_mod.parse_token_estimate(text)
      assert result == condense_mod.estimate_tokens(text)


# ── parse_exchanges ───────────────────────────────────────────────────────


class TestParseExchanges:
   def test_single_exchange(self, condense_mod):
      lines = make_exchange(1)
      exchanges = condense_mod.parse_exchanges(lines)
      assert len(exchanges) == 1
      assert exchanges[0]["start_idx"] == 0

   def test_multiple_exchanges(self, condense_mod):
      lines = make_exchange(1) + make_exchange(2) + make_exchange(3)
      exchanges = condense_mod.parse_exchanges(lines)
      assert len(exchanges) == 3

   def test_empty_input(self, condense_mod):
      assert condense_mod.parse_exchanges([]) == []

   def test_no_user_headers(self, condense_mod):
      lines = ["Some random text\n", "More text\n"]
      assert condense_mod.parse_exchanges(lines) == []


# ── split_at_exchange_boundary ────────────────────────────────────────────


class TestSplitAtExchangeBoundary:
   def test_all_fits_in_tail(self, condense_mod):
      """Small input: everything goes to tail, older is empty."""
      lines = make_exchange(1) + make_exchange(2)
      older, tail = condense_mod.split_at_exchange_boundary(lines, 50_000)
      assert older == []
      assert tail == lines

   def test_split_at_boundary(self, condense_mod):
      """Tail starts at a USER header line."""
      # Create enough exchanges to exceed target
      lines = []
      for i in range(1, 21):
         lines.extend(make_exchange(i, extra_text="padding " * 200))
      older, tail = condense_mod.split_at_exchange_boundary(lines, 5000)
      assert len(older) > 0
      assert len(tail) > 0
      # Tail must start with a USER header
      first_tail = tail[0].strip()
      assert first_tail == "> [!NOTE]"

   def test_respects_target_approximately(self, condense_mod):
      """Tail tokens should be roughly near the target."""
      lines = []
      for i in range(1, 31):
         lines.extend(make_exchange(i, extra_text="padding " * 100))
      older, tail = condense_mod.split_at_exchange_boundary(lines, 5000)
      tail_tokens = condense_mod.estimate_tokens("".join(tail))
      # Should be within reasonable range of target (exchanges are chunky)
      assert tail_tokens >= 3000
      assert tail_tokens <= 10000

   def test_empty_input(self, condense_mod):
      older, tail = condense_mod.split_at_exchange_boundary([], 5000)
      assert older == []
      assert tail == []

   def test_single_huge_exchange(self, condense_mod):
      """One exchange bigger than target: still included in tail."""
      lines = make_exchange(1, extra_text="huge " * 5000)
      older, tail = condense_mod.split_at_exchange_boundary(lines, 1000)
      # Single exchange can't be split, goes to tail
      assert older == []
      assert tail == lines


# ── cmd_split ─────────────────────────────────────────────────────────────


class TestCmdSplit:
   def test_no_action_under_threshold(self, condense_mod, tmp_path):
      """Transcript under 20K tokens: exit code 2, no files created."""
      transcript = make_transcript(5, tokens_per_exchange=200)
      p = tmp_path / "small.md"
      p.write_text(transcript)
      result = condense_mod.cmd_split(str(p), "test12345678")
      assert result == 2
      self._cleanup("test1234")

   def test_no_action_at_threshold(self, condense_mod, tmp_path):
      """Exactly at 20K tokens: no condensation."""
      transcript = make_transcript(5, tokens_per_exchange=200, header_tokens=20000)
      p = tmp_path / "exact.md"
      p.write_text(transcript)
      result = condense_mod.cmd_split(str(p), "test12345678")
      assert result == 2
      self._cleanup("test1234")

   def _cleanup(self, prefix, include_summary=False):
      """Remove temp files created by cmd_split."""
      for f in ["older", "tail", "prompt", "stats"]:
         ext = "txt" if f == "prompt" else ("json" if f == "stats" else "md")
         path = f"/tmp/recall-{f}-{prefix}.{ext}"
         if os.path.exists(path):
            os.remove(path)
      if include_summary:
         path = f"/tmp/recall-summary-{prefix}.md"
         if os.path.exists(path):
            os.remove(path)

   def test_split_creates_files(self, condense_mod, tmp_path):
      """Transcript over 20K: creates older, tail, prompt, and stats files."""
      transcript = make_transcript(40, tokens_per_exchange=800)
      p = tmp_path / "large.md"
      p.write_text(transcript)
      result = condense_mod.cmd_split(str(p), "test12345678")
      assert result == 0
      assert os.path.exists("/tmp/recall-older-test1234.md")
      assert os.path.exists("/tmp/recall-tail-test1234.md")
      assert os.path.exists("/tmp/recall-prompt-test1234.txt")
      assert os.path.exists("/tmp/recall-stats-test1234.json")
      self._cleanup("test1234")

   def test_tail_starts_at_user_header(self, condense_mod, tmp_path):
      """The tail file starts with a USER header."""
      transcript = make_transcript(40, tokens_per_exchange=800)
      p = tmp_path / "large.md"
      p.write_text(transcript)
      condense_mod.cmd_split(str(p), "testtail1234")
      tail = Path("/tmp/recall-tail-testtail.md").read_text()
      first_line = tail.split("\n")[0].strip()
      assert first_line == "> [!NOTE]"
      self._cleanup("testtail")

   def test_prompt_file_contains_key_instructions(self, condense_mod, tmp_path):
      """The prompt file contains key summarization instructions."""
      transcript = make_transcript(40, tokens_per_exchange=800)
      p = tmp_path / "large.md"
      p.write_text(transcript)
      condense_mod.cmd_split(str(p), "testprompt12")
      prompt = Path("/tmp/recall-prompt-testprom.txt").read_text()
      assert "PRIORITIES" in prompt
      assert "File paths" in prompt
      assert "Summarize:" in prompt
      self._cleanup("testprom")


# ── cmd_combine ───────────────────────────────────────────────────────────


class TestCmdCombine:
   def _setup_combine(self, condense_mod, tmp_path, session_id="testcomb12"):
      """Create a large transcript, split it, write a fake summary."""
      transcript = make_transcript(40, tokens_per_exchange=800)
      p = tmp_path / "combine.md"
      p.write_text(transcript)
      result = condense_mod.cmd_split(str(p), session_id + "345678")
      assert result == 0

      prefix = (session_id + "345678")[:8]
      # Write a fake summary
      summary_path = f"/tmp/recall-summary-{prefix}.md"
      Path(summary_path).write_text(
         "This session was about building the TaskTracker CLI. "
         "The user asked to add a new 'delete' command. "
         "Files modified: src/commands/delete.rs, src/main.rs."
      )
      return p, prefix

   def test_combine_produces_sections(self, condense_mod, tmp_path):
      """Combined output has both SUMMARIZED and RECENT sections."""
      p, prefix = self._setup_combine(condense_mod, tmp_path)
      result = condense_mod.cmd_combine(str(p), "testcomb12345678")
      assert result == 0
      output = p.read_text()
      assert "## Summarized Older Context" in output
      assert "## Recent Conversation (Verbatim)" in output

   def test_combine_preserves_header(self, condense_mod, tmp_path):
      """Combined output still has SESSION RESUME and STATISTICS."""
      p, prefix = self._setup_combine(condense_mod, tmp_path)
      condense_mod.cmd_combine(str(p), "testcomb12345678")
      output = p.read_text()
      assert "## Session Resume" in output
      assert "## Statistics" in output

   def test_combine_updates_token_estimate(self, condense_mod, tmp_path):
      """Token estimate is updated after combining."""
      p, prefix = self._setup_combine(condense_mod, tmp_path)
      condense_mod.cmd_combine(str(p), "testcomb12345678")
      output = p.read_text()
      # Should have an updated token estimate
      match = re.search(r"\*\*Estimated tokens:\*\* ~([\d,]+)", output)
      assert match is not None
      tokens = int(match.group(1).replace(",", ""))
      assert tokens > 0

   def test_combine_includes_summary_content(self, condense_mod, tmp_path):
      """The fake summary text appears in the output."""
      p, prefix = self._setup_combine(condense_mod, tmp_path)
      condense_mod.cmd_combine(str(p), "testcomb12345678")
      output = p.read_text()
      assert "TaskTracker CLI" in output
      assert "delete" in output

   def test_combine_cleans_up_temp_files(self, condense_mod, tmp_path):
      """Temp files are removed after combine (except stats, which pre-compact.sh reads)."""
      p, prefix = self._setup_combine(condense_mod, tmp_path)
      condense_mod.cmd_combine(str(p), "testcomb12345678")
      assert not os.path.exists(f"/tmp/recall-older-{prefix}.md")
      assert not os.path.exists(f"/tmp/recall-tail-{prefix}.md")
      assert not os.path.exists(f"/tmp/recall-prompt-{prefix}.txt")
      assert not os.path.exists(f"/tmp/recall-summary-{prefix}.md")
      # Stats file should still exist (pre-compact.sh needs it)
      assert os.path.exists(f"/tmp/recall-stats-{prefix}.json")
      os.remove(f"/tmp/recall-stats-{prefix}.json")

   def test_combine_missing_summary_returns_error(self, condense_mod, tmp_path):
      """If summary file doesn't exist, returns error code."""
      p = tmp_path / "nosummary.md"
      p.write_text(make_transcript(5, tokens_per_exchange=200))
      result = condense_mod.cmd_combine(str(p), "nonexist12345678")
      assert result == 1


# ── Compaction markers ────────────────────────────────────────────────────


class TestCompactionMarkers:
   def test_markers_preserved_in_correct_section(self, condense_mod):
      """Compaction markers stay in whichever section they fall in."""
      lines = []
      for i in range(1, 6):
         lines.extend(make_exchange(i, extra_text="padding " * 200))
      # Insert a compaction marker between exchanges 2 and 3
      marker_lines = ["> [!WARNING]\n", "> **Compaction #1** (auto, 50,000 tokens before)\n", "\n"]
      # Find where exchange 3 starts (> [!NOTE] line)
      exchange3_start = None
      count = 0
      for idx, line in enumerate(lines):
         if line.strip() == "> [!NOTE]":
            count += 1
            if count == 3:
               exchange3_start = idx
               break
      for i, ml in enumerate(marker_lines):
         lines.insert(exchange3_start + i, ml)

      older, tail = condense_mod.split_at_exchange_boundary(lines, 2000)
      combined = "".join(older) + "".join(tail)
      assert "Compaction #1" in combined


# ── Stats JSON ───────────────────────────────────────────────────────────


class TestStatsJson:
   def _cleanup(self, prefix):
      for f in ["older", "tail", "prompt", "stats"]:
         ext = "txt" if f == "prompt" else ("json" if f == "stats" else "md")
         path = f"/tmp/recall-{f}-{prefix}.{ext}"
         if os.path.exists(path):
            os.remove(path)

   def test_stats_written_when_condensed(self, condense_mod, tmp_path):
      """Stats JSON is written when condensation happens."""
      transcript = make_transcript(40, tokens_per_exchange=800)
      p = tmp_path / "large.md"
      p.write_text(transcript)
      result = condense_mod.cmd_split(str(p), "statstst1")
      assert result == 0
      stats_path = "/tmp/recall-stats-statstst.json"
      assert os.path.exists(stats_path)
      stats = json.loads(Path(stats_path).read_text())
      assert stats["condensed"] is True
      assert stats["original_tokens"] > 20000
      assert stats["tail_tokens"] > 0
      assert stats["older_tokens"] > 0
      assert stats["total_exchanges"] == 40
      assert stats["tail_exchanges"] > 0
      assert stats["tail_exchanges"] < 40
      assert stats["verbatim_pct"] > 0
      assert stats["summarized_pct"] > 0
      assert stats["verbatim_pct"] + stats["summarized_pct"] + stats["dropped_pct"] <= 101
      self._cleanup("statstst")

   def test_stats_written_when_not_condensed(self, condense_mod, tmp_path):
      """Stats JSON is written even when no condensation needed."""
      transcript = make_transcript(5, tokens_per_exchange=200)
      p = tmp_path / "small.md"
      p.write_text(transcript)
      result = condense_mod.cmd_split(str(p), "statsnocn")
      assert result == 2
      prefix = "statsnocn"[:8]
      stats_path = f"/tmp/recall-stats-{prefix}.json"
      assert os.path.exists(stats_path)
      stats = json.loads(Path(stats_path).read_text())
      assert stats["condensed"] is False
      assert stats["verbatim_pct"] == 100
      assert stats["summarized_pct"] == 0
      assert stats["dropped_pct"] == 0
      assert stats["total_exchanges"] == 5
      assert stats["tail_exchanges"] == 5
      self._cleanup(prefix)

   def test_stats_has_correct_keys_condensed(self, condense_mod, tmp_path):
      """Condensed stats has all expected keys."""
      transcript = make_transcript(40, tokens_per_exchange=800)
      p = tmp_path / "keys.md"
      p.write_text(transcript)
      condense_mod.cmd_split(str(p), "statskey1")
      stats = json.loads(Path("/tmp/recall-stats-statskey.json").read_text())
      expected_keys = {
         "condensed", "original_tokens", "tail_tokens", "older_tokens",
         "dropped_tokens", "total_exchanges", "tail_exchanges",
         "older_exchanges", "verbatim_pct", "summarized_pct", "dropped_pct",
      }
      assert set(stats.keys()) == expected_keys
      self._cleanup("statskey")

   def test_stats_has_correct_keys_not_condensed(self, condense_mod, tmp_path):
      """Non-condensed stats has all expected keys."""
      transcript = make_transcript(5, tokens_per_exchange=200)
      p = tmp_path / "keys2.md"
      p.write_text(transcript)
      condense_mod.cmd_split(str(p), "statsncky")
      stats = json.loads(Path("/tmp/recall-stats-statsnck.json").read_text())
      expected_keys = {
         "condensed", "original_tokens", "final_tokens",
         "total_exchanges", "tail_exchanges",
         "verbatim_pct", "summarized_pct", "dropped_pct",
      }
      assert set(stats.keys()) == expected_keys
      self._cleanup("statsnck")

   def test_combine_updates_stats_final_tokens(self, condense_mod, tmp_path):
      """cmd_combine updates the stats file with final_tokens."""
      transcript = make_transcript(40, tokens_per_exchange=800)
      p = tmp_path / "combine_stats.md"
      p.write_text(transcript)
      session_id = "stcomb12345678"
      prefix = session_id[:8]
      condense_mod.cmd_split(str(p), session_id)

      # Write fake summary
      Path(f"/tmp/recall-summary-{prefix}.md").write_text(
         "Summary of older context for TaskTracker CLI."
      )
      condense_mod.cmd_combine(str(p), session_id)

      stats = json.loads(Path(f"/tmp/recall-stats-{prefix}.json").read_text())
      assert "final_tokens" in stats
      assert stats["final_tokens"] > 0
      assert stats["final_tokens"] < stats["original_tokens"]
      self._cleanup(prefix)

   def test_percentages_sum_approximately_100(self, condense_mod, tmp_path):
      """Verbatim + summarized + dropped percentages sum to ~100%."""
      transcript = make_transcript(40, tokens_per_exchange=800)
      p = tmp_path / "pct.md"
      p.write_text(transcript)
      session_id = "statspct1"
      prefix = session_id[:8]
      condense_mod.cmd_split(str(p), session_id)
      stats = json.loads(Path(f"/tmp/recall-stats-{prefix}.json").read_text())
      total = stats["verbatim_pct"] + stats["summarized_pct"] + stats["dropped_pct"]
      # Rounding can cause ±1-2% deviation
      assert 98 <= total <= 102
      self._cleanup(prefix)
