#!/usr/bin/env python3
"""Generate synthetic test fixtures for the Recall plugin.

All fixtures use a fictional 'TaskTracker' Rust CLI project.
No personal data — safe for public repository.

Usage: python3 generate_fixtures.py
"""
import json
import os
import uuid
import random
import textwrap

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
JSONL_DIR = os.path.join(FIXTURES_DIR, "jsonl")
MD_DIR = os.path.join(FIXTURES_DIR, "markdown")

BASE_TIME = "2026-01-15T10:00:"
PROJECT_DIR = "/home/alex/projects/tasktracker"
SESSION_ID = "test-session-001"

# Counter for unique UUIDs
_uuid_counter = 0


def next_uuid():
   global _uuid_counter
   _uuid_counter += 1
   return f"00000000-0000-0000-0000-{_uuid_counter:012d}"


def ts(minute, second=0):
   return f"2026-01-15T10:{minute:02d}:{second:02d}"


def user_msg(text, minute, content_override=None):
   return {
      "type": "user",
      "message": {
         "role": "user",
         "content": content_override if content_override is not None else text,
      },
      "cwd": PROJECT_DIR,
      "gitBranch": "main",
      "timestamp": ts(minute),
      "permissionMode": "default",
      "sessionId": SESSION_ID,
      "uuid": next_uuid(),
   }


def assistant_msg(text, minute, tool_calls=None):
   content = []
   if text:
      content.append({"type": "text", "text": text})
   if tool_calls:
      for tc in tool_calls:
         content.append(tc)
   return {
      "type": "assistant",
      "message": {
         "role": "assistant",
         "content": content,
         "stop_reason": "end_turn",
      },
      "uuid": next_uuid(),
      "timestamp": ts(minute, 5),
   }


def tool_use(name, input_data, tool_id=None):
   return {
      "type": "tool_use",
      "id": tool_id or f"toolu_{next_uuid().replace('-', '')[:20]}",
      "name": name,
      "input": input_data,
   }


def file_history_snapshot(minute):
   uid = next_uuid()
   return {
      "type": "file-history-snapshot",
      "messageId": uid,
      "snapshot": {
         "messageId": uid,
         "trackedFileBackups": {},
         "timestamp": ts(minute),
      },
   }


def progress_entry(elapsed=2):
   return {
      "type": "progress",
      "data": {
         "type": "bash_progress",
         "output": "",
         "elapsedTimeSeconds": elapsed,
      },
   }


def compact_boundary(pre_tokens=50000):
   return {
      "type": "system",
      "subtype": "compact_boundary",
      "compactMetadata": {"trigger": "auto", "preTokens": pre_tokens},
   }


def summary_entry(text):
   return {"type": "summary", "summary": text}


def write_jsonl(filename, entries):
   path = os.path.join(JSONL_DIR, filename)
   with open(path, "w") as f:
      for entry in entries:
         f.write(json.dumps(entry) + "\n")
   print(f"  Written: {path} ({len(entries)} entries)")


def write_md(filename, content):
   path = os.path.join(MD_DIR, filename)
   with open(path, "w") as f:
      f.write(content)
   print(f"  Written: {path}")


# ── Rust code snippets for realistic content ──

MAIN_RS = textwrap.dedent("""\
   use clap::{Parser, Subcommand};
   mod commands;
   mod models;

   #[derive(Parser)]
   #[command(name = "tasktracker", version, about = "A CLI task manager")]
   struct Cli {
       #[command(subcommand)]
       command: Commands,
   }

   #[derive(Subcommand)]
   enum Commands {
       Add { title: String, #[arg(short, long)] priority: Option<u8> },
       List { #[arg(short, long)] all: bool },
       Complete { id: u32 },
       Delete { id: u32 },
   }

   fn main() {
       let cli = Cli::parse();
       match cli.command {
           Commands::Add { title, priority } => commands::add::run(title, priority),
           Commands::List { all } => commands::list::run(all),
           Commands::Complete { id } => commands::complete::run(id),
           Commands::Delete { id } => commands::delete::run(id),
       }
   }""")

TASK_MODEL_RS = textwrap.dedent("""\
   use chrono::NaiveDate;
   use serde::{Deserialize, Serialize};

   #[derive(Debug, Clone, Serialize, Deserialize)]
   pub struct Task {
       pub id: u32,
       pub title: String,
       pub completed: bool,
       pub priority: u8,
       pub due_date: Option<NaiveDate>,
       pub tags: Vec<String>,
       pub created_at: NaiveDate,
   }

   impl Task {
       pub fn new(id: u32, title: String, priority: u8) -> Self {
           Self {
               id,
               title,
               completed: false,
               priority,
               due_date: None,
               tags: Vec::new(),
               created_at: chrono::Local::now().date_naive(),
           }
       }

       pub fn matches_filter(&self, filter: &str) -> bool {
           self.title.to_lowercase().contains(&filter.to_lowercase())
               || self.tags.iter().any(|t| t.to_lowercase().contains(&filter.to_lowercase()))
       }
   }""")

FILTER_RS = textwrap.dedent("""\
   use crate::models::task::Task;
   use crate::storage;

   pub fn run(query: Option<String>, tag: Option<String>, priority: Option<u8>, show_completed: bool) {
       let tasks = storage::load_tasks().expect("Failed to load tasks");
       let filtered: Vec<&Task> = tasks.iter()
           .filter(|t| show_completed || !t.completed)
           .filter(|t| match &query {
               Some(q) => t.matches_filter(q),
               None => true,
           })
           .filter(|t| match &tag {
               Some(tag) => t.tags.contains(tag),
               None => true,
           })
           .filter(|t| match priority {
               Some(p) => t.priority >= p,
               None => true,
           })
           .collect();

       if filtered.is_empty() {
           println!("No tasks match the given filters.");
           return;
       }

       println!("Found {} task(s):", filtered.len());
       for task in &filtered {
           let status = if task.completed { "✓" } else { "○" };
           println!("  {} [{}] {} (priority: {})", status, task.id, task.title, task.priority);
       }
   }""")

CARGO_TOML = textwrap.dedent("""\
   [package]
   name = "tasktracker"
   version = "0.3.0"
   edition = "2021"

   [dependencies]
   clap = { version = "4.5", features = ["derive"] }
   serde = { version = "1.0", features = ["derive"] }
   serde_json = "1.0"
   chrono = { version = "0.4", features = ["serde"] }
   directories = "5.0"
   """)


# ═══════════════════════════════════════════════════════════
# JSONL Fixture Generators
# ═══════════════════════════════════════════════════════════


def gen_f01_tiny():
   """F01: 2 exchanges — add --verbose flag."""
   entries = [
      file_history_snapshot(0),
      user_msg("Add a --verbose flag to the list command that shows task details including due date and tags.", 0),
      assistant_msg(
         "I'll add the --verbose flag to the list command. Let me first check the current implementation.",
         0,
         [
            tool_use("Read", {"file_path": f"{PROJECT_DIR}/src/main.rs"}),
         ],
      ),
      user_msg("Looks good, please go ahead with the implementation.", 1),
      assistant_msg(
         "I've added the `--verbose` flag to the `List` subcommand. When enabled, it displays the due date, tags, and creation date alongside each task. The default output remains concise with just the status, ID, title, and priority.",
         1,
         [
            tool_use("Edit", {
               "file_path": f"{PROJECT_DIR}/src/main.rs",
               "old_string": 'List { #[arg(short, long)] all: bool }',
               "new_string": 'List { #[arg(short, long)] all: bool, #[arg(short, long)] verbose: bool }',
            }),
            tool_use("Edit", {
               "file_path": f"{PROJECT_DIR}/src/commands/list.rs",
               "old_string": "pub fn run(all: bool)",
               "new_string": "pub fn run(all: bool, verbose: bool)",
            }),
         ],
      ),
   ]
   write_jsonl("tiny_session.jsonl", entries)


def gen_f02_short():
   """F02: 5 exchanges — bug fix for date parsing."""
   entries = [
      file_history_snapshot(0),
      user_msg("There's a panic when I run `tasktracker add 'Buy groceries' --due 2026-13-01`. It should show a friendly error instead of crashing.", 0),
      assistant_msg(
         "That's a date validation issue — month 13 is invalid and likely causes an unwrap() panic. Let me find where dates are parsed.",
         0,
         [
            tool_use("Grep", {"pattern": "parse.*date|NaiveDate|unwrap", "path": f"{PROJECT_DIR}/src"}),
         ],
      ),
      user_msg("Yes, it panics at src/commands/add.rs line 15 with `unwrap()`.", 2),
      assistant_msg(
         "Found it. The `add` command parses the due date with `NaiveDate::parse_from_str().unwrap()`, which panics on invalid dates. I'll replace it with proper error handling using a match expression.",
         2,
         [
            tool_use("Read", {"file_path": f"{PROJECT_DIR}/src/commands/add.rs"}),
            tool_use("Edit", {
               "file_path": f"{PROJECT_DIR}/src/commands/add.rs",
               "old_string": 'let due = NaiveDate::parse_from_str(&date_str, "%Y-%m-%d").unwrap();',
               "new_string": 'let due = match NaiveDate::parse_from_str(&date_str, "%Y-%m-%d") {\n        Ok(d) => d,\n        Err(e) => {\n            eprintln!("Error: Invalid date \'{}\': {}", date_str, e);\n            std::process::exit(1);\n        }\n    };',
            }),
         ],
      ),
      user_msg("Can you add a test for this?", 4),
      assistant_msg(
         "I'll add an integration test that verifies the error message for invalid dates and ensures the process exits with a non-zero status code.",
         4,
         [
            tool_use("Edit", {
               "file_path": f"{PROJECT_DIR}/tests/integration_test.rs",
               "old_string": "// end of tests",
               "new_string": '#[test]\nfn test_invalid_date_shows_error() {\n    let output = Command::new("cargo")\n        .args(["run", "--", "add", "Test", "--due", "2026-13-01"])\n        .output()\n        .expect("Failed to run");\n    assert!(!output.status.success());\n    let stderr = String::from_utf8_lossy(&output.stderr);\n    assert!(stderr.contains("Invalid date"));\n}\n// end of tests',
            }),
         ],
      ),
      user_msg("Run the tests to make sure everything passes.", 6),
      assistant_msg(
         "All 12 tests pass, including the new `test_invalid_date_shows_error`. The fix correctly handles invalid dates by printing a user-friendly error message and exiting with status code 1 instead of panicking.",
         6,
         [
            tool_use("Bash", {"command": "cd /home/alex/projects/tasktracker && cargo test"}),
         ],
      ),
      user_msg("Great, please commit this fix.", 8),
      assistant_msg(
         "Done. I've committed the date validation fix with the test.",
         8,
         [
            tool_use("Bash", {"command": 'cd /home/alex/projects/tasktracker && git add -A && git commit -m "Fix panic on invalid date input in add command"'}),
         ],
      ),
   ]
   write_jsonl("short_session.jsonl", entries)


