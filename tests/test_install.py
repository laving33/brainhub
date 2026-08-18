"""What `install.sh` has to keep true.

The installer's value is that it runs the tree on a CLEAN interpreter. That is
what caught a claim this README carried for a long time — "the engine, CLI, and
web viewer run on Python 3.10+ standard library alone" — while all three entry
points import markdown-it-py through `brainhub_core.markdown`. Every developer
and every test ran inside an environment that already had it, so nothing
noticed.
"""
import ast
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ROOT / "install.sh"
GUARD = ROOT / "_python_check.py"
ENTRY_POINTS = ("brainhub.py", "brainhub_engine.py", "serve.py")


class VersionGuardTests(unittest.TestCase):
    def test_entry_points_parse_on_older_pythons_than_they_support(self):
        # A guard that only parses on the versions it is meant to reject never
        # runs: the interpreter fails at compile time and the user sees a
        # SyntaxError instead of the sentence.
        for name in ENTRY_POINTS:
            with self.subTest(entry=name):
                source = (ROOT / name).read_text(encoding="utf-8")
                ast.parse(source, feature_version=(3, 7))

    def test_entry_points_check_the_version_before_anything_else(self):
        for name in ENTRY_POINTS:
            with self.subTest(entry=name):
                source = (ROOT / name).read_text(encoding="utf-8")
                tree = ast.parse(source)
                imports = [
                    node
                    for node in tree.body
                    if isinstance(node, (ast.Import, ast.ImportFrom))
                ]
                self.assertTrue(imports, f"{name} imports nothing?")
                names = []
                for node in imports:
                    if isinstance(node, ast.Import):
                        names.extend(alias.name for alias in node.names)
                    else:
                        names.append(node.module or "")
                # __future__ must legally come first; the guard must be next, and
                # in particular ahead of anything that could fail to import.
                ordered = [n for n in names if n != "__future__"]
                self.assertEqual(
                    ordered[0], "_python_check",
                    f"{name} imports {ordered[0]!r} before the version guard",
                )

    def test_guard_itself_parses_on_python_3_7(self):
        ast.parse(GUARD.read_text(encoding="utf-8"), feature_version=(3, 7))

    def test_guard_minimum_matches_what_the_installer_provisions(self):
        minimum = re.search(r"^MINIMUM = \((\d+), (\d+)\)", GUARD.read_text(encoding="utf-8"), re.M)
        self.assertIsNotNone(minimum)
        guard_version = f"{minimum.group(1)}.{minimum.group(2)}"
        pinned = re.search(
            r'^PINNED_PYTHON="([^"]+)"', INSTALL.read_text(encoding="utf-8"), re.M
        )
        self.assertIsNotNone(pinned, "install.sh declares no PINNED_PYTHON")
        self.assertEqual(pinned.group(1), guard_version)

    def test_lockfile_and_packaging_agree_on_the_floor(self):
        # uv.lock's requires-python is rewritten silently by `uv run --python X`;
        # nothing else compares it to what the package declares.
        lock = re.search(
            r'^requires-python = ">=([\d.]+)"', (ROOT / "uv.lock").read_text(encoding="utf-8"), re.M
        )
        pyproject = re.search(
            r'requires-python\s*=\s*">=([\d.]+)',
            (ROOT / "mcp_package" / "pyproject.toml").read_text(encoding="utf-8"),
        )
        self.assertIsNotNone(lock, "uv.lock declares no requires-python")
        self.assertEqual(lock.group(1), pyproject.group(1))

    def test_installer_requires_uv_rather_than_falling_back(self):
        # A system-python fallback means every line here must keep working on
        # whatever the oldest supported distribution ships.
        source = INSTALL.read_text(encoding="utf-8")
        self.assertNotIn("--system-python", source.split("# Usage:")[1])
        self.assertIn("astral.sh/uv/install.sh", source)

    def test_guard_minimum_matches_the_packaging_metadata(self):
        pyproject = (ROOT / "mcp_package" / "pyproject.toml").read_text(encoding="utf-8")
        requires = re.search(r'requires-python\s*=\s*">=([\d.]+)', pyproject)
        self.assertIsNotNone(requires)
        minimum = re.search(r"^MINIMUM = \((\d+), (\d+)\)", GUARD.read_text(encoding="utf-8"), re.M)
        self.assertEqual(requires.group(1), f"{minimum.group(1)}.{minimum.group(2)}")


class InstallerTests(unittest.TestCase):
    def test_installer_is_executable(self):
        self.assertTrue(INSTALL.exists())
        self.assertTrue(INSTALL.stat().st_mode & 0o111, "install.sh is not executable")

    def test_installer_is_valid_shell(self):
        result = subprocess.run(
            ["bash", "-n", str(INSTALL)], capture_output=True, text=True, timeout=60
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_installer_verifies_by_running_the_tree(self):
        # Checking a version number alone is exactly what let the
        # standard-library-only claim survive; the installer must actually
        # execute an entry point before it writes a wrapper.
        source = INSTALL.read_text(encoding="utf-8")
        self.assertRegex(source, r'\$VENV_PYTHON" "\$ROOT/brainhub\.py" --help')

    def test_installer_resolves_a_uv_python_outside_the_project(self):
        # `uv python find` prefers a .venv discovered from the working
        # directory, so run inside a checkout it returns the DEVELOPMENT
        # virtualenv — which then gets baked into the installed wrapper.
        source = INSTALL.read_text(encoding="utf-8")
        self.assertIn("--managed-python", source)
        self.assertIn("env -u VIRTUAL_ENV", source)


class DependencyHonestyTests(unittest.TestCase):
    def test_entry_points_are_not_advertised_as_standard_library_only(self):
        # They import markdown-it-py. Saying otherwise sends people to an
        # install that cannot run.
        for doc in ("README.md", "BRAINHUB.md"):
            with self.subTest(doc=doc):
                text = (ROOT / doc).read_text(encoding="utf-8").lower()
                for claim in ("standard library alone", "stdlib only", "zero dependencies"):
                    self.assertNotIn(claim, text)

    def test_markdown_stack_is_a_declared_dependency(self):
        pyproject = (ROOT / "mcp_package" / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("markdown-it-py", pyproject)


if __name__ == "__main__":
    unittest.main()
