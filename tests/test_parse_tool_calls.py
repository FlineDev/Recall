"""Tests for summarize_tool_call(), count_words(), and estimate_tokens()."""

import pytest


# ── count_words ──────────────────────────────────────────────────────────────

class TestCountWords:
   def test_simple(self, parse_mod):
      assert parse_mod.count_words("hello world") == 2

   def test_empty(self, parse_mod):
      assert parse_mod.count_words("") == 0

   def test_multiline(self, parse_mod):
      assert parse_mod.count_words("one\ntwo\nthree four") == 4

   def test_extra_whitespace(self, parse_mod):
      assert parse_mod.count_words("  lots   of   space  ") == 3


# ── estimate_tokens ──────────────────────────────────────────────────────────

class TestEstimateTokens:
   def test_ascii(self, parse_mod):
      text = "a" * 220
      # 220 bytes / 3.0 = 73.3 → int() = 73
      assert parse_mod.estimate_tokens(text) == int(220 / 3.0)

   def test_empty(self, parse_mod):
      assert parse_mod.estimate_tokens("") == 0

   def test_unicode(self, parse_mod):
      # Each ä is 2 UTF-8 bytes, so 10 * 2 = 20 bytes / 3.0 ≈ 6
      text = "ä" * 10
      assert parse_mod.estimate_tokens(text) == int(20 / 3.0)

   def test_bytes_input(self, parse_mod):
      data = b"hello world"  # 11 bytes
      assert parse_mod.estimate_tokens(data) == int(11 / 3.0)


# ── summarize_tool_call ──────────────────────────────────────────────────────

