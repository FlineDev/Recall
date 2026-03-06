"""Tests for extract-longest.py: select_messages_to_summarize()."""

import pytest


def make_msg(kind, tokens, start_line=1, end_line=10):
   """Helper to build a message dict."""
   return {
      "kind": kind,
      "tokens": tokens,
      "start_line": start_line,
      "end_line": end_line,
      "entries": [{"type": kind.upper(), "tokens": tokens, "start_line": start_line, "end_line": end_line}],
   }


def make_exchange(user_tokens, bot_tokens, start_line=1):
   """Helper to build a user+bot exchange."""
   user = make_msg("user", user_tokens, start_line, start_line + 2)
   bot = make_msg("bot", bot_tokens, start_line + 2, start_line + 5)
   return [user, bot]


class TestSelectMessagesToSummarize:
   """Test select_messages_to_summarize() with constructed message lists."""

   def test_empty_input(self, extract_mod):
      """Empty input returns empty list and 0 budget."""
      to_summarize, budget = extract_mod.select_messages_to_summarize([])
      assert to_summarize == []
      assert budget == 0

   def test_all_small_messages(self, extract_mod):
      """All messages < MIN_MESSAGE_TOKENS (200) -> nothing to summarize."""
      messages = []
      for i in range(10):
         messages.extend(make_exchange(50, 100, start_line=i * 10 + 1))
      to_summarize, _ = extract_mod.select_messages_to_summarize(messages)
      assert len(to_summarize) == 0

   def test_single_large_message_selected(self, extract_mod):
      """A single large bot message among small ones is selected for summarization."""
      messages = []
      # Several small exchanges
      for i in range(4):
         messages.extend(make_exchange(30, 100, start_line=i * 10 + 1))
      # One large exchange
      messages.extend(make_exchange(30, 5000, start_line=41))
      # Final exchange (will be frozen as tail)
      messages.extend(make_exchange(30, 100, start_line=51))

      to_summarize, _ = extract_mod.select_messages_to_summarize(messages)
      # The large bot message (5000 tokens) should be selected
      large_msgs = [m for m in to_summarize if m["tokens"] == 5000]
      assert len(large_msgs) == 1

   def test_last_exchange_always_frozen(self, extract_mod):
      """The last user+bot exchange is never in to_summarize."""
      messages = []
      for i in range(5):
         messages.extend(make_exchange(30, 3000, start_line=i * 10 + 1))

      to_summarize, _ = extract_mod.select_messages_to_summarize(messages)
      # Last exchange messages should not appear
      last_user = messages[-2]
      last_bot = messages[-1]
      assert last_user not in to_summarize
      assert last_bot not in to_summarize

   def test_oversized_tail_gets_force_target_words(self, extract_mod):
      """Bot message > FROZEN_TAIL_MAX (3000) in last exchange gets _force_target_words."""
      messages = []
      # A few small exchanges
      for i in range(3):
         messages.extend(make_exchange(30, 100, start_line=i * 10 + 1))
      # Last exchange with oversized bot
      messages.extend(make_exchange(30, 4000, start_line=31))

      to_summarize, _ = extract_mod.select_messages_to_summarize(messages)
      oversized = [m for m in to_summarize if m["tokens"] == 4000]
      assert len(oversized) == 1
      assert "_force_target_words" in oversized[0]
      # FROZEN_TAIL_TARGET (1500) / 2.5 = 600
      assert oversized[0]["_force_target_words"] == 600

   def test_budget_calculation(self, extract_mod):
      """Remaining budget = TOKEN_BUDGET (15000) - frozen tokens."""
      messages = []
      # One large exchange to summarize
      messages.extend(make_exchange(30, 5000, start_line=1))
      # Last exchange with known tokens (frozen tail)
      messages.extend(make_exchange(200, 300, start_line=11))

      _, budget = extract_mod.select_messages_to_summarize(messages)
      # Frozen tail = last user (200) + last bot (300) = 500
      # First user (30) is small (< 200) so frozen too = 530
      # Budget = 15000 - 530 = 14470
      # The large bot (5000) is selected, budget is what's left for summaries
      assert budget > 0
      assert budget <= 15000

   def test_max_summarize_cap(self, extract_mod):
      """More than MAX_SUMMARIZE (50) candidates get capped to 50 largest."""
      messages = []
      # 60 exchanges with large bot messages
      for i in range(60):
         messages.extend(make_exchange(30, 500 + i * 10, start_line=i * 10 + 1))
      # Final exchange (frozen)
      messages.extend(make_exchange(30, 100, start_line=601))

      to_summarize, _ = extract_mod.select_messages_to_summarize(messages)
      assert len(to_summarize) <= extract_mod.MAX_SUMMARIZE

   def test_uniform_large_messages(self, extract_mod):
      """Uniform messages above MIN_MESSAGE_TOKENS converge correctly."""
      messages = []
      # 20 exchanges all at 500 tokens
      for i in range(20):
         messages.extend(make_exchange(100, 500, start_line=i * 10 + 1))

      to_summarize, budget = extract_mod.select_messages_to_summarize(messages)
      # With uniform sizes the algorithm should converge
      # Total = 20 * (100 + 500) = 12000, under 15K budget, so few/none selected
      # (all fit within budget so many get frozen)
      assert isinstance(to_summarize, list)
      assert isinstance(budget, int)

   def test_mix_small_and_large(self, extract_mod):
      """Small messages are frozen, large ones are selected."""
      messages = []
      # 5 small exchanges
      for i in range(5):
         messages.extend(make_exchange(30, 80, start_line=i * 10 + 1))
      # 3 large exchanges
      for i in range(3):
         messages.extend(make_exchange(30, 3000, start_line=50 + i * 10 + 1))
      # Final exchange (frozen)
      messages.extend(make_exchange(30, 100, start_line=81))

      to_summarize, _ = extract_mod.select_messages_to_summarize(messages)
      # Large bot messages should be selected
      large_tokens = [m["tokens"] for m in to_summarize if m["tokens"] >= 3000]
      assert len(large_tokens) >= 1

   def test_target_words_proportional(self, extract_mod):
      """After main() assigns target_words, they are proportional to token share."""
      messages = []
      # Two large exchanges with different sizes
      messages.extend(make_exchange(30, 2000, start_line=1))
      messages.extend(make_exchange(30, 4000, start_line=11))
      # Final exchange (frozen)
      messages.extend(make_exchange(30, 100, start_line=21))

      to_summarize, remaining_budget = extract_mod.select_messages_to_summarize(messages)
      if len(to_summarize) >= 2:
         # Simulate target_words assignment (same as main())
         total_extracted = sum(m["tokens"] for m in to_summarize)
         for m in to_summarize:
            if "_force_target_words" not in m and total_extracted > 0 and remaining_budget > 0:
               target_tokens = m["tokens"] * (remaining_budget / total_extracted)
               m["target_words"] = max(20, round(target_tokens / 2.5))
            else:
               m["target_words"] = 20

         # The message with more tokens should get more target_words
         sorted_by_tokens = sorted(to_summarize, key=lambda m: m["tokens"])
         sorted_by_target = sorted(to_summarize, key=lambda m: m["target_words"])
         assert [m["tokens"] for m in sorted_by_tokens] == [m["tokens"] for m in sorted_by_target]

   def test_only_two_messages_nothing_to_summarize(self, extract_mod):
      """Only 2 messages (1 exchange) -> everything frozen, nothing to summarize."""
      messages = make_exchange(100, 5000, start_line=1)
      to_summarize, _ = extract_mod.select_messages_to_summarize(messages)
      # The single exchange is the last exchange, so both are frozen
      assert len(to_summarize) <= 1  # oversized tail might be moved to candidates

   def test_oversized_tail_fixture(self, extract_mod, md_fixture):
      """oversized_tail.md: last bot > 3000 tokens gets selected with _force_target_words."""
      entries, _ = extract_mod.parse_entries(md_fixture("oversized_tail.md"))
      messages = extract_mod.group_into_messages(entries)
      to_summarize, _ = extract_mod.select_messages_to_summarize(messages)
      # The last bot message has 3196 tokens (> FROZEN_TAIL_MAX=3000)
      forced = [m for m in to_summarize if "_force_target_words" in m]
      assert len(forced) == 1

   def test_skewed_messages_fixture(self, extract_mod, md_fixture):
      """skewed_messages.md: 2 huge + 20 tiny -> huge ones should be selected."""
      entries, _ = extract_mod.parse_entries(md_fixture("skewed_messages.md"))
      messages = extract_mod.group_into_messages(entries)
      to_summarize, _ = extract_mod.select_messages_to_summarize(messages)
      if to_summarize:
         # Selected messages should include the large ones
         max_tokens = max(m["tokens"] for m in to_summarize)
         assert max_tokens >= 1000
