#!/usr/bin/env python3
"""Parse a Claude Code session transcript into a condensed format for session resumption.

Usage: python3 parse-transcript.py <session-id> [--cwd <path>]
Output: Condensed transcript to stdout, stats to stderr.
"""

import json
import sys
import re
from pathlib import Path


def find_transcript(session_id, project_path=None):
   """Find the transcript JSONL file for a given session ID."""
   claude_dir = Path.home() / ".claude" / "projects"

   if project_path:
      encoded = project_path.replace("/", "-")
      if not encoded.startswith("-"):
         encoded = "-" + encoded
      candidate = claude_dir / encoded / f"{session_id}.jsonl"
      if candidate.exists():
         return candidate

   # Search all project directories
   for project_dir in sorted(claude_dir.iterdir()):
      if project_dir.is_dir():
         candidate = project_dir / f"{session_id}.jsonl"
         if candidate.exists():
            return candidate

   return None


def count_words(text):
   """Count words in text."""
   return len(text.split())


def summarize_tool_call(name, inp):
   """Create a one-line summary of a tool call."""
   home = str(Path.home())

   def short(path):
      return path.replace(home, "~")

   if name == "Read":
      path = short(inp.get("file_path", "?"))
      parts = [path]
      if inp.get("offset"):
         parts.append(f"offset={inp['offset']}")
      if inp.get("limit"):
         parts.append(f"limit={inp['limit']}")
      return f"Read: {' '.join(parts)}"
   elif name == "Edit":
      path = short(inp.get("file_path", "?"))
      return f"Edit: {path}"
   elif name == "Write":
      path = short(inp.get("file_path", "?"))
      content_len = len(inp.get("content", ""))
      return f"Write: {path} ({content_len:,} chars)"
   elif name == "Bash":
      cmd = inp.get("command", "?")[:200]
      bg = " [bg]" if inp.get("run_in_background") else ""
      return f"Bash: {cmd}{bg}"
   elif name == "Agent":
      st = inp.get("subagent_type", "?")
      desc = inp.get("description", "?")
      bg = " [bg]" if inp.get("run_in_background") else ""
      return f"Agent({st}): {desc!r}{bg}"
   elif name == "Glob":
      pattern = inp.get("pattern", "?")
      path = inp.get("path", "")
      return f"Glob: {pattern}" + (f" in {short(path)}" if path else "")
   elif name == "Grep":
      pattern = inp.get("pattern", "?")
      path = inp.get("path", "")
      return f"Grep: {pattern!r}" + (f" in {short(path)}" if path else "")
   elif name == "Skill":
      args = inp.get("args", "")
      return f"Skill: {inp.get('skill', '?')}" + (f" {args}" if args else "")
   elif name == "TaskCreate":
      return f"TaskCreate: {inp.get('subject', '?')}"
   elif name == "TaskUpdate":
      tid = inp.get("taskId", "?")
      parts = [f"id={tid}"]
      if inp.get("status"):
         parts.append(f"status={inp['status']}")
      return f"TaskUpdate: {' '.join(parts)}"
   elif name == "TaskList":
      return "TaskList"
   elif name == "TaskGet":
      return f"TaskGet: id={inp.get('taskId', '?')}"
   elif name == "TaskOutput":
      return f"TaskOutput: id={inp.get('task_id', '?')}"
   elif name == "AskUserQuestion":
      qs = inp.get("questions", [])
      if qs:
         return f"AskUser: {qs[0].get('question', '?')[:150]}"
      return "AskUser: (no question)"
   elif name == "EnterPlanMode":
      return "EnterPlanMode"
   elif name == "ExitPlanMode":
      return "ExitPlanMode"
   elif name == "WebFetch":
      return f"WebFetch: {inp.get('url', '?')[:100]}"
   elif name == "WebSearch":
      return f"WebSearch: {inp.get('query', '?')[:100]}"
   elif name == "ToolSearch":
      return f"ToolSearch: {inp.get('query', '?')[:80]}"
   elif name == "TaskStop":
      return f"TaskStop: {inp.get('task_id', '?')}"
   else:
      params_summary = ", ".join(
         f"{k}={str(v)[:50]}" for k, v in list(inp.items())[:3]
      )
      return f"{name}({params_summary})"