def gen_f03_medium():
   """F03: 20 exchanges — implementing filter subcommand."""
   entries = [file_history_snapshot(0)]
   m = 0

   # Exchange 1
   entries.append(user_msg("I want to add a `filter` subcommand to TaskTracker. It should support filtering by text query, tag, priority level, and optionally show completed tasks.", m))
   m += 1
   entries.append(assistant_msg(
      "That's a great feature to add. Let me explore the current codebase structure to understand how existing commands are organized, then I'll implement the filter subcommand step by step.",
      m,
      [
         tool_use("Glob", {"pattern": "src/**/*.rs", "path": PROJECT_DIR}),
         tool_use("Read", {"file_path": f"{PROJECT_DIR}/src/main.rs"}),
      ],
   ))

   # Exchange 2
   m += 1
   entries.append(user_msg("The commands are in src/commands/ with one file per command.", m))
   entries.append(assistant_msg(
      "Perfect, I can see the pattern. Each command has its own module file with a `run` function. Let me check the Task model to understand what fields are available for filtering.",
      m,
      [
         tool_use("Read", {"file_path": f"{PROJECT_DIR}/src/models/task.rs"}),
         tool_use("Read", {"file_path": f"{PROJECT_DIR}/src/commands/list.rs"}),
      ],
   ))

   # Exchange 3
   m += 1
   entries.append(user_msg("Yes, the Task struct has title, completed, priority, due_date, tags, and created_at fields.", m))
   entries.append(assistant_msg(
      "Great. I'll start by adding the Filter variant to the Commands enum in main.rs. The filter command will accept optional arguments for query text, tag name, minimum priority, and a flag to include completed tasks.",
      m,
      [
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/main.rs",
            "old_string": "Delete { id: u32 },",
            "new_string": 'Delete { id: u32 },\n    Filter {\n        #[arg(short, long)]\n        query: Option<String>,\n        #[arg(short, long)]\n        tag: Option<String>,\n        #[arg(short, long)]\n        priority: Option<u8>,\n        #[arg(long)]\n        show_completed: bool,\n    },',
         }),
      ],
   ))

   # Exchange 4
   m += 1
   entries.append(user_msg("Now add the match arm for Filter in main().", m))
   entries.append(assistant_msg(
      "Adding the match arm that routes to the filter command module. I'll also need to add the module declaration.",
      m,
      [
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/main.rs",
            "old_string": "Commands::Delete { id } => commands::delete::run(id),",
            "new_string": "Commands::Delete { id } => commands::delete::run(id),\n        Commands::Filter { query, tag, priority, show_completed } => commands::filter::run(query, tag, priority, show_completed),",
         }),
      ],
   ))

   # Exchange 5
   m += 1
   entries.append(user_msg("Create the filter module now.", m))
   entries.append(assistant_msg(
      "I'll create the filter command module. It loads all tasks from storage, applies the filters in sequence (text query, tag, priority, completion status), and displays matching results with a count summary.",
      m,
      [
         tool_use("Write", {
            "file_path": f"{PROJECT_DIR}/src/commands/filter.rs",
            "content": FILTER_RS,
         }),
      ],
   ))

   # Exchange 6
   m += 1
   entries.append(user_msg("We need to add `matches_filter` to the Task model too.", m))
   entries.append(assistant_msg(
      "Right, the `matches_filter` method needs to be on the Task struct. It should search both the title and tags for case-insensitive matches. Let me add that implementation.",
      m,
      [
         tool_use("Read", {"file_path": f"{PROJECT_DIR}/src/models/task.rs"}),
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/models/task.rs",
            "old_string": "created_at: chrono::Local::now().date_naive(),\n        }\n    }\n}",
            "new_string": 'created_at: chrono::Local::now().date_naive(),\n        }\n    }\n\n    pub fn matches_filter(&self, filter: &str) -> bool {\n        self.title.to_lowercase().contains(&filter.to_lowercase())\n            || self.tags.iter().any(|t| t.to_lowercase().contains(&filter.to_lowercase()))\n    }\n}',
         }),
      ],
   ))

   # Exchange 7
   m += 1
   entries.append(user_msg("Register the module in commands/mod.rs.", m))
   entries.append(assistant_msg(
      "Adding the filter module declaration to the commands module.",
      m,
      [
         tool_use("Read", {"file_path": f"{PROJECT_DIR}/src/commands/mod.rs"}),
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/commands/mod.rs",
            "old_string": "pub mod delete;",
            "new_string": "pub mod delete;\npub mod filter;",
         }),
      ],
   ))

   # Exchange 8
   m += 1
   entries.append(user_msg("Let's try building it.", m))
   entries.append(assistant_msg(
      "Running cargo build to check for compilation errors. There might be some issues with imports or type mismatches that we need to fix.",
      m,
      [tool_use("Bash", {"command": f"cd {PROJECT_DIR} && cargo build 2>&1"})],
   ))

   # Exchange 9
   m += 1
   entries.append(user_msg("There's a compile error about the storage module not being found in filter.rs.", m))
   entries.append(assistant_msg(
      "The storage module path needs to use `crate::storage` since filter.rs is inside the commands submodule. Let me check how other command files import it and fix the path.",
      m,
      [
         tool_use("Read", {"file_path": f"{PROJECT_DIR}/src/commands/add.rs"}),
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/commands/filter.rs",
            "old_string": "use crate::storage;",
            "new_string": "use crate::storage;\nuse crate::models::task::Task;",
         }),
      ],
   ))

   # Exchange 10
   m += 1
   entries.append(user_msg("Build again.", m))
   entries.append(assistant_msg(
      "The build succeeds now. No warnings from clippy either. Let me run the existing test suite to make sure the new code doesn't break anything.",
      m,
      [
         tool_use("Bash", {"command": f"cd {PROJECT_DIR} && cargo build 2>&1 && cargo clippy 2>&1"}),
      ],
   ))

   # Exchange 11
   m += 1
   entries.append(user_msg("Now let's write tests for the filter command.", m))
   entries.append(assistant_msg(
      "I'll add unit tests for the `matches_filter` method first, then integration tests for the filter subcommand. The unit tests will cover case-insensitive matching, tag matching, and edge cases like empty strings.",
      m,
      [
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/models/task.rs",
            "old_string": "// end of file",
            "new_string": '#[cfg(test)]\nmod tests {\n    use super::*;\n\n    #[test]\n    fn test_matches_filter_by_title() {\n        let task = Task::new(1, "Buy groceries".to_string(), 1);\n        assert!(task.matches_filter("groceries"));\n        assert!(task.matches_filter("GROCERIES"));\n        assert!(!task.matches_filter("laundry"));\n    }\n\n    #[test]\n    fn test_matches_filter_by_tag() {\n        let mut task = Task::new(2, "Review PR".to_string(), 2);\n        task.tags = vec!["work".to_string(), "urgent".to_string()];\n        assert!(task.matches_filter("work"));\n        assert!(task.matches_filter("URGENT"));\n        assert!(!task.matches_filter("personal"));\n    }\n\n    #[test]\n    fn test_matches_filter_empty_string() {\n        let task = Task::new(3, "Any task".to_string(), 1);\n        assert!(task.matches_filter(""));\n    }\n}\n// end of file',
         }),
      ],
   ))

   # Exchange 12
   m += 1
   entries.append(user_msg("Add integration tests too.", m))
   entries.append(assistant_msg(
      "I'll add integration tests that exercise the filter subcommand end-to-end. These tests will set up sample tasks, run the filter command with various arguments, and verify the output contains the expected results.",
      m,
      [
         tool_use("Read", {"file_path": f"{PROJECT_DIR}/tests/integration_test.rs"}),
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/tests/integration_test.rs",
            "old_string": "// end of tests",
            "new_string": '#[test]\nfn test_filter_by_query() {\n    setup_test_tasks();\n    let output = run_cmd(&["filter", "--query", "groceries"]);\n    assert!(output.contains("Buy groceries"));\n    assert!(!output.contains("Review PR"));\n}\n\n#[test]\nfn test_filter_by_tag() {\n    setup_test_tasks();\n    let output = run_cmd(&["filter", "--tag", "work"]);\n    assert!(output.contains("Review PR"));\n    assert!(!output.contains("Buy groceries"));\n}\n\n#[test]\nfn test_filter_by_priority() {\n    setup_test_tasks();\n    let output = run_cmd(&["filter", "--priority", "3"]);\n    assert!(output.contains("Deploy release"));\n    assert!(!output.contains("Buy groceries"));\n}\n\n#[test]\nfn test_filter_no_matches() {\n    setup_test_tasks();\n    let output = run_cmd(&["filter", "--query", "nonexistent"]);\n    assert!(output.contains("No tasks match"));\n}\n// end of tests',
         }),
      ],
   ))

   # Exchange 13
   m += 1
   entries.append(user_msg("Run all tests.", m))
   entries.append(assistant_msg(
      "Running the full test suite including the new unit tests and integration tests for the filter command.",
      m,
      [tool_use("Bash", {"command": f"cd {PROJECT_DIR} && cargo test 2>&1"})],
   ))

   # Exchange 14
   m += 1
   entries.append(user_msg("All tests pass. Can you also add a --sort flag to the filter command? Sort by priority, date, or title.", m))
   entries.append(assistant_msg(
      "Good idea. I'll add a `--sort` option that accepts `priority`, `date`, or `title` as values. I'll use a clap ValueEnum for the sort options and implement the sorting logic after filtering. Default will be by priority descending.",
      m,
      [
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/main.rs",
            "old_string": "show_completed: bool,\n    },",
            "new_string": 'show_completed: bool,\n        #[arg(short, long, value_enum, default_value = "priority")]\n        sort: SortField,\n    },',
         }),
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/main.rs",
            "old_string": "#[derive(Subcommand)]",
            "new_string": '#[derive(Clone, clap::ValueEnum)]\nenum SortField {\n    Priority,\n    Date,\n    Title,\n}\n\n#[derive(Subcommand)]',
         }),
      ],
   ))

   # Exchange 15
   m += 1
   entries.append(user_msg("Update the filter module to accept the sort field.", m))
   entries.append(assistant_msg(
      "I'll update the filter module's `run` function to accept a sort parameter and apply sorting to the filtered results. Priority sorts descending (highest first), date sorts ascending (earliest first), and title sorts alphabetically.",
      m,
      [
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/commands/filter.rs",
            "old_string": "pub fn run(query: Option<String>, tag: Option<String>, priority: Option<u8>, show_completed: bool) {",
            "new_string": "pub fn run(query: Option<String>, tag: Option<String>, priority: Option<u8>, show_completed: bool, sort: crate::SortField) {",
         }),
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/commands/filter.rs",
            "old_string": '    if filtered.is_empty() {',
            "new_string": '    let mut filtered = filtered;\n    match sort {\n        crate::SortField::Priority => filtered.sort_by(|a, b| b.priority.cmp(&a.priority)),\n        crate::SortField::Date => filtered.sort_by(|a, b| a.created_at.cmp(&b.created_at)),\n        crate::SortField::Title => filtered.sort_by(|a, b| a.title.cmp(&b.title)),\n    }\n\n    if filtered.is_empty() {',
         }),
      ],
   ))

   # Exchange 16
   m += 1
   entries.append(user_msg("Update the match arm in main too.", m))
   entries.append(assistant_msg(
      "Right, the match arm needs to pass the sort field to the filter command's run function.",
      m,
      [
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/main.rs",
            "old_string": "Commands::Filter { query, tag, priority, show_completed } => commands::filter::run(query, tag, priority, show_completed),",
            "new_string": "Commands::Filter { query, tag, priority, show_completed, sort } => commands::filter::run(query, tag, priority, show_completed, sort),",
         }),
      ],
   ))

   # Exchange 17
   m += 1
   entries.append(user_msg("Build and test again.", m))
   entries.append(assistant_msg(
      "Building and running the full test suite to verify the sort functionality compiles correctly and all existing tests still pass.",
      m,
      [
         tool_use("Bash", {"command": f"cd {PROJECT_DIR} && cargo build 2>&1 && cargo test 2>&1"}),
      ],
   ))

   # Exchange 18
   m += 1
   entries.append(user_msg("Nice, all passing. Let's format and run clippy one more time before committing.", m))
   entries.append(assistant_msg(
      "Running cargo fmt to ensure consistent formatting, then clippy for lint checks. This catches any style issues or potential bugs before we commit.",
      m,
      [
         tool_use("Bash", {"command": f"cd {PROJECT_DIR} && cargo fmt && cargo clippy -- -W clippy::all 2>&1"}),
      ],
   ))

   # Exchange 19
   m += 1
   entries.append(user_msg("Commit everything with a descriptive message.", m))
   entries.append(assistant_msg(
      "I'll stage all the changed files and create a commit with a clear description of what was added. The commit covers the filter subcommand, the matches_filter method on Task, unit tests, integration tests, and the sort option.",
      m,
      [
         tool_use("Bash", {"command": f"cd {PROJECT_DIR} && git add -A && git status"}),
         tool_use("Bash", {"command": f'cd {PROJECT_DIR} && git commit -m "Add filter subcommand with query, tag, priority filtering and sort options"'}),
      ],
   ))

   # Exchange 20
   m += 1
   entries.append(user_msg("Thanks! The filter command works perfectly.", m))
   entries.append(assistant_msg(
      "You're welcome! The filter subcommand is now fully functional with four filter criteria (text query, tag, minimum priority, and completion status) plus three sort options (priority, date, title). The implementation includes comprehensive unit tests for the matching logic and integration tests for the CLI interface. Let me know if you'd like to add any additional features like date range filtering or output format options.",
      m,
   ))

   write_jsonl("medium_session.jsonl", entries)


