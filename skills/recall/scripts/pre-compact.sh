#!/bin/bash
# pre-compact.sh — Runs on PreCompact to generate the recall transcript.
# Parses the session transcript and condenses if too large (single Sonnet call).
# Writes to both /tmp/ (for manual /recall) and .claude/recall-context.md
# (for automatic injection via CLAUDE.md @-reference after compaction).
#
# Output targets 15-20K tokens (~10% of Claude Code's 200K context window).
#
# Hook input (stdin JSON): { "session_id": "...", "cwd": "...", "trigger": "auto|manual", ... }
# Hook output: None (PreCompact stdout is not injected into context).

# Recursion guard: if claude -p is called for condensation, it might trigger
# its own compaction, which would fire this hook again. Prevent infinite loops.
if [ -n "$RECALL_HOOK_ACTIVE" ]; then
   exit 0
fi
export RECALL_HOOK_ACTIVE=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INPUT=$(cat)

SESSION_ID=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
CWD=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null)

if [ -z "$SESSION_ID" ]; then
   exit 0
fi

OUTPUT_FILE="/tmp/recall-${SESSION_ID}.md"

# Step 1: Run the parser (stderr goes to log, stdout to file)
python3 "${SCRIPT_DIR}/parse-transcript.py" "$SESSION_ID" --cwd "$CWD" > "$OUTPUT_FILE" 2>/tmp/recall-precompact.log

if [ ! -f "$OUTPUT_FILE" ] || [ ! -s "$OUTPUT_FILE" ]; then
   exit 0
fi

# Step 2: Condense if needed (>20K tokens)
# Keeps ~15K tokens of recent exchanges verbatim, summarizes older context
# with a single claude -p --model sonnet call into ~2.5K tokens.
CONDENSE_EXIT=0
python3 "${SCRIPT_DIR}/condense-tail.py" split "$OUTPUT_FILE" "$SESSION_ID" 2>>/tmp/recall-precompact.log || CONDENSE_EXIT=$?

if [ "$CONDENSE_EXIT" -eq 0 ]; then
   SID_PREFIX="${SESSION_ID:0:8}"

   # Must unset CLAUDECODE to allow claude -p from within Claude Code
   unset CLAUDECODE

   cat "/tmp/recall-older-${SID_PREFIX}.md" | \
     claude -p --model sonnet --no-session-persistence \
       "$(cat /tmp/recall-prompt-${SID_PREFIX}.txt)" \
       > "/tmp/recall-summary-${SID_PREFIX}.md" 2>>/tmp/recall-precompact.log

   python3 "${SCRIPT_DIR}/condense-tail.py" combine "$OUTPUT_FILE" "$SESSION_ID" 2>>/tmp/recall-precompact.log
fi

# Step 3: Write to $CWD/.claude/recall-context.md for automatic injection.
# After compaction, Claude Code re-reads CLAUDE.md from disk. If the project's
# CLAUDE.md (or AGENTS.md) contains @.claude/recall-context.md, the recall content
# is pulled into context automatically — no SessionStart stdout needed.
if [ -n "$CWD" ] && [ -d "$CWD/.claude" ]; then
   CONTEXT_FILE="$CWD/.claude/recall-context.md"
   SID_PREFIX="${SESSION_ID:0:8}"
   STATS_FILE="/tmp/recall-stats-${SID_PREFIX}.json"

   # Build the header with stats from condense-tail.py
   if [ -f "$STATS_FILE" ]; then
      # Read all stats in a single python3 call for efficiency
      # Values with commas must be quoted for bash eval
      eval "$(python3 -c "
import json
d = json.load(open('$STATS_FILE'))
print(f\"CONDENSED={'yes' if d['condensed'] else 'no'}\")
print(f\"ORIGINAL_TOKENS='{d['original_tokens']:,}'\")
print(f\"FINAL_TOKENS='{d.get('final_tokens', d['original_tokens']):,}'\")
print(f\"TOTAL_EXCHANGES={d['total_exchanges']}\")
print(f\"TAIL_EXCHANGES={d['tail_exchanges']}\")
print(f\"VERBATIM_PCT={d['verbatim_pct']}\")
print(f\"SUMMARIZED_PCT={d['summarized_pct']}\")
print(f\"DROPPED_PCT={d['dropped_pct']}\")
print(f\"TAIL_TOKENS='{d.get('tail_tokens', d.get('final_tokens', d['original_tokens'])):,}'\")
" 2>/dev/null)"

      if [ "$CONDENSED" = "yes" ]; then
         STATS_BLOCK="=== RECALL STATS ===
Session: ${SESSION_ID}
Original transcript: ~${ORIGINAL_TOKENS} tokens (${TOTAL_EXCHANGES} exchanges)
Condensation: YES — older context summarized by Sonnet
  Verbatim tail: ${VERBATIM_PCT}% of original (last ${TAIL_EXCHANGES} exchanges, ~${TAIL_TOKENS} tokens)
  Summarized: ${SUMMARIZED_PCT}% of original (older exchanges condensed to ~2,500 tokens)
  Dropped: ${DROPPED_PCT}% (earliest exchanges beyond context cap)
Final size: ~${FINAL_TOKENS} tokens"
      else
         STATS_BLOCK="=== RECALL STATS ===
Session: ${SESSION_ID}
Original transcript: ~${ORIGINAL_TOKENS} tokens (${TOTAL_EXCHANGES} exchanges)
Condensation: NO — full transcript preserved (100% verbatim)
Final size: ~${FINAL_TOKENS} tokens"
      fi

      # Clean up stats file
      rm -f "$STATS_FILE"
   else
      # Fallback if stats file missing
      STATS_BLOCK="=== RECALL STATS ===
Session: ${SESSION_ID}
(Stats unavailable — condensation status unknown)"
   fi

   cat > "$CONTEXT_FILE" << HEADER
<!-- Recall: Pre-compaction transcript (auto-generated, auto-cleaned) -->

${STATS_BLOCK}

INSTRUCTIONS: This is the detailed conversation from before compaction — far richer than
the compaction summary. After reading this, do ALL of the following:

1. Print a single status line: "Recall loaded: ~X tokens (Y% verbatim, Z% summarized)"
   using the stats above. If 100% verbatim, just say "Recall loaded: ~X tokens (full transcript)".
2. UNDERSTAND the conversation arc and identify the last pending task
3. RE-READ files needed for pending work (check FILES TOUCHED section)
4. RE-LOAD skills from the SKILLS LOADED section if needed
5. CONTINUE working on the pending task seamlessly

If no work is pending, briefly summarize what was accomplished and ask what to do next.

---

HEADER
   cat "$OUTPUT_FILE" >> "$CONTEXT_FILE"
fi

exit 0