COMPACT_SUMMARY_PREFIX = (
   "This session is being continued from a previous conversation"
)

PLAN_INJECTION_PREFIX = "Implement the following plan:"

SKILL_INJECTION_PREFIX = "Base directory for this skill:"


def condense_skill_injection(text):
   """Condense a skill injection message to just the skill name, path, and arguments.

   Skill injections start with 'Base directory for this skill: <path>'
   and end with 'ARGUMENTS: <args>'. The full skill content in between is not needed.
   """
   if not text.startswith(SKILL_INJECTION_PREFIX):
      return None

   # Extract skill path
   first_line = text.split("\n")[0]
   skill_path = first_line.replace(SKILL_INJECTION_PREFIX, "").strip()
   # Derive skill name from path (last directory component)
   skill_name = skill_path.rstrip("/").rsplit("/", 1)[-1] if "/" in skill_path else skill_path

   # Extract arguments if present
   args_match = re.search(r"\nARGUMENTS:\s*(.*?)$", text, re.DOTALL)
   args = args_match.group(1).strip() if args_match else ""

   content_words = count_words(text)
   content_tokens = estimate_tokens(text)

   line = f"[Skill loaded: {skill_name} (~{content_words} words / ~{content_tokens} tokens)]"
   if args:
      line += f"\n[Skill arguments: {args[:300]}]"

   return line


def condense_plan_injection(text, plan_files):
   """Condense a plan injection message to title, word count, and plan file reference.

   Plan injections start with 'Implement the following plan:' and contain the full
   plan content. The plan file path is found from Write tool calls to ~/.claude/plans/.
   """
   if not text.startswith(PLAN_INJECTION_PREFIX):
      return None

   # Extract title (first markdown heading)
   title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
   title = title_match.group(1).strip() if title_match else "untitled plan"

   content_words = count_words(text)
   content_tokens = estimate_tokens(text)

   # Find the most recent plan file (last one written is most likely the final version)
   plan_file = plan_files[-1] if plan_files else None

   parts = [f"[Plan injected: \"{title}\" (~{content_words} words / ~{content_tokens} tokens)"]
   if plan_file:
      parts.append(f", final plan file: {plan_file}")
      parts.append(" (note: injected content may differ slightly from file if plan was iterated)")
   parts.append("]")

   return "".join(parts)


def parse_task_notification(text):
   """Parse a <task-notification> block and return a condensed summary.

   Returns (summary_line, result_words) or None if not a task-notification.
   """
   if "<task-notification>" not in text:
      return None

   summary_match = re.search(r"<summary>(.*?)</summary>", text, re.DOTALL)
   result_match = re.search(r"<result>(.*?)</result>", text, re.DOTALL)
   status_match = re.search(r"<status>(.*?)</status>", text, re.DOTALL)
   tool_use_id_match = re.search(r"<tool-use-id>(.*?)</tool-use-id>", text, re.DOTALL)

   summary = summary_match.group(1).strip() if summary_match else "unknown task"
   status = status_match.group(1).strip() if status_match else "?"
   tool_use_id = tool_use_id_match.group(1).strip() if tool_use_id_match else None

   result_words = 0
   result_tokens = 0
   if result_match:
      result_text = result_match.group(1).strip()
      result_words = count_words(result_text)
      result_tokens = estimate_tokens(result_text)

   parts = [f"[Task notification: {summary} (status: {status}"]
   if result_words > 0:
      parts.append(f", result: ~{result_words} words / ~{result_tokens} tokens")
   parts.append(")]")

   line = "".join(parts)

   # Add access instruction if we have IDs
   access_hint = ""
   if tool_use_id:
      access_hint = f"  [To read full result: search transcript for tool-use-id '{tool_use_id}']"

   return line, access_hint, result_words