def gen_f04_long_autonomous():
   """F04: 1 user message + 40 consecutive assistant messages — async/await refactor."""
   entries = [file_history_snapshot(0)]

   entries.append(user_msg(
      "Refactor the entire codebase to use async/await with tokio. All file I/O and command handlers should be async. Update Cargo.toml, all command modules, the storage layer, and main.rs. Run tests after each major change.",
      0,
   ))

   files_to_refactor = [
      ("Cargo.toml", "Adding tokio and async dependencies to Cargo.toml."),
      ("src/main.rs", "Converting main() to #[tokio::main] async fn main(). Each command handler call now uses .await."),
      ("src/storage/mod.rs", "Making the storage module async. The load_tasks and save_tasks functions now use tokio::fs for file I/O operations."),
      ("src/models/task.rs", "Adding async serialization helpers to the Task model. The serde operations are wrapped in spawn_blocking for CPU-bound work."),
      ("src/commands/add.rs", "Converting the add command to async. Task creation and storage calls use .await syntax."),
      ("src/commands/list.rs", "Converting the list command to async. Task loading is now non-blocking."),
      ("src/commands/complete.rs", "Converting the complete command to async. Both load and save operations use .await."),
      ("src/commands/delete.rs", "Converting the delete command to async. Error handling now uses async-compatible patterns with ? operator."),
      ("src/commands/filter.rs", "Converting the filter command to async. The filtering logic itself remains synchronous but the I/O is async."),
      ("src/commands/mod.rs", "Updating module declarations. No signature changes needed here, just ensuring re-exports work correctly."),
   ]

   m = 1
   # Phase 1: Read all files (10 assistant messages)
   for filepath, desc in files_to_refactor:
      full_path = f"{PROJECT_DIR}/{filepath}"
      entries.append(assistant_msg(
         f"Let me read {filepath} to understand the current implementation before making it async. {desc}",
         m,
         [tool_use("Read", {"file_path": full_path})],
      ))
      m += 1

   # Phase 2: Edit files (10 assistant messages)
   for filepath, desc in files_to_refactor:
      full_path = f"{PROJECT_DIR}/{filepath}"
      entries.append(assistant_msg(
         f"Now refactoring {filepath} to use async/await. {desc} This involves changing function signatures, adding .await to I/O calls, and updating error handling to work with async contexts.",
         m,
         [tool_use("Edit", {
            "file_path": full_path,
            "old_string": f"// placeholder for {filepath}",
            "new_string": f"// async refactored: {filepath}",
         })],
      ))
      m += 1

   # Phase 3: Build and fix (10 assistant messages with Bash)
   for i in range(10):
      if i < 5:
         entries.append(assistant_msg(
            f"Build attempt {i+1}. Checking for compilation errors after the async migration. If there are issues, they're likely related to missing .await calls or lifetime mismatches with async closures.",
            m,
            [tool_use("Bash", {"command": f"cd {PROJECT_DIR} && cargo build 2>&1 | head -50"})],
         ))
      else:
         entries.append(assistant_msg(
            f"Running test batch {i-4}. Verifying that the async refactoring preserves the existing behavior. All command handlers should produce identical output to their synchronous versions.",
            m,
            [tool_use("Bash", {"command": f"cd {PROJECT_DIR} && cargo test 2>&1"})],
         ))
      m += 1

   # Phase 4: More fixes and tests (10 assistant messages)
   test_files = [
      "tests/integration_test.rs",
      "tests/storage_test.rs",
      "tests/filter_test.rs",
      "tests/add_test.rs",
      "tests/complete_test.rs",
   ]
   for i in range(10):
      if i < 5:
         tf = test_files[i]
         entries.append(assistant_msg(
            f"Updating {tf} to use async test functions with #[tokio::test]. The test assertions remain the same but the setup and teardown are now async. This ensures our tests properly exercise the async code paths.",
            m,
            [
               tool_use("Read", {"file_path": f"{PROJECT_DIR}/{tf}"}),
               tool_use("Edit", {
                  "file_path": f"{PROJECT_DIR}/{tf}",
                  "old_string": "#[test]",
                  "new_string": "#[tokio::test]",
               }),
            ],
         ))
      elif i == 5:
         entries.append(assistant_msg(
            "Running the full test suite one final time to confirm everything passes after the async migration. All 24 tests should pass including the updated integration tests.",
            m,
            [tool_use("Bash", {"command": f"cd {PROJECT_DIR} && cargo test 2>&1"})],
         ))
      elif i == 6:
         entries.append(assistant_msg(
            "Running clippy to ensure the async code follows Rust best practices. Common async clippy warnings include unnecessary async blocks and redundant .await on non-async functions.",
            m,
            [tool_use("Bash", {"command": f"cd {PROJECT_DIR} && cargo clippy -- -W clippy::all 2>&1"})],
         ))
      elif i == 7:
         entries.append(assistant_msg(
            "Formatting all source files with cargo fmt to ensure consistent style after the refactoring. The async/await syntax can sometimes cause long lines that need reformatting.",
            m,
            [tool_use("Bash", {"command": f"cd {PROJECT_DIR} && cargo fmt"})],
         ))
      elif i == 8:
         entries.append(assistant_msg(
            "Staging all changes and reviewing the diff to make sure nothing was missed in the async migration. The diff should show consistent patterns across all command modules.",
            m,
            [
               tool_use("Bash", {"command": f"cd {PROJECT_DIR} && git add -A && git diff --cached --stat"}),
            ],
         ))
      else:
         entries.append(assistant_msg(
            "The async/await refactoring is complete. All 10 source files have been migrated to use tokio for async I/O. The key changes were: (1) Added tokio dependency with full features to Cargo.toml, (2) Converted all command handlers to async functions, (3) Made storage layer use tokio::fs for non-blocking file operations, (4) Updated main() to use #[tokio::main], (5) Migrated all 24 tests to use #[tokio::test]. All tests pass and clippy reports no warnings.",
            m,
            [tool_use("Bash", {"command": f'cd {PROJECT_DIR} && git commit -m "Refactor entire codebase to async/await with tokio"'})],
         ))
      m += 1

   write_jsonl("long_autonomous.jsonl", entries)


def gen_f05_multi_compaction():
   """F05: 3 compact_boundary markers with summary messages after each."""
   entries = [file_history_snapshot(0)]

   # Segment 1
   entries.append(user_msg("Add a priority field to the Task struct.", 0))
   entries.append(assistant_msg("I'll add a priority field (u8) to the Task struct in models/task.rs.", 0,
      [tool_use("Edit", {"file_path": f"{PROJECT_DIR}/src/models/task.rs", "old_string": "pub title: String,", "new_string": "pub title: String,\n    pub priority: u8,"})]))
   entries.append(user_msg("Good, now update the add command to accept --priority.", 2))
   entries.append(assistant_msg("Updated the add command with a --priority flag defaulting to 1.", 2,
      [tool_use("Edit", {"file_path": f"{PROJECT_DIR}/src/commands/add.rs", "old_string": "title: String", "new_string": "title: String, priority: Option<u8>"})]))

   # First compaction
   entries.append(compact_boundary(45000))
   entries.append(summary_entry("Added priority field to Task struct and --priority flag to add command."))
   entries.append(user_msg("This session is being continued from a previous conversation that ran out of context. Here is a summary of what was discussed: We added a priority field to the Task struct and a --priority flag to the add command. The user now wants to continue with sorting by priority.", 4))
   entries.append(assistant_msg("I see the priority field was added. Let me check the current state of the code and add priority-based sorting to the list command.", 4,
      [tool_use("Read", {"file_path": f"{PROJECT_DIR}/src/commands/list.rs"})]))

   # Segment 2
   entries.append(user_msg("Sort tasks by priority in the list output.", 6))
   entries.append(assistant_msg("I'll sort the tasks vector by priority in descending order before displaying them, so high-priority tasks appear first.", 6,
      [tool_use("Edit", {"file_path": f"{PROJECT_DIR}/src/commands/list.rs", "old_string": "for task in &tasks {", "new_string": "tasks.sort_by(|a, b| b.priority.cmp(&a.priority));\n    for task in &tasks {"})]))
   entries.append(user_msg("Add color coding for different priority levels.", 8))
   entries.append(assistant_msg("I'll use the colored crate to add red for high priority (3+), yellow for medium (2), and default for low (1).", 8,
      [tool_use("Edit", {"file_path": f"{PROJECT_DIR}/Cargo.toml", "old_string": '[dependencies]', "new_string": '[dependencies]\ncolored = "2.1"'})]))

   # Second compaction
   entries.append(compact_boundary(48000))
   entries.append(summary_entry("Added priority sorting and color coding to list output. Using colored crate for terminal colors."))
   entries.append(user_msg("This session is being continued from a previous conversation that ran out of context. Summary: Priority field added, list command sorts by priority, colored crate added for terminal colors. Now want to add priority to the filter command.", 10))
   entries.append(assistant_msg("Building on the priority system, I'll add a --min-priority flag to the filter command so users can filter tasks by minimum priority level.", 10,
      [tool_use("Read", {"file_path": f"{PROJECT_DIR}/src/commands/filter.rs"})]))

   # Segment 3
   entries.append(user_msg("Yes, add --min-priority to filter.", 12))
   entries.append(assistant_msg("Added the --min-priority option to the filter subcommand. It accepts a u8 value and only shows tasks with priority >= the specified level.", 12,
      [tool_use("Edit", {"file_path": f"{PROJECT_DIR}/src/commands/filter.rs", "old_string": "show_completed: bool", "new_string": "show_completed: bool, min_priority: Option<u8>"})]))

   # Third compaction
   entries.append(compact_boundary(52000))
   entries.append(summary_entry("Full priority system implemented: field, sorting, colors, filtering by min-priority."))
   entries.append(user_msg("This session is being continued from a previous conversation that ran out of context. Summary: Complete priority system with field, sorting, color output, and filter --min-priority. User wants to run final tests.", 14))
   entries.append(assistant_msg("Let me run the full test suite to make sure everything works together — the priority field, sorting, color output, and the filter min-priority flag.", 14,
      [tool_use("Bash", {"command": f"cd {PROJECT_DIR} && cargo test 2>&1"})]))

   entries.append(user_msg("All tests pass. Commit the priority system.", 16))
   entries.append(assistant_msg("Committed the complete priority system feature.", 16,
      [tool_use("Bash", {"command": f'cd {PROJECT_DIR} && git add -A && git commit -m "Add priority system: field, sorting, colors, filter support"'})]))

   write_jsonl("multi_compaction.jsonl", entries)


