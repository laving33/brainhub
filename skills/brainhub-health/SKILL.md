---
name: brainhub-health
description: Use at the start of BrainHub work when readiness is unclear, after installs or upgrades, and before repairs; verify health, inspect interrupted writes, back up, and repair generated indexes without MCP.
---

# BrainHub Health

Use the `bh` CLI. Load this skill before trusting a new or changed BrainHub wiki, after installs/upgrades, and before broad repair or restore work. In a source checkout, replace `bh` with `python3 brainhub_engine.py`. MCP and the local web viewer are optional; `bh serve` is only for humans to browse the wiki.

1. Check readiness first:
   ```bash
   bh health [link-root]
   ```
2. If the output mentions interrupted or stale operations, inspect them before repair:
   ```bash
   bh operations [link-root]
   ```
3. Before broad repairs, migrations, or restore work, create a backup:
   ```bash
   bh backup [link-root]
   ```
4. Repair only generated or structural state that BrainHub reports as safe:
   ```bash
   bh doctor --fix [link-root]
   bh rebuild-index [link-root]
   bh rebuild-backlinks [link-root]
   ```
5. Validate before saying the wiki is healthy:
   ```bash
   bh validate [link-root]
   bh health [link-root]
   ```

If the user asks whether MCP is ready, run `bh verify-mcp [link-root]`. Do not start `bh serve` for MCP or CLI work.

To check whether optional local semantic recall is active (lexical is always the fallback):
```bash
bh semantic [link-root]
```
It reports the provider tier, model, and index state, and prints the exact setup command when the layer is available but not yet enabled.