def parse_session(transcript_path):
   """Parse a session transcript and return structured data."""
   with open(transcript_path, "r") as f:
      lines = f.readlines()

   total_bytes = sum(len(l) for l in lines)
   entries = []
   metadata = {}
   compaction_count = 0
   compaction_summaries_bytes = 0
   unknown_types = {}  # type_key -> count

   # Known entry types we handle or intentionally skip
   known_types = {
      "user", "assistant", "progress", "file-history-snapshot",
      "queue-operation", "summary",
   }
   known_system_subtypes = {
      "compact_boundary", "microcompact_boundary",
      "local_command", "turn_duration",
   }

   # First pass: find compact/microcompact boundary line indices and collect metadata
   compact_boundaries = {}  # line_index -> metadata dict
   session_summary = None  # from 'summary' type entries
   plan_files = []  # paths to plan files written during this session
   for i, line in enumerate(lines):
      try:
         obj = json.loads(line)
      except json.JSONDecodeError:
         continue
      # Collect plan file paths from Write tool calls
      if obj.get("type") == "assistant":
         content = obj.get("message", {}).get("content", [])
         if isinstance(content, list):
            for block in content:
               if isinstance(block, dict) and block.get("type") == "tool_use":
                  if block.get("name") == "Write":
                     fp = block.get("input", {}).get("file_path", "")
                     if ".claude/plans/" in fp:
                        plan_files.append(fp)
      subtype = obj.get("subtype", "")
      if subtype == "compact_boundary":
         cm = obj.get("compactMetadata", {})
         compact_boundaries[i] = {
            "trigger": cm.get("trigger", "?"),
            "preTokens": cm.get("preTokens", 0),
            "kind": "compact",
         }
      elif subtype == "microcompact_boundary":
         compact_boundaries[i] = {
            "trigger": "micro",
            "preTokens": 0,
            "kind": "microcompact",
         }
      elif obj.get("type") == "summary":
         session_summary = obj.get("summary", "")

   # Track which lines are compact summaries (the user message right after a boundary)
   skip_summary_lines = set()
   for boundary_idx, bdata in compact_boundaries.items():
      if bdata["kind"] == "microcompact":
         continue  # microcompacts don't have summary messages
      # The summary is the next user-type message after the boundary
      for j in range(boundary_idx + 1, min(boundary_idx + 5, len(lines))):
         try:
            obj = json.loads(lines[j])
         except json.JSONDecodeError:
            continue
         if obj.get("type") == "user":
            msg = obj.get("message", {})
            content = msg.get("content", "")
            content_str = content if isinstance(content, str) else ""
            if isinstance(content, list):
               for b in content:
                  if isinstance(b, dict) and b.get("type") == "text":
                     content_str = b.get("text", "")
                     break
            if content_str.startswith(COMPACT_SUMMARY_PREFIX):
               skip_summary_lines.add(j)
               compaction_summaries_bytes += len(content_str)
            break

   # Second pass: parse entries
   for i, line in enumerate(lines):
      try:
         obj = json.loads(line)
      except json.JSONDecodeError:
         continue

      msg_type = obj.get("type")
      subtype = obj.get("subtype", "")

      # Insert compaction/microcompaction marker
      if i in compact_boundaries:
         compaction_count += 1
         cm = compact_boundaries[i]
         trigger = cm["trigger"]
         pre_tokens = cm["preTokens"]
         kind = cm["kind"]
         entries.append({
            "role": "compaction",
            "number": compaction_count,
            "trigger": trigger,
            "pre_tokens": pre_tokens,
            "kind": kind,
         })
         continue

      # Skip compact summary user messages
      if i in skip_summary_lines:
         continue

      # Track unknown types
      if msg_type == "system":
         if subtype not in known_system_subtypes:
            key = f"system:{subtype}" if subtype else "system"
            unknown_types[key] = unknown_types.get(key, 0) + 1
      elif msg_type not in known_types:
         unknown_types[msg_type] = unknown_types.get(msg_type, 0) + 1

      if msg_type == "user":
         msg = obj.get("message", {})
         content = msg.get("content", "")
         timestamp = obj.get("timestamp", "")
         cwd = obj.get("cwd", "")
         branch = obj.get("gitBranch", "")
         perm_mode = obj.get("permissionMode", "")

         if cwd and not metadata.get("cwd"):
            metadata["cwd"] = cwd
         if branch and not metadata.get("branch"):
            metadata["branch"] = branch
         if timestamp and not metadata.get("start_time"):
            metadata["start_time"] = timestamp
         metadata["last_time"] = timestamp
         if perm_mode:
            metadata["permission_mode"] = perm_mode

         texts = []
         tool_results_count = 0
         tool_results_bytes = 0

         if isinstance(content, str):
            if "<system-reminder>" in content:
               pass
            elif "<local-command-caveat>" in content:
               pass  # Skip caveat wrappers
            elif content.startswith(SKILL_INJECTION_PREFIX):
               condensed = condense_skill_injection(content)
               if condensed:
                  texts.append(condensed)
            elif content.startswith(PLAN_INJECTION_PREFIX):
               condensed = condense_plan_injection(content, plan_files)
               if condensed:
                  texts.append(condensed)
            elif "<task-notification>" in content:
               parsed = parse_task_notification(content)
               if parsed:
                  line_text, access_hint, _ = parsed
                  texts.append(line_text)
                  if access_hint:
                     texts.append(access_hint)
            elif "<command-name>" in content:
               m = re.search(r"<command-name>(.*?)</command-name>", content)
               if m:
                  cmd = m.group(1)
                  cmd_display = f"/{cmd}" if not cmd.startswith("/") else cmd
                  texts.append(f"[User ran: {cmd_display}]")
            elif "<local-command-stdout>" in content:
               m = re.search(
                  r"<local-command-stdout>(.*?)</local-command-stdout>",
                  content,
                  re.DOTALL,
               )
               if m:
                  stdout = m.group(1).strip()
                  if stdout:
                     texts.append(f"[Command output: {stdout[:200]}]")
            else:
               texts.append(content)
         elif isinstance(content, list):
            for block in content:
               if not isinstance(block, dict):
                  continue
               bt = block.get("type", "")
               if bt == "text":
                  text = block.get("text", "")
                  if "<system-reminder>" in text:
                     continue
                  if "<local-command-caveat>" in text:
                     continue
                  if text.startswith(SKILL_INJECTION_PREFIX):
                     condensed = condense_skill_injection(text)
                     if condensed:
                        texts.append(condensed)
                     continue
                  if text.startswith(PLAN_INJECTION_PREFIX):
                     condensed = condense_plan_injection(text, plan_files)
                     if condensed:
                        texts.append(condensed)
                     continue
                  if "<task-notification>" in text:
                     parsed = parse_task_notification(text)
                     if parsed:
                        line_text, access_hint, _ = parsed
                        texts.append(line_text)
                        if access_hint:
                           texts.append(access_hint)
                     continue
                  if "<command-name>" in text:
                     m = re.search(r"<command-name>(.*?)</command-name>", text)
                     if m:
                        cmd = m.group(1)
                        cmd_display = f"/{cmd}" if not cmd.startswith("/") else cmd
                        texts.append(f"[User ran: {cmd_display}]")
                     continue
                  if "<local-command-stdout>" in text:
                     m = re.search(
                        r"<local-command-stdout>(.*?)</local-command-stdout>",
                        text,
                        re.DOTALL,
                     )
                     if m:
                        stdout = m.group(1).strip()
                        if stdout:
                           texts.append(f"[Command output: {stdout[:200]}]")
                     continue
                  if text.startswith("[Image:"):
                     texts.append(text)
                     continue
                  texts.append(text)
               elif bt == "tool_result":
                  tool_results_count += 1
                  tool_results_bytes += len(json.dumps(block.get("content", "")))
               elif bt == "image":
                  source = block.get("source", {})
                  media = source.get("media_type", "image")
                  texts.append(f"[Image: {media}]")

         if texts:
            entries.append({
               "role": "user",
               "texts": texts,
               "timestamp": timestamp,
               "tool_results_count": tool_results_count,
               "tool_results_bytes": tool_results_bytes,
            })

      elif msg_type == "assistant":
         msg = obj.get("message", {})
         content = msg.get("content", [])

         texts = []
         tool_calls = []

         if isinstance(content, list):
            for block in content:
               if not isinstance(block, dict):
                  continue
               bt = block.get("type", "")
               if bt == "text":
                  t = block.get("text", "").strip()
                  if t:
                     texts.append(t)
               elif bt == "tool_use":
                  tool_name = block.get("name", "?")
                  inp = block.get("input", {})
                  summary = summarize_tool_call(tool_name, inp)
                  tool_calls.append({
                     "name": tool_name,
                     "summary": summary,
                     "file_path": inp.get("file_path", ""),
                  })

         if texts or tool_calls:
            entries.append({
               "role": "assistant",
               "texts": texts,
               "tool_calls": tool_calls,
            })

   metadata["compaction_count"] = compaction_count
   metadata["compaction_summaries_bytes"] = compaction_summaries_bytes
   metadata["session_summary"] = session_summary
   metadata["unknown_types"] = unknown_types
   return entries, metadata, total_bytes, len(lines)