def gen_f06_with_subagents():
   """F06: 3 Agent tool_use calls with task-notification responses."""
   entries = [file_history_snapshot(0)]

   entries.append(user_msg("I need you to do three things in parallel: (1) add input validation to all commands, (2) write a README.md, and (3) set up GitHub Actions CI.", 0))

   # First Agent call
   agent_tool_id_1 = "toolu_agent_001"
   entries.append(assistant_msg(
      "I'll handle these three tasks using subagents for parallel execution. Let me start all three.",
      0,
      [
         tool_use("Agent", {"prompt": "Add input validation to all command handlers in src/commands/. Validate that task IDs are positive integers, titles are non-empty, and priority is 1-5.", "allowedTools": ["Read", "Edit", "Bash"]}, tool_id=agent_tool_id_1),
         tool_use("Agent", {"prompt": "Create a comprehensive README.md with installation, usage examples for all commands, and contributing guidelines.", "allowedTools": ["Write", "Read"]}, tool_id="toolu_agent_002"),
         tool_use("Agent", {"prompt": "Set up GitHub Actions CI with a workflow that runs cargo test, cargo clippy, and cargo fmt --check on push and PR.", "allowedTools": ["Write", "Read"]}, tool_id="toolu_agent_003"),
      ],
   ))

   # Subagent 1 result
   entries.append(user_msg("", 2, content_override=[
      {"type": "tool_result", "tool_use_id": agent_tool_id_1, "content": "<task-notification>\n<summary>Added input validation to all 5 command handlers</summary>\n<status>completed</status>\n<result>Validated task IDs (must be > 0), titles (non-empty, max 200 chars), and priority (1-5 range). Added ValidationError enum. All 18 tests pass.</result>\n<task-id>task-001</task-id>\n<tool-use-id>toolu_agent_001</tool-use-id>\n</task-notification>"}
   ]))
   entries.append(assistant_msg("The first subagent has completed input validation. All command handlers now validate their inputs with clear error messages. Let me check the results of the other two.", 2))

   # Subagent 2 result
   entries.append(user_msg("", 3, content_override=[
      {"type": "tool_result", "tool_use_id": "toolu_agent_002", "content": "<task-notification>\n<summary>Created comprehensive README.md</summary>\n<status>completed</status>\n<result>README includes: project description, installation from crates.io, usage examples for add/list/filter/complete/delete commands, configuration, and contributing guide.</result>\n<task-id>task-002</task-id>\n<tool-use-id>toolu_agent_002</tool-use-id>\n</task-notification>"}
   ]))
   entries.append(assistant_msg("README is done. Waiting on the CI setup subagent.", 3))

   # Subagent 3 result
   entries.append(user_msg("", 4, content_override=[
      {"type": "tool_result", "tool_use_id": "toolu_agent_003", "content": "<task-notification>\n<summary>Created GitHub Actions CI workflow</summary>\n<status>completed</status>\n<result>Created .github/workflows/ci.yml with jobs for test (cargo test), lint (cargo clippy), and format check (cargo fmt --check). Matrix strategy for stable and nightly Rust. Runs on push to main and all PRs.</result>\n<task-id>task-003</task-id>\n<tool-use-id>toolu_agent_003</tool-use-id>\n</task-notification>"}
   ]))
   entries.append(assistant_msg(
      "All three subagents have completed successfully. Here's a summary of what was done:\n\n1. **Input validation**: All command handlers validate inputs (positive IDs, non-empty titles, priority 1-5) with a new ValidationError enum.\n2. **README.md**: Comprehensive documentation with installation, usage examples, and contributing guidelines.\n3. **GitHub Actions CI**: Workflow with test, lint, and format jobs running on stable and nightly Rust.\n\nLet me commit all these changes together.",
      4,
      [tool_use("Bash", {"command": f'cd {PROJECT_DIR} && git add -A && git commit -m "Add input validation, README, and CI workflow"'})],
   ))

   write_jsonl("with_subagents.jsonl", entries)


def gen_f07_with_skills():
   """F07: 2 skill injections as user messages."""
   entries = [file_history_snapshot(0)]

   entries.append(user_msg("Use the rust-helper skill to optimize the storage module.", 0))

   # Skill injection 1 (with ARGUMENTS)
   entries.append(user_msg(
      "Base directory for this skill: /home/alex/.claude/skills/rust-helper\n\n# Rust Helper\n\nThis skill provides Rust-specific optimizations and best practices.\n\n## Capabilities\n- Identify unnecessary clones and allocations\n- Suggest iterator chain optimizations\n- Recommend error handling patterns\n- Apply clippy suggestions automatically\n\n## Usage\nAnalyze the specified Rust files and apply optimizations.\n\nARGUMENTS: src/storage/mod.rs",
      1,
   ))

   entries.append(assistant_msg(
      "Using the Rust helper skill to optimize the storage module. I'll analyze the file for unnecessary allocations, clone calls, and suboptimal patterns, then apply improvements.",
      1,
      [
         tool_use("Read", {"file_path": f"{PROJECT_DIR}/src/storage/mod.rs"}),
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/storage/mod.rs",
            "old_string": "let contents = fs::read_to_string(&path).unwrap();",
            "new_string": "let contents = fs::read_to_string(&path)\n        .map_err(|e| StorageError::ReadFailed(path.clone(), e))?;",
         }),
      ],
   ))

   entries.append(user_msg("Now use the benchmark skill to measure performance.", 4))

   # Skill injection 2 (without ARGUMENTS)
   entries.append(user_msg(
      "Base directory for this skill: /home/alex/.claude/skills/bench-runner\n\n# Benchmark Runner\n\nRuns criterion benchmarks and reports results.\n\n## Setup\nEnsures criterion is in dev-dependencies and benchmarks directory exists.\n\n## Output\nGenerates HTML reports in target/criterion/.",
      5,
   ))

   entries.append(assistant_msg(
      "I'll set up criterion benchmarks for the storage operations. This will measure the performance of task loading and saving with different data sizes.",
      5,
      [
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/Cargo.toml",
            "old_string": "[dev-dependencies]",
            "new_string": '[dev-dependencies]\ncriterion = { version = "0.5", features = ["html_reports"] }\n\n[[bench]]\nname = "storage_bench"\nharness = false',
         }),
         tool_use("Write", {
            "file_path": f"{PROJECT_DIR}/benches/storage_bench.rs",
            "content": 'use criterion::{criterion_group, criterion_main, Criterion};\nuse tasktracker::storage;\n\nfn bench_load(c: &mut Criterion) {\n    c.bench_function("load_tasks", |b| b.iter(|| storage::load_tasks()));\n}\n\ncriterion_group!(benches, bench_load);\ncriterion_main!(benches);\n',
         }),
         tool_use("Bash", {"command": f"cd {PROJECT_DIR} && cargo bench 2>&1 | tail -20"}),
      ],
   ))

   entries.append(user_msg("What were the results?", 8))
   entries.append(assistant_msg(
      "The benchmark results show that loading tasks takes approximately 45 microseconds for a file with 100 tasks, and 180 microseconds for 1000 tasks. The storage optimization we applied earlier (removing the unnecessary clone) reduced the load time by about 12%. The HTML report has been saved to target/criterion/ for detailed analysis.",
      8,
   ))

   write_jsonl("with_skills.jsonl", entries)


def gen_f08_chatty():
   """F08: 60 short exchanges — triggers 100-message cap."""
   entries = [file_history_snapshot(0)]

   qa_pairs = [
      ("What's the current Rust edition?", "The project uses Rust edition 2021, as specified in Cargo.toml."),
      ("How many commands does TaskTracker have?", "There are 5 commands: add, list, filter, complete, and delete."),
      ("What serialization format is used?", "Tasks are stored as JSON using serde_json."),
      ("Where's the data file stored?", "In the platform-specific data directory via the directories crate, typically ~/.local/share/tasktracker/tasks.json."),
      ("Does it support due dates?", "Yes, the Task struct has an optional due_date field of type NaiveDate from chrono."),
      ("What about recurring tasks?", "Not yet — that would require a recurrence pattern field and a scheduler."),
      ("How are task IDs generated?", "Auto-incremented: the highest existing ID + 1."),
      ("Any database support?", "No, it's file-based JSON only. SQLite could be a future enhancement."),
      ("What's the test coverage like?", "There are 24 tests covering all commands and the Task model."),
      ("Is there CI?", "Yes, GitHub Actions runs test, clippy, and fmt on push and PR."),
      ("What Rust version is required?", "1.70+ for the edition 2021 features and clap derive macros."),
      ("How do I install it?", "cargo install tasktracker or build from source with cargo build --release."),
      ("Any config file support?", "Not currently. All settings are command-line arguments."),
      ("Shell completion?", "Clap can generate completions. Run tasktracker --generate-completions bash."),
      ("What's the binary size?", "About 3.5 MB in release mode with LTO."),
      ("Can I export tasks?", "Not yet — an export command for CSV/JSON would be useful."),
      ("Is there undo support?", "No, deletions are permanent. A soft-delete or trash could be added."),
      ("How fast is the filter?", "Linear scan — O(n) for n tasks. Fine for thousands of tasks."),
      ("Any plans for a TUI?", "It's been considered. ratatui would be a good choice for the interface."),
      ("Does it support subtasks?", "Not in the current model. Would need a parent_id field."),
      ("Can I set reminders?", "No, it's not a daemon. A notify-send integration could work though."),
      ("How's error handling done?", "Custom error enums with thiserror, propagated with ? operator."),
      ("Any logging?", "Uses env_logger. Set RUST_LOG=debug for verbose output."),
      ("What about Windows support?", "It compiles on Windows. The directories crate handles path differences."),
      ("Can tags have spaces?", "Yes, tags are stored as strings. Use quotes on the CLI: --tag 'my tag'."),
      ("How many tags per task?", "Unlimited — tags are a Vec<String>."),
      ("Is there tag autocompletion?", "Not built-in, but shell completions could include known tags."),
      ("What happens on corrupt data?", "Deserialization fails with an error message. The file isn't overwritten."),
      ("Backup support?", "No automatic backups. Could add a --backup flag to save before writes."),
      ("Can I change task titles?", "Not yet — an edit command would be needed."),
      ("What about task notes?", "No description/notes field currently. Would be a simple addition."),
      ("Sort by due date?", "The filter command supports --sort date for sorting by creation date. Due date sort could be added."),
      ("JSON output mode?", "Not yet. A --json flag on list and filter would be useful for scripting."),
      ("How do I reset all tasks?", "Delete the data file manually. A purge command could be added."),
      ("Can multiple users share tasks?", "No, it's single-user. A server mode would need authentication."),
      ("What's the max title length?", "Validated to 200 characters. Longer titles are rejected."),
      ("Is priority 0 valid?", "No, priority must be 1-5. Zero is rejected by input validation."),
      ("Can I filter by date range?", "Not yet — would need --from and --to flags on the filter command."),
      ("How are completed tasks stored?", "Same file, with completed=true. Use list --all to see them."),
      ("Any statistics command?", "No, but it would be easy: count by status, priority distribution, etc."),
      ("Does it handle timezones?", "Uses NaiveDate (no timezone). Could switch to DateTime<Utc> if needed."),
      ("What about task dependencies?", "Not supported. Would need a depends_on field with cycle detection."),
      ("Can I import from Todoist?", "No import feature exists. Would need API integration or CSV parsing."),
      ("How's the code organized?", "Modules: commands/ (one per command), models/ (Task), storage/ (JSON I/O)."),
      ("Any benchmarks?", "Yes, criterion benchmarks for storage operations in benches/."),
      ("What license is it?", "MIT license."),
      ("How to contribute?", "Fork, branch, PR. Run cargo test and cargo clippy before submitting."),
      ("Any documentation comments?", "Partial. Public functions have doc comments, internals are sparse."),
      ("Does it support emoji in titles?", "Yes, titles are UTF-8 strings. Emoji work fine."),
      ("What about task archiving?", "No archive feature. Completed tasks stay in the main file."),
      ("Can I set a default priority?", "Not yet. Could be a config file option."),
      ("How do I list only high priority?", "Use filter --priority 3 to show tasks with priority 3 and above."),
      ("Any color themes?", "No theming. Colors are hardcoded. Could use a config file for customization."),
      ("Does it work in tmux?", "Yes, ANSI colors work in tmux. Set TERM=xterm-256color if issues arise."),
      ("Can I pipe output?", "Yes, stdout is used for data. Colors are disabled when not a TTY."),
      ("What about fish shell?", "Clap generates fish completions: tasktracker --generate-completions fish."),
      ("How do I update it?", "cargo install tasktracker again to get the latest version."),
      ("Any breaking changes planned?", "The data format may change in 1.0. A migration tool will be provided."),
      ("What's the roadmap?", "Next: edit command, date range filter, JSON output, and TUI mode."),
      ("Is it on crates.io?", "Yes, published as the tasktracker crate. Version 0.3.0 is current."),
   ]

   m = 0
   for question, answer in qa_pairs:
      entries.append(user_msg(question, m))
      entries.append(assistant_msg(answer, m))
      m += 1

   write_jsonl("chatty_session.jsonl", entries)


