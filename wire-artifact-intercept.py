#!/usr/bin/env python3
"""Wire the Artifact->brainhub intercept into ~/.claude/settings.json.

Idempotent + backed up + JSON-validated. Adds two things:
  1. permissions.deny  += "Artifact"                (structurally blocks claude.ai artifact publish + list)
  2. hooks.PreToolUse  += {matcher:"Artifact", ...}  (redirects the agent to `bh publish`/`bh build` (CLI))

Run this yourself in the terminal (it changes the permission surface, so an agent
must not run it):  python3 /home/aworkr/aworkr/tools/brainhub/wire-artifact-intercept.py
Undo: restore the printed backup, or set REVERT=1 in the env to remove both.
"""
import json
import os
import shutil
import sys
from datetime import datetime

SETTINGS = os.path.expanduser("~/.claude/settings.json")
HOOK_CMD = "python3 -S -E -s /home/aworkr/aworkr/core/hooks/intercept-artifact.py"
REVERT = os.environ.get("REVERT") == "1"

with open(SETTINGS) as f:
    d = json.load(f)

backup = f"{SETTINGS}.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
shutil.copy2(SETTINGS, backup)

perms = d.setdefault("permissions", {})
deny = perms.setdefault("deny", [])
hooks = d.setdefault("hooks", {})
pre = hooks.setdefault("PreToolUse", [])

def has_artifact_hook():
    return any(h.get("matcher") == "Artifact" for h in pre)

if REVERT:
    perms["deny"] = [x for x in deny if x != "Artifact"]
    hooks["PreToolUse"] = [h for h in pre if h.get("matcher") != "Artifact"]
    action = "REVERTED (removed Artifact deny + hook)"
else:
    if "Artifact" not in deny:
        deny.append("Artifact")
    if not has_artifact_hook():
        pre.append({
            "matcher": "Artifact",
            "hooks": [{
                "type": "command",
                "command": HOOK_CMD,
                "timeout": 5,
                "statusMessage": "artifact->brainhub",
            }],
        })
    action = "WIRED (Artifact deny + redirect hook)"

# validate before writing
text = json.dumps(d, ensure_ascii=False, indent=2)
json.loads(text)  # raises if malformed
with open(SETTINGS, "w") as f:
    f.write(text + "\n")

print(f"✓ {action}")
print(f"  backup: {backup}")
print(f"  permissions.deny now has 'Artifact': {'Artifact' in perms['deny']}")
print(f"  Artifact PreToolUse hook present: {has_artifact_hook()}")
print("\nNext: verify live — in a session, ask an agent to publish a HARMLESS test")
print("artifact (fake data, no client names). It should be BLOCKED and redirected")
print("to the brainhub CLI. If it still publishes to claude.ai, the hook did not fire —")
print("tell chief (matcher behaviour has diverged from docs before).")
