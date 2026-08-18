---
name: 46m-bh-retrieve
description: Retrieves compact BrainHub context through the CLI without loading the whole wiki or needing MCP. Use before answering work that may depend on user memory, project history, source-backed notes, or prior decisions.
allowed-tools: Bash(bh:*), Read
---

# BrainHub Retrieve

Use bounded CLI commands so the agent does not dump the whole wiki into context. Load this skill proactively at the first substantive turn of a session, before project/release/debug/design work, or whenever the answer may depend on prior BrainHub memory. In a source checkout, replace `bh` with `python3 brainhub_engine.py`.

1. If readiness is unclear, start with:
   ```bash
   bh health [link-root]
   ```
2. If the user is inside a project repo and BrainHub has no project context yet, seed allowlisted source-backed context before broad searching:
   ```bash
   bh seed . [link-root]
   ```
   This reads project docs/rule files, blocks secret-looking values, and does not create durable memories.
3. For most questions, use a compact query packet:
   ```bash
   bh query "<question or task>" [link-root] --budget micro
   ```
   Read `recall_capsule` first. Increase to `--budget small`, `--budget medium`, or `--budget large` only when the packet says more context is needed.
4. Before longer work, prime from memory:
   ```bash
   bh brief "<current task>" [link-root]
   ```
5. For graph context, stay bounded:
   ```bash
   bh graph-summary "<topic>" [link-root] --limit 40 --depth 1
   ```
6. For performance checks, use:
   ```bash
   bh benchmark "<topic>" [link-root] --budget small
   ```

Do not enumerate every page, grep raw files, or request the full graph unless the user explicitly asks for an export or exhaustive audit, or the compact packet is insufficient and tells you which follow-up to use.

Recalled memories carry `confidence` labels and, when the optional local semantic tier is installed, a `match` field: `lexical`, `hybrid`, or `semantic`. Treat `semantic` matches (paraphrase similarity, capped confidence) and `weak` matches as hints to verify with the user, not facts to act on.
