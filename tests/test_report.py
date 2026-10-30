"""The backend section of report.json and report.md, with a mock config. No service is called and no file is parsed.

Run from the repository root: python3 -m unittest discover -s tests -v
"""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from mineru_plus import backends, config, run  # noqa: E402

PATHS = "/nonexistent/private/tool-call.py"    # stands in for a local helper path; must never reach the report

# The config of the measured setup, except that the page judge runs through agy (a command, so the model is not named).
MEASURED_LIKE = {
    "primary_reader": {"backend": "gateway", "tool_call": PATHS, "tier": "advanced"},
    "second_reader": {"backend": "gateway", "tool_call": PATHS},
    "decision_judge": {"backend": "gateway", "jev_call": PATHS, "model": "d3-ultra"},
    "page_judge": {"backend": "agy", "command": "agy-min"},
}
CALIBRATION_LINE = "Calibration measured with: primary_reader gateway (tool mineru, tier advanced); "


class ReportBackendsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        config.reset()
        backends.reset()
        self.addCleanup(config.reset)
        self.addCleanup(backends.reset)

    def configure(self, doc):
        p = Path(self.tmp.name) / "mineru_plus.json"
        p.write_text(json.dumps(doc))
        config.load(p)
        backends.reset()

    def report(self):
        """The fields render() reads, with the backend section built from the config as run() builds it."""
        return {"version": "0.5.5", "input": "/nonexistent/paper.pdf",
                "scope": {"pages": 1, "pages_without_text_layer": [], "blocks_by_type": {}}, "readers": {},
                "figures": {"transcriptions": 0, "moved_out_of_text": 0, "tokens": 0, "tokens_printed": 0,
                            "figures_without_text_layer": 0},
                "checks": {}, "backends": run.backend_report(), "calibration": {"example": "a calibration line"},
                "unchecked": [], "open_issues": 0}

    def test_backends_section_lists_each_role_and_one_calibration_line(self):
        self.configure(MEASURED_LIKE)
        rep = run.backend_report()
        self.assertEqual(rep["decision_judge"], {"backend": "gateway", "model": "d3-ultra"})
        self.assertNotIn("as_measured", json.dumps(rep))
        text = run.render(self.report())
        self.assertIn("## Backends of this run", text)
        self.assertIn("- decision_judge: gateway (model d3-ultra)", text)
        self.assertIn("- page_judge: agy (command agy-min)", text)
        self.assertEqual(text.count("Calibration measured with: "), 1)
        self.assertIn(CALIBRATION_LINE, text)
        self.assertNotIn("does not apply", text)
        self.assertLess(text.index("## Backends of this run"), text.index("## How far the checks can be trusted"))
        self.assertLess(text.index("Calibration measured with"), text.index("## How far the checks can be trusted"))

    def test_a_changed_tier_or_model_is_shown_as_configured_and_the_calibration_line_is_unchanged(self):
        doc = json.loads(json.dumps(MEASURED_LIKE))
        doc["primary_reader"]["tier"] = "standard"
        doc["decision_judge"]["model"] = "other-judge"
        self.configure(doc)
        rep = run.backend_report()
        self.assertEqual(rep["primary_reader"]["tier"], "standard")
        self.assertEqual(rep["decision_judge"]["model"], "other-judge")
        text = run.render(self.report())
        self.assertIn("- primary_reader: gateway (tool mineru, tier standard)", text)
        self.assertIn("- decision_judge: gateway (model other-judge)", text)
        self.assertIn(CALIBRATION_LINE, text)

    def test_report_holds_no_secret_name_no_secret_value_and_no_path(self):
        doc = {
            "primary_reader": {"backend": "mineru_kit", "command": "/nonexistent/venv/bin/mineru-kit"},
            "decision_judge": {"backend": "openai", "base_url": "https://example.invalid/v1/PATHMARK",
                               "model": "judge-model", "api_key_env": "MP_TEST_SECRET_NAME"},
            "page_judge": {"backend": "agy", "command": "agy-min"},
        }
        self.configure(doc)
        with mock.patch.dict(os.environ, {"MP_TEST_SECRET_NAME": "value-that-must-not-appear"}):
            rep = self.report()
            text = run.render(rep) + json.dumps(rep["backends"], ensure_ascii=False)
        self.assertIn("mineru-kit", text)
        self.assertIn("judge-model", text)
        for leak in ("MP_TEST_SECRET_NAME", "value-that-must-not-appear", "PATHMARK", "/nonexistent", "example.invalid"):
            self.assertNotIn(leak, text)
        self.assertEqual(rep["backends"]["primary_reader"]["command"], "mineru-kit")

    def test_unconfigured_second_reader_is_described_by_its_state(self):
        doc = {k: v for k, v in MEASURED_LIKE.items() if k != "second_reader"}
        self.configure(doc)
        rep = run.backend_report()
        self.assertEqual(rep["second_reader"], {"backend": None, "note": "not configured"})
        text = run.render(self.report())
        self.assertIn("- second_reader: not configured", text)
        self.assertIn(CALIBRATION_LINE, text)


if __name__ == "__main__":
    unittest.main()
