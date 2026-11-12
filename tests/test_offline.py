"""Regression tests that need no browser: Excalidraw importer, scaffold, example JSON."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EXAMPLES = ROOT / "examples"


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, cwd=ROOT)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class OfflineTests(unittest.TestCase):
    def test_excalidraw_import_matches_example(self):
        src = EXAMPLES / "excalidraw-import" / "agent-loop.excalidraw"
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out.json"
            r = run(SCRIPTS / "excalidraw_import.py", src, "-o", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            got = load(out)
        want = load(EXAMPLES / "excalidraw-import" / "config.json")
        for c in (got, want):
            c.get("meta", {}).pop("source", None)
        self.assertEqual(got, want)

    def test_scaffold_example_roundtrip(self):
        ex = run(SCRIPTS / "scaffold.py", "--example")
        self.assertEqual(ex.returncode, 0, ex.stderr)
        with tempfile.TemporaryDirectory() as d:
            spec, out = Path(d) / "spec.json", Path(d) / "config.json"
            spec.write_text(ex.stdout, encoding="utf-8")
            r = run(SCRIPTS / "scaffold.py", "--spec", spec, "--out", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            cfg = load(out)
        self.assertTrue(cfg.get("elements"))
        self.assertTrue(cfg.get("machines"))

    def test_example_files_parse(self):
        files = sorted(EXAMPLES.rglob("*.json")) + sorted(EXAMPLES.rglob("*.excalidraw"))
        self.assertTrue(files)
        for p in files:
            with self.subTest(file=str(p.relative_to(ROOT))):
                load(p)


if __name__ == "__main__":
    unittest.main()
