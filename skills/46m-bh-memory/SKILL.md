---
name: 46m-bh-memory
description: Manages the BrainHub durable-memory lifecycle through the CLI — remember, recall, review, update, archive, restore, forget, explain — without needing MCP. Use after important user-approved decisions, when durable context should be proposed or reviewed, and for explicit memory-lifecycle requests.
allowed-tools: Bash(bh:*), Read
---

# BrainHub Memory

Use this skill after important user-approved decisions, preference changes, project conventions, or long work sessions that may deserve durable context. In a source checkout, replace `bh` with `python3 brainhub_engine.py`. Do not silently save durable memory; propose first unless the user directly asks to remember, approves a proposal, or explicitly confirms an important decision should become durable memory.

If BrainHub session hooks are installed for this agent, the memory brief is injected automatically at session start — skip step 1 and go straight to task-specific recall.

1. Prime before work:
   ```bash
   bh brief "<current task>" [link-root]
   ```
2. Recall specific memory:
   ```bash
   bh recall "<topic>" [link-root]
   ```
3. End a session with proposal-only memory candidates:
   ```bash
   bh session-end <session-notes-or-transcript> [link-root] --limit 3
   ```
   Use `-` as the input when piping a transcript on stdin. Show the proposals to the user; do not save durable memory until the user approves one.
4. Save an explicit memory:
   ```bash
   bh remember "<user-approved memory>" [link-root] --type note --scope user
   ```
   Use `--project <slug>` for project-scoped memory, `--visibility private|project|team` for sharing intent, `--review-after YYYY-MM-DD` for stale-risk memories, and `--expires-at YYYY-MM-DD` for temporary context.
When a brief or recall reports a memory backlog (pending captures or reviews above threshold), offer the user a short consolidation pass:
   ```bash
   bh consolidate [link-root]
   ```
   The plan is read-only: it groups duplicates and recurring themes and prints accept/discard/review commands. Apply an action only after the user approves it.

5. Review and explain before trusting uncertain memory:
   ```bash
   bh memory-inbox [link-root]
   bh explain-memory <name-or-title> [link-root]
   bh review-memory <name-or-title> [link-root]
   ```
6. Change lifecycle safely:
   ```bash
   bh update-memory <name-or-title> "<new text>" [link-root]
   bh archive-memory <name-or-title> [link-root] --reason "<why>"
   bh restore-memory <name-or-title> [link-root]
   bh forget-memory <name-or-title> [link-root] --confirm
   ```

When duplicate or conflict warnings appear, prefer updating, reviewing, or archiving existing memory over creating another page.
