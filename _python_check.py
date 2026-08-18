"""Refuse an unsupported interpreter with a sentence, not a traceback.

Imported first by every entry point, before anything that uses newer syntax or
newer stdlib. Written in Python 3.7-compatible syntax on purpose: a guard that
only parses on the versions it is meant to reject never runs. `datetime.UTC`
(3.11+) once sat at the top of `brainhub.py`, so on Ubuntu 22.04's stock 3.10
every command — including `bh --help` — died with an ImportError naming a
stdlib module, which reads like a broken install rather than a version floor.

The floor tracks what `install.sh` provisions. There is no system-Python
path, so nothing older has to be accommodated — but a user can still point a
wrapper at any interpreter by hand, and this is what tells them why it failed.
"""
import sys

MINIMUM = (3, 12)


def require_supported_python():
    if sys.version_info >= MINIMUM:
        return
    running = ".".join(str(part) for part in sys.version_info[:3])
    wanted = ".".join(str(part) for part in MINIMUM)
    sys.stderr.write(
        "BrainHub needs Python {wanted} or newer; this is {running}\n"
        "  ({executable})\n"
        "\n"
        "Install BrainHub's own interpreter (no root, no system change):\n"
        "  curl -LsSf https://astral.sh/uv/install.sh | sh\n"
        "  ./install.sh\n".format(
            wanted=wanted,
            running=running,
            executable=sys.executable,
        )
    )
    raise SystemExit(1)


require_supported_python()