def merge_consecutive_tools(entries):
   """Merge consecutive assistant entries that only have tool_calls (no text)."""
   merged = []
   for entry in entries:
      if (
         entry["role"] == "assistant"
         and not entry.get("texts")
         and entry.get("tool_calls")
         and merged
         and merged[-1]["role"] == "assistant"
         and not merged[-1].get("texts")
         and merged[-1].get("tool_calls")
      ):
         # Merge tool calls into previous entry
         merged[-1]["tool_calls"].extend(entry["tool_calls"])
      else:
         merged.append(entry)
   return merged


def collect_skills_loaded(entries):
   """Collect all skills that were loaded during the session."""
   skills = []  # List of (skill_name, args_or_None)
   seen = set()

   for entry in entries:
      if entry.get("role") != "user":
         continue
      for text in entry.get("texts", []):
         if not text.startswith("[Skill loaded: "):
            continue
         # Extract skill name from "[Skill loaded: name (~X words / ~Y tokens)]"
         m = re.match(r"\[Skill loaded: ([\w-]+)", text)
         if not m:
            continue
         skill_name = m.group(1)
         # Extract arguments if present (next line)
         args = None
         args_m = re.search(r"\[Skill arguments: (.+?)\]", text)
         if args_m:
            args = args_m.group(1)
         # Deduplicate by (name, args) — same skill may be loaded twice with different args
         key = (skill_name, args)
         if key not in seen:
            seen.add(key)
            skills.append((skill_name, args))

   return skills


