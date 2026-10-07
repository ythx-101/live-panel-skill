"""Browser regression tests for optional cycle fields and out-of-order seeks.

Uses the same Chrome transport as the renderer, with no third-party packages.
Run: CHROME=/path/to/chrome python3 -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import livepanel as lp
from check_frames import TOL_PIXELS, pixel_diff


class CycleReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        chrome = lp.find_exe(os.environ.get("CHROME"), lp.CHROME_NAMES, "Chrome")
        cls.browser = lp.Chrome(chrome, 400, 300)
        cls.directory = tempfile.TemporaryDirectory(prefix="livepanel-cycle-test-")
        cls.page = Path(cls.directory.name) / "page.html"
        config = {
            "canvas": {"width": 400, "height": 300, "duration": 3},
            "theme": {"preset": "light-pastel", "font": "Arial", "colors": {
                "active": "#22aa66", "inactive": "#445566"
            }},
            "machines": {
                "seq.other": {"type": "counter", "start": 123, "rate": 0},
                "seq": {"type": "cycle", "period": 1, "values": [
                    {"t": "done"},
                    {"m": "working", "note": "pending", "legacy": "old"},
                    "idle",
                ]},
            },
            "elements": [
                {"type": "text", "x": 20, "y": 20 + 30 * i, "runs": [{"v": field}]}
                for i, field in enumerate([
                    "seq", "seq.t", "seq.m", "seq.note", "seq.legacy", "seq.i", "seq.other"
                ])
            ] + [{
                "type": "box", "x": 20, "y": 240, "w": 120, "h": 40,
                "fill": "inactive", "when": {"var": "seq.note", "eq": "pending"},
                "then": {"fill": "active"},
            }],
        }
        config_path = Path(cls.directory.name) / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        lp.build_page(config_path, cls.page)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.directory.cleanup()

    def setUp(self):
        self.browser.open(self.page.as_uri() + "?manual")

    def frame(self, t):
        self.browser.seek(t)
        return self.browser.eval("""({
            text: Array.from(document.querySelectorAll('#stage > [data-t="text"]'), e => e.textContent),
            fill: getComputedStyle(document.querySelector('.box')).backgroundColor,
            error: window.__error || ''
        })""")

    def test_optional_fields_follow_current_value(self):
        expected = [
            ["done", "done", "", "", "", "0", "123"],
            ["working", "", "working", "pending", "old", "1", "123"],
            ["idle", "idle", "", "", "", "2", "123"],
        ]
        for index in [0, 1, 2, 1, 0]:
            with self.subTest(index=index):
                actual = self.frame(index + 0.25)
                self.assertEqual(actual["text"], expected[index])
                self.assertEqual(actual["fill"], "rgb(34, 170, 102)" if index == 1 else "rgb(68, 85, 102)")
                self.assertEqual(actual["error"], "")

    def test_returning_to_same_time_restores_text_and_highlight(self):
        direct = self.frame(0.25)
        self.frame(1.25)
        self.assertEqual(self.frame(0.25), direct)

    def test_returning_to_same_time_restores_pixels(self):
        self.frame(0.25)
        direct = self.browser.shot()
        self.frame(1.25)
        self.browser.shot()
        self.frame(0.25)
        again = self.browser.shot()
        different, _ = pixel_diff(self.browser, direct, again)
        self.assertLessEqual(different, TOL_PIXELS)


if __name__ == "__main__":
    unittest.main()