class TestSummarizeToolCall:
   """Parametrized tests for all tool types."""

   # -- Read --
   def test_read_basic(self, parse_mod):
      result = parse_mod.summarize_tool_call("Read", {"file_path": "/tmp/foo.txt"})
      assert result == "Read: /tmp/foo.txt"

   def test_read_with_offset_limit(self, parse_mod):
      result = parse_mod.summarize_tool_call("Read", {
         "file_path": "/tmp/foo.txt",
         "offset": 10,
         "limit": 50,
      })
      assert result == "Read: /tmp/foo.txt offset=10 limit=50"

   def test_read_home_shortening(self, parse_mod):
      result = parse_mod.summarize_tool_call("Read", {
         "file_path": "/home/alex/projects/file.rs",
      })
      assert result == "Read: ~/projects/file.rs"

   # -- Edit --
   def test_edit(self, parse_mod):
      result = parse_mod.summarize_tool_call("Edit", {
         "file_path": "/tmp/bar.rs",
      })
      assert result == "Edit: /tmp/bar.rs"

   def test_edit_home_shortening(self, parse_mod):
      result = parse_mod.summarize_tool_call("Edit", {
         "file_path": "/home/alex/src/main.rs",
      })
      assert result == "Edit: ~/src/main.rs"

   # -- Write --
   def test_write(self, parse_mod):
      result = parse_mod.summarize_tool_call("Write", {
         "file_path": "/tmp/out.txt",
         "content": "hello world",
      })
      assert result == "Write: /tmp/out.txt (11 chars)"

   def test_write_large_content(self, parse_mod):
      result = parse_mod.summarize_tool_call("Write", {
         "file_path": "/tmp/big.txt",
         "content": "x" * 12345,
      })
      assert result == "Write: /tmp/big.txt (12,345 chars)"

   def test_write_no_content(self, parse_mod):
      result = parse_mod.summarize_tool_call("Write", {
         "file_path": "/tmp/empty.txt",
      })
      assert result == "Write: /tmp/empty.txt (0 chars)"

   # -- Bash --
   def test_bash_basic(self, parse_mod):
      result = parse_mod.summarize_tool_call("Bash", {"command": "ls -la"})
      assert result == "Bash: ls -la"

   def test_bash_long_command_truncation(self, parse_mod):
      long_cmd = "echo " + "x" * 300
      result = parse_mod.summarize_tool_call("Bash", {"command": long_cmd})
      # Command truncated to 200 chars
      assert len(result) <= 200 + len("Bash: ")
      assert result.startswith("Bash: echo ")

   def test_bash_background(self, parse_mod):
      result = parse_mod.summarize_tool_call("Bash", {
         "command": "make build",
         "run_in_background": True,
      })
      assert result == "Bash: make build [bg]"

   def test_bash_no_background(self, parse_mod):
      result = parse_mod.summarize_tool_call("Bash", {
         "command": "make build",
         "run_in_background": False,
      })
      assert result == "Bash: make build"

   # -- Agent --
   def test_agent(self, parse_mod):
      result = parse_mod.summarize_tool_call("Agent", {
         "subagent_type": "research",
         "description": "Find all test files",
      })
      assert result == "Agent(research): 'Find all test files'"

   def test_agent_background(self, parse_mod):
      result = parse_mod.summarize_tool_call("Agent", {
         "subagent_type": "task",
         "description": "Run tests",
         "run_in_background": True,
      })
      assert result == "Agent(task): 'Run tests' [bg]"

   # -- Glob --
   def test_glob_no_path(self, parse_mod):
      result = parse_mod.summarize_tool_call("Glob", {"pattern": "**/*.rs"})
      assert result == "Glob: **/*.rs"

   def test_glob_with_path(self, parse_mod):
      result = parse_mod.summarize_tool_call("Glob", {
         "pattern": "*.rs",
         "path": "/home/alex/projects/tasktracker",
      })
      assert result == "Glob: *.rs in ~/projects/tasktracker"

   # -- Grep --
   def test_grep_no_path(self, parse_mod):
      result = parse_mod.summarize_tool_call("Grep", {"pattern": "TODO"})
      assert result == "Grep: 'TODO'"

   def test_grep_with_path(self, parse_mod):
      result = parse_mod.summarize_tool_call("Grep", {
         "pattern": "fn main",
         "path": "/home/alex/projects/tasktracker/src",
      })
      assert result == "Grep: 'fn main' in ~/projects/tasktracker/src"

   # -- Skill --
   def test_skill_no_args(self, parse_mod):
      result = parse_mod.summarize_tool_call("Skill", {"skill": "commit"})
      assert result == "Skill: commit"

   def test_skill_with_args(self, parse_mod):
      result = parse_mod.summarize_tool_call("Skill", {
         "skill": "review-pr",
         "args": "123",
      })
      assert result == "Skill: review-pr 123"

   # -- Task tools --
   def test_task_create(self, parse_mod):
      result = parse_mod.summarize_tool_call("TaskCreate", {
         "subject": "Fix login bug",
      })
      assert result == "TaskCreate: Fix login bug"

   def test_task_update_with_status(self, parse_mod):
      result = parse_mod.summarize_tool_call("TaskUpdate", {
         "taskId": "42",
         "status": "completed",
      })
      assert result == "TaskUpdate: id=42 status=completed"

   def test_task_update_no_status(self, parse_mod):
      result = parse_mod.summarize_tool_call("TaskUpdate", {
         "taskId": "7",
      })
      assert result == "TaskUpdate: id=7"

   def test_task_list(self, parse_mod):
      result = parse_mod.summarize_tool_call("TaskList", {})
      assert result == "TaskList"

   def test_task_get(self, parse_mod):
      result = parse_mod.summarize_tool_call("TaskGet", {"taskId": "5"})
      assert result == "TaskGet: id=5"

   def test_task_output(self, parse_mod):
      result = parse_mod.summarize_tool_call("TaskOutput", {"task_id": "99"})
      assert result == "TaskOutput: id=99"

   def test_task_stop(self, parse_mod):
      result = parse_mod.summarize_tool_call("TaskStop", {"task_id": "12"})
      assert result == "TaskStop: 12"

   # -- AskUserQuestion --
   def test_ask_user_question(self, parse_mod):
      result = parse_mod.summarize_tool_call("AskUserQuestion", {
         "questions": [{"question": "Do you want to proceed?"}],
      })
      assert result == "AskUser: Do you want to proceed?"

   def test_ask_user_question_no_questions(self, parse_mod):
      result = parse_mod.summarize_tool_call("AskUserQuestion", {"questions": []})
      assert result == "AskUser: (no question)"

   def test_ask_user_question_long_truncation(self, parse_mod):
      long_q = "x" * 300
      result = parse_mod.summarize_tool_call("AskUserQuestion", {
         "questions": [{"question": long_q}],
      })
      # Truncated to 150 chars
      assert len(result) <= 150 + len("AskUser: ")

   # -- WebFetch --
   def test_web_fetch(self, parse_mod):
      result = parse_mod.summarize_tool_call("WebFetch", {
         "url": "https://example.com/page",
      })
      assert result == "WebFetch: https://example.com/page"

   def test_web_fetch_long_url(self, parse_mod):
      long_url = "https://example.com/" + "a" * 200
      result = parse_mod.summarize_tool_call("WebFetch", {"url": long_url})
      # URL truncated to 100 chars
      assert len(result) <= 100 + len("WebFetch: ")

   # -- WebSearch --
   def test_web_search(self, parse_mod):
      result = parse_mod.summarize_tool_call("WebSearch", {
         "query": "rust async tutorial",
      })
      assert result == "WebSearch: rust async tutorial"

   def test_web_search_long_query(self, parse_mod):
      long_query = "q" * 200
      result = parse_mod.summarize_tool_call("WebSearch", {"query": long_query})
      assert len(result) <= 100 + len("WebSearch: ")

   # -- Plan mode --
   def test_enter_plan_mode(self, parse_mod):
      result = parse_mod.summarize_tool_call("EnterPlanMode", {})
      assert result == "EnterPlanMode"

   def test_exit_plan_mode(self, parse_mod):
      result = parse_mod.summarize_tool_call("ExitPlanMode", {})
      assert result == "ExitPlanMode"

   # -- ToolSearch --
   def test_tool_search(self, parse_mod):
      result = parse_mod.summarize_tool_call("ToolSearch", {
         "query": "file reading tools",
      })
      assert result == "ToolSearch: file reading tools"

   def test_tool_search_long(self, parse_mod):
      long_q = "z" * 200
      result = parse_mod.summarize_tool_call("ToolSearch", {"query": long_q})
      assert len(result) <= 80 + len("ToolSearch: ")

   # -- Unknown tool (fallback) --
   def test_unknown_tool(self, parse_mod):
      result = parse_mod.summarize_tool_call("NewFancyTool", {
         "alpha": "one",
         "beta": "two",
      })
      assert result.startswith("NewFancyTool(")
      assert "alpha=one" in result
      assert "beta=two" in result

   def test_unknown_tool_truncates_values(self, parse_mod):
      result = parse_mod.summarize_tool_call("BigTool", {
         "data": "x" * 100,
      })
      # Values are truncated to 50 chars
      assert "BigTool(" in result
      assert len(result) < 100

   def test_unknown_tool_max_3_params(self, parse_mod):
      result = parse_mod.summarize_tool_call("ManyParams", {
         "a": "1",
         "b": "2",
         "c": "3",
         "d": "4",
         "e": "5",
      })
      # Only first 3 params shown
      assert result.count("=") <= 3


# ── Parametrized home-dir shortening ─────────────────────────────────────────

@pytest.mark.parametrize("tool_name,inp_key", [
   ("Read", "file_path"),
   ("Edit", "file_path"),
   ("Write", "file_path"),
   ("Glob", "path"),
   ("Grep", "path"),
])
def test_home_dir_shortening(parse_mod, tool_name, inp_key):
   """All tools that accept paths should shorten /home/alex → ~."""
   inp = {inp_key: "/home/alex/deep/nested/file.txt"}
   if tool_name == "Write":
      inp["content"] = "x"
   if tool_name == "Glob":
      inp["pattern"] = "*.txt"
   if tool_name == "Grep":
      inp["pattern"] = "TODO"
   result = parse_mod.summarize_tool_call(tool_name, inp)
   assert "~/deep/nested/file.txt" in result
   assert "/home/alex" not in result