def collect_file_operations(entries):
   """Collect all file operations, grouped by file path."""
   files = {}

   for entry in entries:
      if entry.get("role") != "assistant":
         continue
      for tc in entry.get("tool_calls", []):
         name = tc["name"]
         path = tc.get("file_path", "")
         if not path:
            continue
         if path not in files:
            files[path] = {"reads": 0, "edits": 0, "writes": 0}
         if name == "Read":
            files[path]["reads"] += 1
         elif name == "Edit":
            files[path]["edits"] += 1
         elif name == "Write":
            files[path]["writes"] += 1

   return files


def estimate_tokens(text):
   """Estimate token count from text using byte count / 3.0.

   Calibrated against Xenova/claude-tokenizer on 50 real compaction summaries
   and 4 real recall transcripts:
   - bytes/2.2 (old): avg error +37%, massively overcounted
   - bytes/3.0 (new): avg error +0.1%, avg |error| 7.5%
   """
   byte_count = len(text.encode("utf-8")) if isinstance(text, str) else len(text)
   return int(byte_count / 3.0)


def format_output(entries, metadata, total_bytes, total_lines, transcript_path):
   """Format the condensed transcript."""
   home = str(Path.home())
   output = []

   cwd = metadata.get("cwd", "unknown")
   branch = metadata.get("branch", "unknown")
   start = metadata.get("start_time", "")
   end = metadata.get("last_time", "")
   perm = metadata.get("permission_mode", "")
   compactions = metadata.get("compaction_count", 0)
   stripped_bytes = metadata.get("compaction_summaries_bytes", 0)
   session_summary = metadata.get("session_summary", "")
   session_id = metadata.get("session_id", "")
   unknown_types = metadata.get("unknown_types", {})

   output.append("# Session Resume")
   output.append("")
   if session_summary:
      output.append(f"- **Summary:** {session_summary}")
   output.append(f"- **Project:** {cwd}")
   output.append(f"- **Branch:** {branch}")
   if perm:
      output.append(f"- **Permission mode:** {perm}")
   if session_id:
      output.append(f"- **Session ID:** {session_id}")
   output.append(f"- **Transcript:** {transcript_path}")
   if start:
      output.append(f"- **Started:** {start[:19]}")
   if end:
      output.append(f"- **Last activity:** {end[:19]}")
   output.append(
      f"- **Original transcript:** {total_bytes / 1024 / 1024:.1f} MB ({total_lines} lines)"
   )
   if compactions:
      output.append(
         f"- **Compactions:** {compactions} (summaries stripped, {stripped_bytes:,} bytes saved)"
      )
   output.append("")

   # Stats
   user_msgs = sum(1 for e in entries if e.get("role") == "user")
   assistant_msgs = sum(1 for e in entries if e.get("role") == "assistant")
   total_tool_calls = sum(
      len(e.get("tool_calls", [])) for e in entries if e.get("role") == "assistant"
   )
   agent_calls = sum(
      1
      for e in entries
      if e.get("role") == "assistant"
      for tc in e.get("tool_calls", [])
      if tc["name"] == "Agent"
   )

   output.append("# Statistics")
   output.append("")
   output.append(f"- **User messages:** {user_msgs}")
   output.append(f"- **Assistant responses:** {assistant_msgs}")
   output.append(f"- **Tool calls:** {total_tool_calls}")
   output.append(f"- **Subagent calls:** {agent_calls}")
   output.append("")

   # File operations
   files = collect_file_operations(entries)
   if files:
      output.append("# Files Touched")
      output.append("")
      sorted_files = sorted(
         files.items(),
         key=lambda x: (
            -(x[1]["edits"] + x[1]["writes"]),
            x[0],
         ),
      )
      for path, ops in sorted_files:
         short_path = path.replace(home, "~")
         parts = []
         if ops["reads"]:
            parts.append(f"read {ops['reads']}x")
         if ops["edits"]:
            parts.append(f"edited {ops['edits']}x")
         if ops["writes"]:
            parts.append(f"written {ops['writes']}x")
         output.append(f"- `{short_path}` ({', '.join(parts)})")
      output.append("")

   # Skills loaded
   skills = collect_skills_loaded(entries)
   if skills:
      output.append("# Skills Loaded")
      output.append("")
      for skill_name, args in skills:
         line = f"- {skill_name}"
         if args:
            line += f" (args: {args})"
         output.append(line)
      output.append("")

   # Warnings about unknown entry types
   if unknown_types:
      output.append("# Warnings")
      output.append("")
      output.append("Unknown entry types encountered (may indicate transcript format changes):")
      output.append("")
      for type_key, count in sorted(unknown_types.items()):
         output.append(f"- {type_key}: {count} entries skipped")
      output.append("")
      output.append("Consider updating the recall skill if these are important.")
      output.append("")

   # Conversation
   output.append("# Conversation")
   output.append("")
   output.append("---")
   output.append("")

   exchange_num = 0
   for entry in entries:
      role = entry.get("role")

      if role == "compaction":
         num = entry["number"]
         trigger = entry["trigger"]
         pre_tokens = entry["pre_tokens"]
         kind = entry.get("kind", "compact")
         if kind == "microcompact":
            output.append("> [!WARNING]")
            output.append(f"> **Microcompaction #{num}**")
         else:
            output.append("> [!WARNING]")
            output.append(
               f"> **Compaction #{num}** ({trigger}, {pre_tokens:,} tokens before)"
            )
         output.append("")

      elif role == "user":
         exchange_num += 1
         ts = entry.get("timestamp", "")[:19]
         content_lines = [t.strip() for t in entry["texts"]]
         tr_count = entry.get("tool_results_count", 0)
         tr_bytes = entry.get("tool_results_bytes", 0)
         if tr_count:
            tr_tokens = int(tr_bytes / 3.0)
            content_lines.append(
               f"[+ {tr_count} tool results returned, ~{tr_tokens:,} tokens]"
            )
         entry_tokens = estimate_tokens("\n".join(content_lines))
         output.append("> [!NOTE]")
         output.append(
            f"> **User #{exchange_num}** · {ts} · {entry_tokens} tokens"
         )
         output.append(">")
         for line in content_lines:
            output.append(f"> {line}")
         output.append("")

      elif role == "assistant":
         if entry.get("texts"):
            texts_combined = "\n".join(t.strip() for t in entry["texts"])
            words = count_words(texts_combined)
            entry_tokens = estimate_tokens(texts_combined)
            output.append(
               f"**Assistant** · {words} words / {entry_tokens} tokens"
            )
            output.append("")
            for text in entry["texts"]:
               output.append(text.strip())
            output.append("")

         if entry.get("tool_calls"):
            n = len(entry["tool_calls"])
            tools_text = "\n".join(tc['summary'] for tc in entry["tool_calls"])
            entry_tokens = estimate_tokens(tools_text)
            output.append(
               f"> **Tools** ({n} call{'s' if n > 1 else ''} / {entry_tokens} tokens)"
            )
            for tc in entry["tool_calls"]:
               output.append(f"> {tc['summary']}")
            output.append("")
            output.append("---")
            output.append("")

   # Add token estimate at the very end
   full_text = "\n".join(output)
   est_tokens = estimate_tokens(full_text)
   # Insert token estimate into the header (after Statistics)
   stats_line = f"- **Estimated tokens:** ~{est_tokens:,}"
   # Find the right place to insert
   for idx, line in enumerate(output):
      if line == "# Statistics":
         # Find the empty line after stats
         for j in range(idx + 1, len(output)):
            if output[j] == "":
               output.insert(j, stats_line)
               break
         break

   return "\n".join(output)