def gen_f09_with_images():
   """F09: 2 user messages with image blocks."""
   entries = [file_history_snapshot(0)]

   # First image message
   entries.append(user_msg("Here's a screenshot of the error I'm getting:", 0, content_override=[
      {"type": "text", "text": "Here's a screenshot of the error I'm getting when running tasktracker filter:"},
      {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="}},
   ]))
   entries.append(assistant_msg(
      "I can see the error in the screenshot — it's a panic at src/storage/mod.rs:23 caused by an unwrap() on a None value. This happens when the tasks.json file exists but is empty. Let me fix the storage module to handle empty files gracefully.",
      0,
      [
         tool_use("Read", {"file_path": f"{PROJECT_DIR}/src/storage/mod.rs"}),
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/storage/mod.rs",
            "old_string": 'let tasks: Vec<Task> = serde_json::from_str(&contents).unwrap();',
            "new_string": 'let tasks: Vec<Task> = if contents.trim().is_empty() {\n        Vec::new()\n    } else {\n        serde_json::from_str(&contents)\n            .map_err(|e| StorageError::ParseFailed(e))?\n    };',
         }),
      ],
   ))

   # Second image message
   entries.append(user_msg("", 3, content_override=[
      {"type": "text", "text": "Now I'm getting this different error after your fix. See the screenshot:"},
      {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="}},
   ]))
   entries.append(assistant_msg(
      "Ah, I see — the error is now a permission denied issue when trying to create the data directory. The directories crate returns the path but doesn't create it automatically. Let me add directory creation logic to the storage initialization.",
      3,
      [
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/storage/mod.rs",
            "old_string": "let path = data_dir.join(\"tasks.json\");",
            "new_string": "fs::create_dir_all(&data_dir)\n        .map_err(|e| StorageError::DirCreateFailed(data_dir.clone(), e))?;\n    let path = data_dir.join(\"tasks.json\");",
         }),
      ],
   ))

   write_jsonl("with_images.jsonl", entries)


def gen_f10_large_tool_results():
   """F10: User messages with large tool_result content (5000+ chars)."""
   entries = [file_history_snapshot(0)]

   # Generate a large realistic tool result (cargo test output)
   test_output_lines = []
   test_output_lines.append("running 24 tests")
   for i in range(24):
      module = random.choice(["commands::add", "commands::list", "commands::filter", "commands::complete", "commands::delete", "models::task", "storage"])
      test_name = f"test_{module.replace('::', '_')}_{i:02d}"
      test_output_lines.append(f"test {module}::{test_name} ... ok")
   test_output_lines.append("")
   test_output_lines.append("test result: ok. 24 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 1.23s")
   test_output_lines.append("")
   # Add a large clippy output
   for i in range(80):
      test_output_lines.append(f"    Checking dependency_{i:02d} v0.{i}.0")
   test_output_lines.append("    Checking tasktracker v0.3.0 (/home/alex/projects/tasktracker)")
   # Pad with warnings to ensure 5000+ chars
   for i in range(30):
      test_output_lines.append(f"warning: unused variable `temp_{i}` in src/commands/filter.rs:{100+i}:{10+i}")
      test_output_lines.append(f"  --> src/commands/filter.rs:{100+i}:{10+i}")
      test_output_lines.append(f"   |")
      test_output_lines.append(f"{100+i} |     let temp_{i} = calculate_something();")
      test_output_lines.append(f"   |         ^^^^^^ help: if this is intentional, prefix it with an underscore: `_temp_{i}`")
      test_output_lines.append(f"   |")

   large_result = "\n".join(test_output_lines)

   entries.append(user_msg("Run the full test suite and clippy.", 0))
   entries.append(assistant_msg("Running tests and clippy analysis now.", 0,
      [tool_use("Bash", {"command": f"cd {PROJECT_DIR} && cargo test 2>&1 && cargo clippy 2>&1"})]))

   # Tool result in user message
   entries.append(user_msg("", 2, content_override=[
      {"type": "tool_result", "tool_use_id": "toolu_bash_result_001", "content": large_result},
   ]))
   entries.append(assistant_msg(
      "The tests all pass (24/24), but clippy found 30 unused variable warnings in src/commands/filter.rs. These are all temporary variables from the calculation functions that were left in during development. I'll clean them up by either removing unused variables or prefixing them with underscores where the side effects are needed.",
      2,
      [tool_use("Edit", {
         "file_path": f"{PROJECT_DIR}/src/commands/filter.rs",
         "old_string": "let temp_0 = calculate_something();",
         "new_string": "let _temp_0 = calculate_something();",
      })],
   ))

   # Another large tool result — cargo build verbose output
   build_lines = []
   for i in range(100):
      build_lines.append(f"   Compiling dep_{i:03d} v{i}.0.{i} (registry+https://github.com/rust-lang/crates.io-index)")
   build_lines.append(f"   Compiling tasktracker v0.3.0 ({PROJECT_DIR})")
   build_lines.append("    Finished `release` profile [optimized] target(s) in 45.23s")
   large_build = "\n".join(build_lines)

   entries.append(user_msg("", 5, content_override=[
      {"type": "tool_result", "tool_use_id": "toolu_bash_result_002", "content": large_build},
   ]))
   entries.append(assistant_msg(
      "The release build completed successfully in 45 seconds. All 100 dependencies compiled without issues. The final binary is in target/release/tasktracker.",
      5,
   ))

   write_jsonl("large_tool_results.jsonl", entries)


def gen_f11_empty():
   """F11: Only file-history-snapshot and progress entries. No user or assistant messages."""
   entries = [
      file_history_snapshot(0),
      progress_entry(1),
      progress_entry(3),
      file_history_snapshot(5),
      progress_entry(2),
      progress_entry(4),
   ]
   write_jsonl("empty_session.jsonl", entries)


def gen_f12_single_message():
   """F12: 1 user message, no assistant response."""
   entries = [
      file_history_snapshot(0),
      user_msg("Analyze the TaskTracker codebase and suggest architectural improvements for better testability and modularity.", 0),
   ]
   write_jsonl("single_message.jsonl", entries)


def gen_f13_with_plans():
   """F13: EnterPlanMode tool call, Write to plans file, then plan implementation message."""
   entries = [file_history_snapshot(0)]

   entries.append(user_msg("Let's plan the implementation of a task export feature.", 0))
   entries.append(assistant_msg(
      "I'll enter plan mode to think through the export feature design before implementing anything.",
      0,
      [tool_use("EnterPlanMode", {})],
   ))

   entries.append(user_msg("Good, write out the plan.", 2))
   entries.append(assistant_msg(
      "I've written the implementation plan for the task export feature. It covers CSV, JSON, and Markdown export formats with filtering support.",
      2,
      [tool_use("Write", {
         "file_path": "/home/alex/.claude/plans/export-feature-plan.md",
         "content": "# Task Export Feature Plan\n\n## Context\nTaskTracker needs an export command to let users extract their tasks in various formats.\n\n## Requirements\n1. Support CSV, JSON, and Markdown output formats\n2. Allow filtering exported tasks (by status, priority, tag)\n3. Output to stdout by default, --output flag for file\n4. Include headers/metadata in exported files\n\n## Implementation Steps\n1. Add `Export` variant to Commands enum\n2. Create src/commands/export.rs\n3. Create src/formats/ module with csv.rs, json.rs, markdown.rs\n4. Add format detection from --format flag or file extension\n5. Write tests for each format\n6. Update README with export examples\n\n## API\n```\ntasktracker export --format csv --output tasks.csv\ntasktracker export --format json --tag work\ntasktracker export --format md --priority 3\n```\n",
      })],
   ))

   entries.append(user_msg(
      "Implement the following plan:\n\n# Task Export Feature Plan\n\n## Context\nTaskTracker needs an export command to let users extract their tasks in various formats.\n\n## Requirements\n1. Support CSV, JSON, and Markdown output formats\n2. Allow filtering exported tasks (by status, priority, tag)\n3. Output to stdout by default, --output flag for file\n4. Include headers/metadata in exported files\n\n## Implementation Steps\n1. Add Export variant to Commands enum\n2. Create src/commands/export.rs\n3. Create src/formats/ module with csv.rs, json.rs, markdown.rs\n4. Add format detection from --format flag or file extension\n5. Write tests for each format\n6. Update README with export examples",
      4,
   ))
   entries.append(assistant_msg(
      "I'll implement the export feature step by step following the plan. Starting with the Commands enum and the export command module.",
      4,
      [
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/main.rs",
            "old_string": "Delete { id: u32 },",
            "new_string": 'Delete { id: u32 },\n    Export {\n        #[arg(short, long, value_enum)]\n        format: ExportFormat,\n        #[arg(short, long)]\n        output: Option<String>,\n        #[arg(long)]\n        tag: Option<String>,\n        #[arg(long)]\n        priority: Option<u8>,\n    },',
         }),
         tool_use("Write", {
            "file_path": f"{PROJECT_DIR}/src/commands/export.rs",
            "content": "use crate::models::task::Task;\nuse crate::storage;\n\npub fn run(format: crate::ExportFormat, output: Option<String>, tag: Option<String>, priority: Option<u8>) {\n    let tasks = storage::load_tasks().expect(\"Failed to load tasks\");\n    // Apply filters then format output\n    let content = match format {\n        crate::ExportFormat::Csv => format_csv(&tasks),\n        crate::ExportFormat::Json => format_json(&tasks),\n        crate::ExportFormat::Markdown => format_markdown(&tasks),\n    };\n    match output {\n        Some(path) => std::fs::write(&path, &content).expect(\"Failed to write file\"),\n        None => print!(\"{}\", content),\n    }\n}\n\nfn format_csv(tasks: &[Task]) -> String { todo!() }\nfn format_json(tasks: &[Task]) -> String { todo!() }\nfn format_markdown(tasks: &[Task]) -> String { todo!() }\n",
         }),
      ],
   ))

   write_jsonl("with_plans.jsonl", entries)


def gen_f14_microcompact():
   """F14: microcompact_boundary entries (no summary after)."""
   entries = [file_history_snapshot(0)]

   entries.append(user_msg("Add a tag management command.", 0))
   entries.append(assistant_msg("I'll add a tags command that lists all unique tags used across tasks.", 0,
      [tool_use("Read", {"file_path": f"{PROJECT_DIR}/src/main.rs"})]))

   entries.append({"type": "system", "subtype": "microcompact_boundary"})

   entries.append(user_msg("Also add tag rename functionality.", 2))
   entries.append(assistant_msg("I'll add a tags rename subcommand that finds all tasks with the old tag and replaces it.", 2,
      [tool_use("Edit", {"file_path": f"{PROJECT_DIR}/src/commands/tags.rs", "old_string": "// tag commands", "new_string": "pub fn rename(old: &str, new: &str) { /* ... */ }"})]))

   entries.append({"type": "system", "subtype": "microcompact_boundary"})

   entries.append(user_msg("Add tag deletion too.", 4))
   entries.append(assistant_msg("Adding a tags delete subcommand that removes a specific tag from all tasks.", 4,
      [tool_use("Edit", {"file_path": f"{PROJECT_DIR}/src/commands/tags.rs", "old_string": "// more tag commands", "new_string": "pub fn delete(tag: &str) { /* ... */ }"})]))

   entries.append({"type": "system", "subtype": "microcompact_boundary"})

   entries.append(user_msg("Test all tag commands.", 6))
   entries.append(assistant_msg("Running the tag command tests. All three operations (list, rename, delete) pass.", 6,
      [tool_use("Bash", {"command": f"cd {PROJECT_DIR} && cargo test tags 2>&1"})]))

   write_jsonl("microcompact.jsonl", entries)


def gen_f15_unknown_types():
   """F15: Mix of normal messages plus unknown entry types."""
   entries = [file_history_snapshot(0)]

   entries.append(user_msg("Check the project structure.", 0))
   entries.append({"type": "new_experimental_feature", "data": {"feature": "code_lens", "enabled": True}})
   entries.append(assistant_msg("The project has a clean modular structure with separate directories for commands, models, and storage.", 0,
      [tool_use("Glob", {"pattern": "**/*.rs", "path": PROJECT_DIR})]))

   entries.append({"type": "system", "subtype": "analytics_event", "event": "tool_usage", "count": 5})

   entries.append(user_msg("How many lines of code?", 2))
   entries.append({"type": "new_experimental_feature", "data": {"feature": "inline_diff", "version": 2}})
   entries.append(assistant_msg("The project has approximately 850 lines of Rust code across 12 source files, plus 400 lines of tests.", 2,
      [tool_use("Bash", {"command": f"cd {PROJECT_DIR} && find src tests -name '*.rs' | xargs wc -l"})]))

   entries.append({"type": "system", "subtype": "analytics_event", "event": "session_metrics", "duration": 120})

   entries.append(user_msg("Thanks for the overview.", 4))
   entries.append(assistant_msg("You're welcome! The codebase is well-organized and maintainable. Let me know if you'd like to dive deeper into any specific module.", 4))

   write_jsonl("unknown_types.jsonl", entries)


