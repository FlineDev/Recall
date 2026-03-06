"""End-to-end pipeline tests: parse-transcript -> extract-longest -> apply-summaries."""

import json
import os
import sys
from pathlib import Path

import pytest


def mock_summarize_entries(entries_dir, apply_mod):
   """Replace entry file content with shorter fake summaries."""
   for filename in sorted(os.listdir(entries_dir)):
      if not filename.endswith(".md"):
         continue
      filepath = os.path.join(entries_dir, filename)
      metadata, content = apply_mod.parse_entry_file(filepath)
      if not metadata:
         continue
      target_words = metadata.get("target_words", 20)
      fake_summary = f"Summarized: performed {target_words} operations on the codebase."
      text = Path(filepath).read_text()
      idx = text.index("\n---\n", 4)
      Path(filepath).write_text(text[:idx + 5] + fake_summary + "\n")


class TestFullPipeline:
   """End-to-end tests combining parse, extract, and apply."""

   def test_parse_extract_line_references_valid(
      self, parse_mod, extract_mod, jsonl_fixture, tmp_path
   ):
      """Parse tiny_session.jsonl, format to markdown, then extract entries.

      Verify that all line references from parse_entries() are valid
      (within file range and non-empty content).
      """
      # Step 1: Parse the JSONL file
      transcript_path = jsonl_fixture("tiny_session.jsonl")
      entries, metadata, total_bytes, total_lines = parse_mod.parse_session(
         str(transcript_path)
      )

      # Step 2: Merge consecutive tools
      entries = parse_mod.merge_consecutive_tools(entries)

      # Step 3: Format to markdown
      md_output = parse_mod.format_output(
         entries, metadata, total_bytes, total_lines, str(transcript_path)
      )

      # Step 4: Write to tmp file
      md_path = tmp_path / "parsed.md"
      md_path.write_text(md_output)

      # Step 5: Extract entries from the markdown
      extracted, lines = extract_mod.parse_entries(str(md_path))
      assert len(extracted) > 0, "Should extract at least one entry"

      # Step 6: Group into messages
      messages = extract_mod.group_into_messages(extracted)
      assert len(messages) > 0

      # Step 7: Verify line references are valid
      total_lines_in_file = len(lines)
      for e in extracted:
         assert 1 <= e["start_line"] <= total_lines_in_file, (
            f"start_line {e['start_line']} out of range (1-{total_lines_in_file})"
         )
         assert e["start_line"] < e["end_line"] <= total_lines_in_file, (
            f"end_line {e['end_line']} out of range"
         )
         # Content at those lines is not empty
         chunk = "".join(lines[e["start_line"] - 1 : e["end_line"]]).strip()
         assert len(chunk) > 0

   def test_pipeline_with_summarization(
      self, parse_mod, extract_mod, apply_mod, jsonl_fixture, tmp_path
   ):
      """Parse medium_session.jsonl, produce markdown, mock-summarize if needed.

      If the markdown exceeds 25K tokens, extract entries, mock-summarize,
      apply, and verify the output is smaller and structurally intact.
      """
      transcript_path = jsonl_fixture("medium_session.jsonl")
      entries, metadata, total_bytes, total_lines = parse_mod.parse_session(
         str(transcript_path)
      )
      entries = parse_mod.merge_consecutive_tools(entries)
      md_output = parse_mod.format_output(
         entries, metadata, total_bytes, total_lines, str(transcript_path)
      )

      md_path = tmp_path / "medium.md"
      md_path.write_text(md_output)

      original_tokens = apply_mod.estimate_tokens(md_output)

      if original_tokens > 25000:
         # Extract
         extracted, lines = extract_mod.parse_entries(str(md_path))
         messages = extract_mod.group_into_messages(extracted)
         to_summarize, remaining_budget = extract_mod.select_messages_to_summarize(
            messages
         )

         if to_summarize:
            # Write entry files
            entries_dir = tmp_path / "entries"
            entries_dir.mkdir()

            total_extracted_tokens = sum(m["tokens"] for m in to_summarize)
            for idx, msg in enumerate(to_summarize):
               if "_force_target_words" in msg:
                  target_words = msg["_force_target_words"]
               elif total_extracted_tokens > 0 and remaining_budget > 0:
                  target_tokens = msg["tokens"] * (
                     remaining_budget / total_extracted_tokens
                  )
                  target_words = max(20, round(target_tokens / 2.5))
               else:
                  target_words = 20

               start_idx = msg["start_line"] - 1
               end_idx = msg["end_line"]
               content = "".join(lines[start_idx:end_idx]).strip()

               entry_path = entries_dir / f"{idx:03d}.md"
               entry_path.write_text(
                  f"---\n"
                  f"id: {idx}\n"
                  f"start_line: {msg['start_line']}\n"
                  f"end_line: {msg['end_line']}\n"
                  f"tokens: {msg['tokens']}\n"
                  f"kind: {msg['kind']}\n"
                  f"target_words: {target_words}\n"
                  f"---\n\n"
                  f"{content}\n"
               )

            # Mock summarize
            mock_summarize_entries(str(entries_dir), apply_mod)

            # Apply
            old_argv = sys.argv
            sys.argv = ["apply-summaries.py", str(md_path), str(entries_dir)]
            try:
               apply_mod.main()
            finally:
               sys.argv = old_argv

            result = md_path.read_text()
            final_tokens = apply_mod.estimate_tokens(result)

            # Verify output is smaller
            assert final_tokens < original_tokens, (
               f"Expected smaller output: {final_tokens} >= {original_tokens}"
            )

            # Verify structure intact
            assert "=== SESSION RESUME ===" in result
            assert "=== STATISTICS ===" in result
            assert "=== CONVERSATION ===" in result
      else:
         # Under 25K: just verify structure
         assert "=== CONVERSATION ===" in md_output

   def test_large_transcript_full_pipeline(
      self, extract_mod, apply_mod, md_fixture, tmp_path
   ):
      """Use large_transcript.md directly: extract, mock-summarize, apply.

      Verify output is under 25K tokens and no data corruption occurred.
      """
      source_path = md_fixture("large_transcript.md")
      # Copy to tmp so we can modify it
      md_path = tmp_path / "large.md"
      md_path.write_text(Path(source_path).read_text())

      original_text = md_path.read_text()
      original_tokens = apply_mod.estimate_tokens(original_text)

      # Extract
      extracted, lines = extract_mod.parse_entries(str(md_path))
      messages = extract_mod.group_into_messages(extracted)
      to_summarize, remaining_budget = extract_mod.select_messages_to_summarize(
         messages
      )

      assert len(to_summarize) > 0, (
         f"large_transcript.md ({original_tokens} tokens) should need summarization"
      )

      # Write entry files
      entries_dir = tmp_path / "entries"
      entries_dir.mkdir()

      total_extracted_tokens = sum(m["tokens"] for m in to_summarize)
      for idx, msg in enumerate(to_summarize):
         if "_force_target_words" in msg:
            target_words = msg["_force_target_words"]
         elif total_extracted_tokens > 0 and remaining_budget > 0:
            target_tokens = msg["tokens"] * (
               remaining_budget / total_extracted_tokens
            )
            target_words = max(20, round(target_tokens / 2.5))
         else:
            target_words = 20

         start_idx = msg["start_line"] - 1
         end_idx = msg["end_line"]
         content = "".join(lines[start_idx:end_idx]).strip()

         entry_path = entries_dir / f"{idx:03d}.md"
         entry_path.write_text(
            f"---\n"
            f"id: {idx}\n"
            f"start_line: {msg['start_line']}\n"
            f"end_line: {msg['end_line']}\n"
            f"tokens: {msg['tokens']}\n"
            f"kind: {msg['kind']}\n"
            f"target_words: {target_words}\n"
            f"---\n\n"
            f"{content}\n"
         )

      # Mock summarize
      mock_summarize_entries(str(entries_dir), apply_mod)

      # Apply
      old_argv = sys.argv
      sys.argv = ["apply-summaries.py", str(md_path), str(entries_dir)]
      try:
         apply_mod.main()
      finally:
         sys.argv = old_argv

      result = md_path.read_text()
      final_tokens = apply_mod.estimate_tokens(result)

      # Verify output is significantly smaller
      assert final_tokens < original_tokens

      # Verify output is under or near 25K tokens (allowing some margin)
      assert final_tokens < 25000, (
         f"Expected under 25K tokens, got {final_tokens}"
      )

      # Verify structural integrity
      assert "=== SESSION RESUME ===" in result
      assert "=== STATISTICS ===" in result
      assert "=== CONVERSATION ===" in result

      # Verify non-summarized lines are intact: check that user messages survive
      # All USER headers should still be present
      original_user_count = original_text.count("--- USER #")
      result_user_count = result.count("--- USER #")
      assert result_user_count == original_user_count, (
         f"User message count changed: {original_user_count} -> {result_user_count}"
      )

      # Verify [Summarized] markers were added
      assert "[Summarized]" in result

   def test_small_transcript_no_summarization_needed(
      self, extract_mod, apply_mod, md_fixture
   ):
      """small_transcript.md (~2K tokens) should NOT need summarization."""
      source_path = md_fixture("small_transcript.md")
      entries, lines = extract_mod.parse_entries(source_path)
      messages = extract_mod.group_into_messages(entries)
      to_summarize, _ = extract_mod.select_messages_to_summarize(messages)

      # All messages are small, nothing should be selected
      assert len(to_summarize) == 0
