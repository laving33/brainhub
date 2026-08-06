---
name: brainhub-ingest
description: Use when raw files are present, source pages look stale, or a user asks to ingest notes into BrainHub; refresh source-backed wiki pages, propose memories, and validate updates through the CLI without MCP.
---

# BrainHub Ingest

Use `bh ingest-status` as the source of truth. Load this skill when the user drops files into `raw/`, mentions new notes/transcripts/docs, or asks what BrainHub should learn next. In a source checkout, replace `bh` with `python3 brainhub_engine.py`. The command tells you which raw files need work and which checks must run next.

1. Inspect the ingest plan:
   ```bash
   bh ingest-status [link-root]
   ```
2. If BrainHub reports secret-looking values, unreadable files, or unsafe paths, stop and ask the user to fix or redact them.
3. Read only the pending raw files named by the ingest plan. Create or update one `wiki/sources/...` page per raw file, and update existing concept/entity/exploration/memory pages before creating thin duplicates.
4. Keep durable memory proposal-only until the user approves it:
   ```bash
   bh propose-memories raw/<file> [link-root]
   ```
5. After writing wiki pages, rebuild generated indexes and validate:
   ```bash
   bh rebuild-index [link-root]
   bh rebuild-backlinks [link-root]
   bh validate [link-root]
   bh health [link-root]
   ```

Do not put raw source contents into chat unless needed for the current ingest task. Preserve source paths and provenance on generated pages.