def main():
   if len(sys.argv) < 2:
      print(
         "Usage: python3 parse-transcript.py <session-id> [--cwd <path>]",
         file=sys.stderr,
      )
      sys.exit(1)

   session_id = sys.argv[1]
   project_path = None

   if "--cwd" in sys.argv:
      idx = sys.argv.index("--cwd")
      if idx + 1 < len(sys.argv):
         project_path = sys.argv[idx + 1]

   transcript_path = find_transcript(session_id, project_path)
   if not transcript_path:
      print(
         f"ERROR: Could not find transcript for session {session_id}",
         file=sys.stderr,
      )
      sys.exit(1)

   print(f"Found: {transcript_path}", file=sys.stderr)

   entries, metadata, total_bytes, total_lines = parse_session(transcript_path)
   metadata["session_id"] = session_id

   # Merge consecutive tool-only assistant entries
   entries = merge_consecutive_tools(entries)

   # Split oversized bot messages into chunks of MAX_ENTRIES_PER_MESSAGE.
   # When Claude works autonomously, a single "bot message" (everything between
   # two user messages) can have hundreds of entries. Splitting keeps the output
   # readable and ensures condense-tail.py can split at meaningful boundaries.
   MAX_ENTRIES_PER_MESSAGE = 10
   split_entries = []
   i = 0
   while i < len(entries):
      entry = entries[i]
      if entry.get("role") == "user":
         split_entries.append(entry)
         # Collect all consecutive non-user entries (the "bot message")
         bot_entries = []
         j = i + 1
         while j < len(entries) and entries[j].get("role") != "user":
            if entries[j].get("role") in ("assistant", "compaction"):
               bot_entries.append(entries[j])
            j += 1
         # Split bot entries into chunks of MAX_ENTRIES_PER_MESSAGE
         if len(bot_entries) > MAX_ENTRIES_PER_MESSAGE:
            for chunk_start in range(0, len(bot_entries), MAX_ENTRIES_PER_MESSAGE):
               chunk = bot_entries[chunk_start:chunk_start + MAX_ENTRIES_PER_MESSAGE]
               split_entries.extend(chunk)
               # Insert a synthetic user marker between chunks (except after the last)
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
         # Orphan non-user entry at the start (before any user message)
         split_entries.append(entry)
         i += 1
   entries = split_entries

   # No message cap — condense-tail.py handles sizing (15K tail + 85K older context).
   # The full parsed output preserves all exchanges for maximum context recovery.

   output = format_output(entries, metadata, total_bytes, total_lines, str(transcript_path))

   # Stats
   output_bytes = len(output.encode("utf-8"))
   compression = (1 - output_bytes / total_bytes) * 100
   est_tokens = estimate_tokens(output)

   print(
      f"Condensed: {output_bytes:,} bytes (~{est_tokens:,} tokens)", file=sys.stderr
   )
   print(f"Compression: {compression:.1f}% reduction", file=sys.stderr)

   print(output)


if __name__ == "__main__":
   main()
