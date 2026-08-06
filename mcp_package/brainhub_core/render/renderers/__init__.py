"""BrainHub renderer modules.

Each module in this package registers exactly one renderer against the shared
``render.registry`` singleton at import time. Adding a renderer = dropping a new
module here; the parent package auto-imports every module in this directory so
its registration runs. No module in this package edits any shared file.
"""