def gen_f16_mixed_content_user():
   """F16: User messages with array content containing text, tool_result, and image blocks."""
   entries = [file_history_snapshot(0)]

   # Message with text + tool_result + image
   entries.append(user_msg("", 0, content_override=[
      {"type": "text", "text": "Here are the test results and a screenshot of the failing assertion:"},
      {"type": "tool_result", "tool_use_id": "toolu_test_001", "content": "running 5 tests\ntest commands::filter::test_empty_query ... ok\ntest commands::filter::test_by_tag ... FAILED\ntest commands::filter::test_by_priority ... ok\ntest commands::filter::test_combined ... ok\ntest models::task::test_new ... ok\n\nfailures:\n\n---- commands::filter::test_by_tag stdout ----\nthread 'commands::filter::test_by_tag' panicked at 'assertion failed: result.contains(\"work\")', src/commands/filter.rs:89:5\n\ntest result: FAILED. 4 passed; 1 failed"},
      {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPj/HwADBwIAMCbHYQAAAABJRU5ErkJggg=="}},
   ]))
   entries.append(assistant_msg(
      "I can see the test failure and the screenshot. The `test_by_tag` test fails because the filter function does a case-sensitive tag comparison, but the test expects case-insensitive matching. The screenshot confirms the tag 'Work' (capitalized) doesn't match the filter 'work' (lowercase). Let me fix the comparison.",
      0,
      [
         tool_use("Read", {"file_path": f"{PROJECT_DIR}/src/commands/filter.rs"}),
         tool_use("Edit", {
            "file_path": f"{PROJECT_DIR}/src/commands/filter.rs",
            "old_string": "t.tags.contains(tag)",
            "new_string": "t.tags.iter().any(|t| t.eq_ignore_ascii_case(tag))",
         }),
      ],
   ))

   # Message with multiple text blocks and a tool result
   entries.append(user_msg("", 3, content_override=[
      {"type": "text", "text": "I also found this issue in the storage module:"},
      {"type": "tool_result", "tool_use_id": "toolu_read_001", "content": "pub fn save_tasks(tasks: &[Task]) -> Result<(), StorageError> {\n    let path = get_data_path();\n    let json = serde_json::to_string(tasks)?;\n    fs::write(&path, json)?;\n    Ok(())\n}"},
      {"type": "text", "text": "It's not using pretty-printed JSON. The data file is one huge line and impossible to debug manually. Can you fix that too?"},
   ]))
   entries.append(assistant_msg(
      "Good catch — using `to_string_pretty` instead of `to_string` makes the data file human-readable, which is really helpful for debugging. The performance difference is negligible for the amount of data TaskTracker handles.",
      3,
      [tool_use("Edit", {
         "file_path": f"{PROJECT_DIR}/src/storage/mod.rs",
         "old_string": "let json = serde_json::to_string(tasks)?;",
         "new_string": "let json = serde_json::to_string_pretty(tasks)?;",
      })],
   ))

   # Message with text + image + text
   entries.append(user_msg("", 5, content_override=[
      {"type": "text", "text": "After your fixes, here's the new test output:"},
      {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="}},
      {"type": "text", "text": "All green! Can you commit these two fixes?"},
   ]))
   entries.append(assistant_msg(
      "All 5 tests pass now. I'll commit both fixes — the case-insensitive tag filtering and the pretty-printed JSON storage.",
      5,
      [tool_use("Bash", {"command": f'cd {PROJECT_DIR} && git add -A && git commit -m "Fix case-insensitive tag filter and use pretty JSON for storage"'})],
   ))

   write_jsonl("mixed_content_user.jsonl", entries)


# ═══════════════════════════════════════════════════════════
# Markdown Fixture Generators
# ═══════════════════════════════════════════════════════════

MD_HEADER_TEMPLATE = """\
## Session Resume

- **Project:** /home/alex/projects/tasktracker
- **Branch:** {branch}
- **Session ID:** {session_id}
- **Transcript:** /tmp/{transcript}
- **Started:** {started}
- **Last activity:** {last_activity}
- **Original transcript:** {size} ({lines} lines)

## Statistics

- **User messages:** {user_msgs}
- **Assistant responses:** {assistant_msgs}
- **Tool calls:** {tool_calls}
- **Subagent calls:** {subagent_calls}
- **Estimated tokens:** ~{tokens:,}

## Conversation

---
"""


def md_user(num, timestamp, tokens, text):
   return (
      f"\n> [!NOTE]\n"
      f"> **User #{num}** · {timestamp} · {tokens} tokens\n"
      f">\n"
      f"> {text}\n"
   )


def md_tools(calls, tokens, entries):
   lines = f"\n> **Tools** ({calls} calls / {tokens} tokens)\n"
   for entry in entries:
      lines += f"> {entry}\n"
   return lines


def md_assistant(words, tokens, text):
   return f"\n**Assistant** · {words} words / {tokens} tokens\n\n{text}\n\n---\n"


def gen_m01_small():
   """M01: 5 exchanges, ~2000 tokens."""
   header = MD_HEADER_TEMPLATE.format(
      branch="main", session_id="test-session-m01", transcript="test-m01.jsonl",
      started="2026-01-15T10:00:00", last_activity="2026-01-15T10:15:00",
      size="45 KB", lines="50", user_msgs=5, assistant_msgs=5,
      tool_calls=8, subagent_calls=0, tokens=2000,
   )

   content = header
   content += md_user(1, "2026-01-15T10:00:00", 30, "Add a --json output flag to the list command.")
   content += md_tools(2, 60, ["Read: src/main.rs", "Read: src/commands/list.rs"])
   content += md_assistant(35, 90, "I'll add a --json flag to the list command. Currently the output is formatted as plain text with status icons. Let me modify both the CLI definition and the output logic.")

   content += md_user(2, "2026-01-15T10:03:00", 20, "Yes, go ahead and implement it.")
   content += md_tools(2, 80, [
      "Edit: src/main.rs — added json: bool to List variant",
      "Edit: src/commands/list.rs — added JSON output branch",
   ])
   content += md_assistant(40, 100, "Done. When --json is passed, the list command now outputs a JSON array of task objects instead of the formatted text. Each object includes all fields: id, title, completed, priority, due_date, tags, and created_at.")

   content += md_user(3, "2026-01-15T10:06:00", 15, "Does it work with the filter command too?")
   content += md_assistant(25, 70, "Not yet — the filter command has its own output formatting. I can add --json to filter as well. Want me to do that?")

   content += md_user(4, "2026-01-15T10:08:00", 10, "Yes please.")
   content += md_tools(1, 50, ["Edit: src/commands/filter.rs — added JSON output support"])
   content += md_assistant(30, 80, "Added --json to filter as well. Both commands now share a common output_tasks() helper that handles formatting, reducing code duplication.")

   content += md_user(5, "2026-01-15T10:10:00", 15, "Run the tests to verify.")
   content += md_tools(1, 40, ["Bash: cargo test"])
   content += md_assistant(20, 60, "All 24 tests pass. The JSON output is valid and parseable. I also verified it works with jq for piping.")

   write_md("small_transcript.md", content)


def gen_m02_large():
   """M02: 30 exchanges, ~40,000 tokens. Needs summarization."""
   header = MD_HEADER_TEMPLATE.format(
      branch="feature/export", session_id="test-session-m02", transcript="test-m02.jsonl",
      started="2026-01-15T09:00:00", last_activity="2026-01-15T12:30:00",
      size="2.1 MB", lines="1200", user_msgs=30, assistant_msgs=30,
      tool_calls=85, subagent_calls=2, tokens=40000,
   )

   content = header

   # Generate 30 exchanges with long assistant responses about implementing an export system
   topics = [
      ("Design the export command architecture", "I'll design a modular export system with pluggable formatters", "Read: src/main.rs\nGlob: src/**/*.rs", 3, 120),
      ("What formats should we support?", "Based on common use cases, I recommend CSV, JSON, TOML, and Markdown", "", 0, 0),
      ("Start with CSV export", "CSV is the simplest format to implement. I'll create a CsvFormatter", "Write: src/formats/csv.rs", 1, 80),
      ("Add headers to CSV output", "Adding configurable headers with the task field names as column headers", "Edit: src/formats/csv.rs", 1, 60),
      ("Handle special characters in CSV", "Fields containing commas, quotes, or newlines need proper escaping", "Edit: src/formats/csv.rs", 1, 70),
      ("Now implement JSON export", "The JSON export is straightforward since we already use serde", "Write: src/formats/json.rs", 1, 50),
      ("Make JSON pretty-printable", "Adding a --pretty flag for human-readable JSON vs compact for piping", "Edit: src/formats/json.rs\nEdit: src/main.rs", 2, 80),
      ("Implement Markdown export", "Markdown tables are great for documentation and GitHub issues", "Write: src/formats/markdown.rs", 1, 70),
      ("Add task count summary to Markdown", "Adding a summary section with total, completed, and pending counts", "Edit: src/formats/markdown.rs", 1, 50),
      ("Create the formats module", "Setting up the module with a Formatter trait for polymorphic dispatch", "Write: src/formats/mod.rs", 1, 60),
      ("Define the Formatter trait", "The trait needs format_tasks() and file_extension() methods", "Edit: src/formats/mod.rs", 1, 80),
      ("Wire up the export command in main.rs", "Adding the Export variant with format, output, and filter options", "Edit: src/main.rs", 1, 70),
      ("Create the export command handler", "The handler loads tasks, applies filters, then delegates to formatter", "Write: src/commands/export.rs", 1, 80),
      ("Add filter integration to export", "Reusing the existing filter logic for consistent behavior", "Edit: src/commands/export.rs\nRead: src/commands/filter.rs", 2, 90),
      ("Handle file output vs stdout", "Auto-detecting format from extension when writing to file", "Edit: src/commands/export.rs", 1, 60),
      ("Build and check for errors", "Fixing import paths and lifetime issues in the formatter trait", "Bash: cargo build 2>&1", 1, 100),
      ("Fix the lifetime issue", "The Formatter trait needs a reference lifetime parameter", "Edit: src/formats/mod.rs\nEdit: src/formats/csv.rs\nEdit: src/formats/json.rs\nEdit: src/formats/markdown.rs", 4, 120),
      ("Build again after lifetime fix", "Clean build now. All formatters implement the trait correctly", "Bash: cargo build 2>&1", 1, 80),
      ("Write CSV unit tests", "Testing header generation, field escaping, and empty task list", "Write: tests/export_csv_test.rs", 1, 90),
      ("Write JSON unit tests", "Testing both compact and pretty formats, and field completeness", "Write: tests/export_json_test.rs", 1, 80),
      ("Write Markdown unit tests", "Testing table formatting, summary generation, and special chars", "Write: tests/export_markdown_test.rs", 1, 80),
      ("Write integration tests for export", "Testing the full CLI: tasktracker export --format csv", "Edit: tests/integration_test.rs", 1, 100),
      ("Run the full test suite", "All 42 tests pass including the new export tests", "Bash: cargo test 2>&1", 1, 60),
      ("Add TOML export format", "TOML is useful for Rust developers and config-like output", "Write: src/formats/toml.rs\nEdit: src/formats/mod.rs", 2, 90),
      ("Update README with export docs", "Adding usage examples for all four export formats", "Edit: README.md", 1, 70),
      ("Run clippy on the new code", "Fixing two warnings about unnecessary clones in formatters", "Bash: cargo clippy 2>&1\nEdit: src/formats/csv.rs\nEdit: src/formats/json.rs", 3, 100),
      ("Format everything with cargo fmt", "Consistent formatting across all new and modified files", "Bash: cargo fmt", 1, 40),
      ("Review the full diff", "The export feature adds 450 lines across 8 new files and 4 modified", "Bash: git diff --stat", 1, 80),
      ("Commit the export feature", "Creating a feature commit with detailed description", "Bash: git add -A && git commit", 1, 60),
      ("Create a PR for the export feature", "Opening a pull request with the implementation summary", "Bash: gh pr create", 1, 80),
   ]

   for i, (question, answer_start, tools_str, tool_count, tool_tokens) in enumerate(topics):
      num = i + 1
      user_tokens = 20 + len(question.split()) * 3
      content += md_user(num, f"2026-01-15T{9 + i // 6:02d}:{(i % 6) * 10:02d}:00", user_tokens, question)

      if tools_str:
         tool_entries = [t.strip() for t in tools_str.split("\n") if t.strip()]
         content += md_tools(tool_count, tool_tokens, tool_entries)

      # Generate a long assistant response (100-200 words)
      long_answer = answer_start + ". "
      long_answer += "This is an important step in the implementation because it ensures " \
         "the export system is modular and extensible. By using a trait-based approach, " \
         "we can easily add new formats in the future without modifying the core export logic. " \
         "The formatter receives a slice of Task references and returns a String with the " \
         "formatted output. Error handling is done through the standard Result type with " \
         "our custom ExportError enum that covers serialization failures, I/O errors, and " \
         "unsupported format combinations. "
      long_answer += f"For this specific change (step {num} of 30), I've verified that the " \
         "implementation follows the established patterns in the codebase. " \
         "The code uses the same error handling conventions, naming patterns, and module " \
         "organization as the existing command handlers. I've also ensured that the " \
         "documentation comments explain the public API surface clearly. "
      long_answer += "The tests cover both the happy path and edge cases including " \
         "empty task lists, tasks with special characters in titles and tags, " \
         "and the interaction between filters and formatters."

      word_count = len(long_answer.split())
      ast_tokens = word_count * 3
      content += md_assistant(word_count, ast_tokens, long_answer)

   write_md("large_transcript.md", content)


def gen_m03_oversized_tail():
   """M03: 10 exchanges where the last assistant response is ~4000 tokens."""
   header = MD_HEADER_TEMPLATE.format(
      branch="main", session_id="test-session-m03", transcript="test-m03.jsonl",
      started="2026-01-15T14:00:00", last_activity="2026-01-15T15:00:00",
      size="120 KB", lines="200", user_msgs=10, assistant_msgs=10,
      tool_calls=15, subagent_calls=0, tokens=8000,
   )

   content = header

   # 9 normal exchanges
   normal_exchanges = [
      ("Set up the project for async", "Adding tokio to dependencies.", "Edit: Cargo.toml", 1, 40),
      ("Convert main to async", "Changed main() to #[tokio::main] async fn main().", "Edit: src/main.rs", 1, 50),
      ("Make storage async", "Using tokio::fs for file operations.", "Edit: src/storage/mod.rs", 1, 60),
      ("Convert add command", "The add command now awaits storage operations.", "Edit: src/commands/add.rs", 1, 40),
      ("Convert list command", "List command uses async task loading.", "Edit: src/commands/list.rs", 1, 40),
      ("Convert filter command", "Filter applies async loading then sync filtering.", "Edit: src/commands/filter.rs", 1, 45),
      ("Convert complete command", "Complete command awaits both load and save.", "Edit: src/commands/complete.rs", 1, 40),
      ("Convert delete command", "Delete command is now fully async.", "Edit: src/commands/delete.rs", 1, 40),
      ("Update test helpers", "Test utilities now use #[tokio::test].", "Edit: tests/test_helpers.rs", 1, 50),
   ]

   for i, (q, a, tools, tc, tt) in enumerate(normal_exchanges):
      num = i + 1
      content += md_user(num, f"2026-01-15T14:{i*5:02d}:00", 20, q)
      content += md_tools(tc, tt, [tools])
      content += md_assistant(15, 40, a)

   # Exchange 10 — very large assistant response (~4000 tokens = ~800-1000 words)
   content += md_user(10, "2026-01-15T14:45:00", 30, "Give me a comprehensive summary of all the async changes and any remaining issues.")
   content += md_tools(3, 120, [
      "Bash: cargo test 2>&1",
      "Bash: cargo clippy 2>&1",
      "Bash: git diff --stat",
   ])

   long_summary = textwrap.dedent("""\
      Here is a comprehensive summary of the async/await migration for TaskTracker.

      ## Overview of Changes

      The entire TaskTracker codebase has been migrated from synchronous to asynchronous execution using the tokio runtime. This affects 12 source files and 5 test files. The migration was done methodically, starting from the lowest-level I/O operations (storage) and working up through the command handlers to main().

      ## Dependency Changes (Cargo.toml)

      Added tokio as a dependency with the following features enabled: full (includes rt-multi-thread, macros, fs, io-util, time, sync). The tokio version is 1.36 which is the latest stable release. Also added tokio-test 0.4 as a dev-dependency for async test utilities. The total dependency count increased from 45 to 52 due to tokio's transitive dependencies, but the compile time only increased by about 8 seconds.

      ## Storage Layer (src/storage/mod.rs)

      The storage module underwent the most significant changes. The load_tasks() function now uses tokio::fs::read_to_string() instead of std::fs::read_to_string(), and save_tasks() uses tokio::fs::write(). Both functions return impl Future<Output = Result<..., StorageError>> instead of Result directly. The file locking mechanism was updated to use tokio::sync::Mutex for concurrent access protection, which is important for potential future multi-threaded command execution.

      Error handling was improved during the migration. Previously, some I/O errors were handled with unwrap() calls that would panic. Now all file operations use the ? operator with proper error propagation through the StorageError enum. New variants were added: StorageError::AsyncReadFailed and StorageError::AsyncWriteFailed, which include the tokio::io::Error for detailed diagnostics.

      ## Command Handlers (src/commands/*.rs)

      All five command handlers (add, list, filter, complete, delete) were converted to async functions. The pattern for each was consistent: change fn run(...) to async fn run(...), add .await to storage calls, and update error handling to work with async Results.

      The filter command required special attention because its filtering logic involves iterating over tasks with closures. While the closures themselves remain synchronous (they only compare fields), the task loading that feeds them is now async. The solution was to load tasks first with .await, then apply the synchronous filter chain. This separation is clean and avoids the complexity of async closures.

      The complete and delete commands both perform load-modify-save cycles. In the synchronous version, these were simple sequential calls. In the async version, they still execute sequentially (load.await, modify, save.await) but now yield to the runtime between I/O operations, allowing better resource utilization in potential future concurrent scenarios.

      ## Main Entry Point (src/main.rs)

      The main() function was annotated with #[tokio::main] to set up the tokio runtime. The match expression that dispatches to command handlers now uses .await for each arm. The runtime configuration uses the multi-thread flavor by default, though for a CLI tool the current-thread flavor would be equally appropriate. This choice was made for forward compatibility in case a server mode or concurrent batch processing is added later.

      ## Test Migration (tests/*.rs)

      All test functions were changed from #[test] to #[tokio::test]. The test helper module was updated to use async setup and teardown functions. Temporary test data files are now created and cleaned up using tokio::fs operations for consistency with the production code.

      Integration tests required the most changes because they spawn the binary as a subprocess. The Command::output() calls were wrapped in tokio::process::Command for non-blocking subprocess execution. This prevents test timeouts when the binary hangs, as the async runtime can enforce a timeout wrapper around each test.

      ## Performance Impact

      Benchmarks show that the async version has approximately 3-5% overhead for single-task operations due to the runtime overhead. However, for operations that process many tasks (like filter with a large dataset), the async version is actually 2% faster because tokio's file I/O uses more efficient system calls (io_uring on Linux, kqueue on macOS).

      ## Remaining Issues

      There are three known issues that should be addressed in follow-up PRs:

      1. The export command (src/commands/export.rs) was not included in this migration because it depends on the formatter trait which has synchronous I/O for writing to stdout. This needs a design decision about whether stdout writes should be async.

      2. The benchmark suite (benches/storage_bench.rs) needs to be updated to use tokio's benchmark utilities. Currently the benchmarks compile but may produce inaccurate timing results because they don't account for async runtime overhead.

      3. There is a potential race condition in the test suite: two tests that modify the same test data file could interfere with each other when running in parallel. Adding a test mutex or using unique temp directories per test would fix this.

      ## Conclusion

      The async migration is functionally complete for the core command handlers and storage layer. All 24 existing tests pass with the async versions. Clippy reports no warnings. The code is formatted with cargo fmt. The git diff shows 12 files changed with 180 insertions and 95 deletions, indicating a relatively clean migration with more new async boilerplate than removed synchronous code.\
   """)

   word_count = len(long_summary.split())
   content += md_assistant(word_count, word_count * 4, long_summary)

   write_md("oversized_tail.md", content)


def gen_m04_uniform():
   """M04: 20 exchanges where every message is roughly ~500 tokens. Total ~20,000."""
   header = MD_HEADER_TEMPLATE.format(
      branch="main", session_id="test-session-m04", transcript="test-m04.jsonl",
      started="2026-01-15T10:00:00", last_activity="2026-01-15T12:00:00",
      size="500 KB", lines="600", user_msgs=20, assistant_msgs=20,
      tool_calls=40, subagent_calls=0, tokens=20000,
   )

   content = header

   topics = [
      "Add a new 'stats' command that shows task statistics",
      "Show count of tasks by status (pending, completed, deleted)",
      "Add priority distribution to stats output",
      "Show average completion time for finished tasks",
      "Add tag frequency analysis to stats",
      "Show tasks completed per day/week/month breakdown",
      "Add a progress bar visualization for completion rate",
      "Include overdue task count in stats",
      "Add streak tracking for consecutive days with completed tasks",
      "Show productivity score based on priority-weighted completions",
      "Add comparison with previous week's stats",
      "Include most productive day of week in stats",
      "Show tag co-occurrence matrix in verbose mode",
      "Add export support for stats (JSON format)",
      "Write unit tests for the stats calculations",
      "Write integration tests for stats command output",
      "Add colored output for stats based on thresholds",
      "Handle edge case of empty task list in stats",
      "Run full test suite to verify all stats features",
      "Commit the completed stats command implementation",
   ]

   for i, topic in enumerate(topics):
      num = i + 1
      # Each user message ~100 tokens
      user_text = f"{topic}. This should follow the existing command patterns and use " \
         f"the same error handling approach. Make sure it integrates with the " \
         f"storage layer properly and handles edge cases like empty data files. " \
         f"The output should be well-formatted and readable in terminal."
      content += md_user(num, f"2026-01-15T{10 + i // 6:02d}:{(i % 6) * 10:02d}:00", 100, user_text)

      # Each tools section ~100 tokens
      content += md_tools(2, 100, [
         f"Read: src/commands/stats.rs",
         f"Edit: src/commands/stats.rs — implemented {topic.lower()}",
      ])

      # Each assistant response ~300 tokens (~75 words)
      assistant_text = f"I've implemented the {topic.lower()} feature. " \
         f"The implementation follows the established patterns in the codebase, " \
         f"using the same error handling conventions with Result types and the " \
         f"StorageError enum. The output is formatted using the colored crate " \
         f"for terminal readability, with green for positive indicators and " \
         f"red for negative ones. Edge cases like empty task lists and missing " \
         f"dates are handled gracefully with appropriate fallback messages. " \
         f"The calculations use iterator chains for clean, functional-style " \
         f"data processing. All existing tests continue to pass with this addition."
      word_count = len(assistant_text.split())
      content += md_assistant(word_count, 300, assistant_text)

   write_md("uniform_messages.md", content)


def gen_m05_skewed():
   """M05: 2 huge bot messages (~5000 tokens each) + 20 tiny exchanges (~50 tokens each). Total ~11,000."""
   header = MD_HEADER_TEMPLATE.format(
      branch="refactor/modules", session_id="test-session-m05", transcript="test-m05.jsonl",
      started="2026-01-15T10:00:00", last_activity="2026-01-15T11:30:00",
      size="280 KB", lines="400", user_msgs=22, assistant_msgs=22,
      tool_calls=30, subagent_calls=0, tokens=11000,
   )

   content = header

   # Exchange 1: Huge assistant response (~5000 tokens = ~1000 words)
   content += md_user(1, "2026-01-15T10:00:00", 40, "Analyze the entire TaskTracker architecture and suggest a comprehensive refactoring plan.")
   content += md_tools(5, 200, [
      "Glob: src/**/*.rs",
      "Read: src/main.rs",
      "Read: src/models/task.rs",
      "Read: src/storage/mod.rs",
      "Read: Cargo.toml",
   ])

   huge_response_1 = textwrap.dedent("""\
      After analyzing the complete TaskTracker codebase, here is my comprehensive architectural assessment and refactoring recommendations.

      ## Current Architecture Analysis

      The project currently follows a flat module structure with three main areas: commands (5 modules), models (1 module), and storage (1 module). While this works for the current scope, several architectural issues will cause problems as the project grows.

      ### Issue 1: Tight Coupling Between Commands and Storage

      Every command module directly imports and calls storage functions. This creates a tight coupling that makes testing difficult — you cannot test command logic without the file system. The solution is to introduce a repository pattern: define a TaskRepository trait with methods like get_all(), get_by_id(), save(), and delete(), then inject this into command handlers. Tests can use a MockTaskRepository that operates on in-memory data.

      The trait should look like this: trait TaskRepository with async methods for load_all returning a Result of Vec Task, save_all accepting a reference to Vec Task, and find_by_id accepting a u32 and returning Option Task. This enables testing command logic independently of storage.

      ### Issue 2: No Separation of Business Logic

      Command handlers mix three concerns: argument parsing (CLI layer), business logic (domain layer), and output formatting (presentation layer). For example, the filter command parses arguments, loads tasks, applies filters, formats output, and prints results all in one function. This violates the single responsibility principle and makes it impossible to reuse the filtering logic programmatically.

      The refactoring should extract a service layer: TaskService with methods like add_task(), complete_task(), filter_tasks(), and get_statistics(). Each service method handles only business logic and returns domain types. The command handlers become thin wrappers that parse CLI args, call the service, and format the output.

      ### Issue 3: Error Handling Inconsistencies

      Three different error handling patterns exist in the codebase. Some functions use unwrap() which panics on errors. Others use expect() with messages. The newer code uses proper Result types with custom error enums. This inconsistency is confusing and causes runtime panics that should be recoverable errors.

      The fix is to standardize on a single error hierarchy: AppError at the top level with variants for StorageError, ValidationError, FormatError, and CommandError. Each module defines its own error type that implements Into AppError. All functions return Result types — no unwrap() or expect() calls except in tests.

      ### Issue 4: Missing Configuration System

      Hard-coded values are scattered across the codebase: the data file name (tasks.json), the default priority (1), the maximum title length (200), and color codes for priority levels. These should be centralized in a Config struct loaded from a TOML file or environment variables.

      A good structure would be: Config with fields for data_dir (PathBuf), default_priority (u8), max_title_length (usize), color_scheme (ColorScheme), and date_format (String). The config file path follows XDG conventions, falling back to sensible defaults when no config exists.

      ### Issue 5: No Middleware or Hook System

      Cross-cutting concerns like logging, performance monitoring, and data validation are implemented ad-hoc in each command. A simple middleware pattern would allow these to be applied consistently. Before each command runs: validate inputs, acquire file lock, log the operation. After each command: release lock, log duration, update statistics.

      ## Recommended Refactoring Order

      Phase 1 (Week 1): Extract the TaskRepository trait and implement FileTaskRepository. Update all commands to accept a repository parameter. Create MockTaskRepository for tests. This unblocks all other phases.

      Phase 2 (Week 2): Extract TaskService with business logic methods. Slim down command handlers to parse-call-format pattern. Add service-level tests that use the mock repository.

      Phase 3 (Week 3): Standardize error handling. Define the AppError hierarchy. Replace all unwrap and expect calls. Add error context with thiserror and anyhow for the CLI layer.

      Phase 4 (Week 4): Add configuration system. Define Config struct. Add config file loading. Replace all hardcoded values. Add a config subcommand for viewing and editing settings.

      ## Impact Assessment

      This refactoring touches all 12 source files and 5 test files. Line count will increase from approximately 850 to 1200 as we add traits, service methods, and proper error types. However, each individual file becomes simpler and more focused. Test coverage should improve from the current estimated 60 percent to over 85 percent because service logic can be tested without file system dependencies.

      The refactoring can be done incrementally — each phase produces a working, deployable state. I recommend creating a feature branch for each phase and merging via PR for review.\
   """)
   word_count = len(huge_response_1.split())
   content += md_assistant(word_count, word_count * 5, huge_response_1)

   # 20 tiny exchanges (~50 tokens each)
   tiny_pairs = [
      ("Start Phase 1", "Creating the TaskRepository trait in src/repository/mod.rs."),
      ("Define the trait methods", "Added load_all, save_all, find_by_id, and delete methods."),
      ("Implement FileTaskRepository", "Created FileTaskRepository wrapping the existing storage logic."),
      ("Update add command", "Add command now accepts a dyn TaskRepository parameter."),
      ("Update list command", "List command refactored to use repository trait."),
      ("Update filter command", "Filter command uses repository for task loading."),
      ("Update complete command", "Complete command uses repository load and save."),
      ("Update delete command", "Delete command migrated to repository pattern."),
      ("Create MockTaskRepository", "In-memory mock repository for testing."),
      ("Write repository tests", "Added 8 tests for FileTaskRepository."),
      ("Write mock-based command tests", "12 new tests using MockTaskRepository."),
      ("Run all tests", "All 44 tests pass. Phase 1 complete."),
      ("Commit Phase 1", "Committed: Introduce TaskRepository trait."),
      ("Start Phase 2", "Creating TaskService struct."),
      ("Extract add logic", "TaskService::add_task handles validation and storage."),
      ("Extract filter logic", "TaskService::filter_tasks with typed filter criteria."),
      ("Extract stats logic", "TaskService::get_statistics returns StatsReport."),
      ("Slim down handlers", "All command handlers are now under 20 lines each."),
      ("Run tests for Phase 2", "All 56 tests pass."),
      ("Commit Phase 2", "Committed: Extract TaskService layer."),
   ]

   for i, (q, a) in enumerate(tiny_pairs):
      num = i + 2
      content += md_user(num, f"2026-01-15T10:{10 + i*2:02d}:00", 15, q)
      content += md_tools(1, 30, [f"Edit: src/{'repository' if i < 13 else 'service'}/mod.rs"])
      content += md_assistant(10, 25, a)

   # Exchange 22: Another huge assistant response
   content += md_user(22, "2026-01-15T11:20:00", 40, "Now give me a detailed retrospective on Phases 1 and 2. What worked, what was harder than expected, and what should we adjust for Phases 3 and 4?")
   content += md_tools(4, 150, [
      "Bash: git log --oneline -10",
      "Bash: cargo test 2>&1 | tail -5",
      "Bash: git diff --stat HEAD~2",
      "Bash: wc -l src/**/*.rs",
   ])

   huge_response_2 = textwrap.dedent("""\
      Here is a detailed retrospective on the Phase 1 and Phase 2 refactoring of TaskTracker.

      ## Phase 1 Retrospective: TaskRepository Trait

      Phase 1 went smoother than expected. The main goal was to decouple command handlers from direct storage access by introducing a TaskRepository trait. This was accomplished in 13 steps over about 45 minutes.

      ### What Worked Well

      The repository pattern was a natural fit for this codebase. The existing storage module already had clean function signatures (load_tasks and save_tasks) that mapped directly to trait methods. Converting from direct function calls to trait method calls was mostly mechanical — find every storage::load_tasks() call and replace with self.repository.load_all(). The compiler caught every missed conversion.

      The MockTaskRepository was simple to implement because the trait surface was small (4 methods). Using a Vec Task internally with RefCell for interior mutability gave us a lightweight mock that required no external mocking libraries. Tests that previously needed temporary files now run entirely in memory, reducing test execution time from 2.3 seconds to 0.4 seconds.

      ### What Was Harder Than Expected

      The lifetime annotations on the repository trait were tricky. Initially I defined the trait with a generic lifetime parameter, but this caused issues when storing the repository in command handler structs. The solution was to use dynamic dispatch (Box dyn TaskRepository) in the command handlers and Arc dyn TaskRepository for the service layer. This added some indirection but kept the API clean.

      Another unexpected challenge was the file locking mechanism in FileTaskRepository. The original storage module used a simple file lock that worked for sequential command execution. With the repository trait, the lock needed to be held across load-modify-save cycles, which required changing the locking strategy from per-operation to per-transaction. This was a design improvement that would have been needed eventually, but it added complexity to what was supposed to be a straightforward refactoring.

      ### Metrics

      Files changed in Phase 1: 14 (5 command handlers, 2 new repository files, 5 test files, main.rs, commands mod.rs). Lines added: 280. Lines removed: 120. Net increase: 160 lines. New test count: 20 (8 repository tests plus 12 mock-based command tests).

      ## Phase 2 Retrospective: TaskService Layer

      Phase 2 was the more ambitious refactoring. The goal was to extract business logic from command handlers into a dedicated service layer. This took 8 steps and about 30 minutes.

      ### What Worked Well

      Having the repository trait in place from Phase 1 made the service extraction clean. TaskService accepts a Box dyn TaskRepository in its constructor, and all business methods delegate I/O through the repository trait. This means the service is fully testable with the mock repository.

      The filter logic benefited the most from extraction. Previously it was interleaved with CLI argument parsing and output formatting. Now TaskService::filter_tasks accepts a FilterCriteria struct and returns a Vec of Task references. The FilterCriteria struct is reusable — the export command can use the same filtering without duplicating logic.

      The command handlers are now satisfyingly thin. Each one follows the same pattern: parse CLI args into domain types, call the appropriate service method, format and print the result. The longest handler (filter) went from 45 lines to 18 lines. This makes the CLI layer easy to reason about and modify.

      ### What Was Harder Than Expected

      Error propagation through the service layer required careful design. The service methods can fail for different reasons (storage errors, validation errors, business rule violations) and the command handlers need to present appropriate error messages for each case. I ended up defining a ServiceError enum that wraps StorageError and adds service-specific variants like TaskNotFound and InvalidFilter. This is the right approach but it means three levels of error types: StorageError, ServiceError, and the eventual AppError from Phase 3.

      The statistics calculation was surprisingly complex to extract. The original stats command computed everything inline with ad-hoc iterator chains. Extracting it into TaskService::get_statistics required defining a StatsReport struct with 12 fields. Some calculations depend on each other (completion rate depends on total and completed counts), so the computation order matters. I created a StatsBuilder that computes metrics in the right order and produces an immutable StatsReport.

      ### Recommendations for Phases 3 and 4

      For Phase 3 (error handling standardization), I recommend using thiserror for all error type definitions and anyhow at the CLI boundary for flexible error context. The three-level error hierarchy (Storage, Service, App) should be formalized with From implementations for automatic conversion. Consider adding a user-facing error formatter that produces helpful messages with suggestions for resolution.

      For Phase 4 (configuration), start with a minimal config: data directory path and default priority. Load from a TOML file at the XDG config path, with environment variable overrides. Add the full configuration options incrementally based on actual user needs rather than speculative requirements. The config module should use the builder pattern for construction and validation.

      Overall assessment: the refactoring is on track and the code quality has improved substantially. The test suite has grown from 24 to 56 tests, and the average function length has decreased from 35 lines to 15 lines. I recommend proceeding with Phases 3 and 4 next week.\
   """)
   word_count = len(huge_response_2.split())
   content += md_assistant(word_count, word_count * 5, huge_response_2)

   write_md("skewed_messages.md", content)


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def generate_all():
   """Generate all fixtures."""
   os.makedirs(JSONL_DIR, exist_ok=True)
   os.makedirs(MD_DIR, exist_ok=True)

   print("Generating JSONL fixtures...")
   global _uuid_counter
   _uuid_counter = 0; gen_f01_tiny()
   _uuid_counter = 100; gen_f02_short()
   _uuid_counter = 200; gen_f03_medium()
   _uuid_counter = 400; gen_f04_long_autonomous()
   _uuid_counter = 600; gen_f05_multi_compaction()
   _uuid_counter = 700; gen_f06_with_subagents()
   _uuid_counter = 800; gen_f07_with_skills()
   _uuid_counter = 900; gen_f08_chatty()
   _uuid_counter = 1100; gen_f09_with_images()
   _uuid_counter = 1200; gen_f10_large_tool_results()
   _uuid_counter = 1400; gen_f11_empty()
   _uuid_counter = 1500; gen_f12_single_message()
   _uuid_counter = 1600; gen_f13_with_plans()
   _uuid_counter = 1700; gen_f14_microcompact()
   _uuid_counter = 1800; gen_f15_unknown_types()
   _uuid_counter = 1900; gen_f16_mixed_content_user()

   print("\nGenerating Markdown fixtures...")
   gen_m01_small()
   gen_m02_large()
   gen_m03_oversized_tail()
   gen_m04_uniform()
   gen_m05_skewed()

   print("\nAll fixtures generated successfully.")


if __name__ == "__main__":
   generate_all()
