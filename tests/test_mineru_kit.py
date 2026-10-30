"""Tests of the mineru_kit primary reader, with a stand-in for the mineru-kit command: no model is loaded and no service
is called.

Run from the repository root: python3 -m unittest discover -s tests -v
"""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from mineru_plus import backends, config  # noqa: E402

# Stands in for "mineru-kit parse PDF -o DIR --format zip". It records its argv and telemetry setting, then writes
# <stem>.zip into the -o directory, as the real command does. FAKE_MODE selects what the archive holds.
FAKE = '''#!__PY__
import json, os, pathlib, sys, zipfile
pathlib.Path(os.environ["FAKE_LOG"]).write_text(json.dumps(
    {"argv": sys.argv[1:], "telemetry": os.environ.get("MINERU_TELEMETRY_DISABLED")}))
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "exit":
    print("boom", file=sys.stderr)
    sys.exit(2)
pdf = pathlib.Path(sys.argv[2])
out = pathlib.Path(sys.argv[sys.argv.index("-o") + 1])
out.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(out / (pdf.stem + ".zip"), "w") as z:
    if mode != "no_structured":
        page = {"page_idx": 0, "blocks": [{"type": "text", "bbox": [0.1, 0.1, 0.9, 0.2], "content": "Hello"}]}
        z.writestr("structured_content.json", json.dumps({"pages": [page]}))
    if mode != "no_markdown":
        z.writestr("markdown.md", "Hello")
    if mode == "unsafe":
        z.writestr("../escaped.txt", "x")
    z.writestr("images/a.png", b"png")
'''


class MineruKitTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.fake = d / "fake-mineru-kit"
        self.fake.write_text(FAKE.replace("__PY__", sys.executable))
        self.fake.chmod(0o755)
        self.log = d / "argv.json"
        self.pdf = d / "paper.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 stand-in")
        self.out = d / "out"
        env = mock.patch.dict(os.environ, {"FAKE_LOG": str(self.log), "FAKE_MODE": "ok"})
        env.start()
        self.addCleanup(env.stop)
        config.reset()
        backends.reset()
        self.addCleanup(config.reset)
        self.addCleanup(backends.reset)

    def configure(self, **extra):
        p = Path(self.tmp.name) / "mineru_plus.json"
        spec = {"backend": "mineru_kit", "command": str(self.fake), **extra}
        p.write_text(json.dumps({"primary_reader": spec}))
        config.load(p)
        backends.reset()
        return backends.get("primary_reader")

    def logged(self):
        return json.loads(self.log.read_text())

    def test_archive_is_extracted_checked_and_recorded(self):
        meta = self.configure(tier="standard").read(self.pdf, self.out)
        self.assertTrue((self.out / "structured_content.json").is_file())
        self.assertTrue((self.out / "markdown.md").is_file())
        self.assertTrue((self.out / "images" / "a.png").is_file())
        self.assertFalse((self.out / "_mineru_kit").exists())
        rm = json.loads((self.out / "reader_meta.json").read_text())
        self.assertEqual(rm, meta)
        self.assertEqual((rm["reader"], rm["command"], rm["route"], rm["tier"]),
                         ("mineru_kit", "fake-mineru-kit", "local", "standard"))

    def test_argv_is_a_list_with_the_documented_options(self):
        self.configure(tier="advanced", extra_args=["--ocr-mode", "auto"]).read(self.pdf, self.out)
        argv = self.logged()["argv"]
        self.assertEqual(argv[0], "parse")
        self.assertEqual(argv[1], str(self.pdf))
        self.assertEqual(argv[2], "-o")
        self.assertEqual(argv[4:], ["--format", "zip", "--tier", "advanced", "--ocr-mode", "auto"])

    def test_tier_is_left_out_when_not_configured(self):
        self.configure().read(self.pdf, self.out)
        self.assertNotIn("--tier", self.logged()["argv"])

    def test_telemetry_is_disabled_unless_the_environment_sets_it(self):
        self.configure().read(self.pdf, self.out)
        self.assertEqual(self.logged()["telemetry"], "1")
        with mock.patch.dict(os.environ, {"MINERU_TELEMETRY_DISABLED": "0"}):
            self.configure().read(self.pdf, self.out)
        self.assertEqual(self.logged()["telemetry"], "0")

    def test_remote_flag_is_passed_and_the_route_is_recorded(self):
        meta = self.configure(extra_args=["--remote"]).read(self.pdf, self.out)
        self.assertIn("--remote", self.logged()["argv"])
        self.assertEqual(meta["route"], "remote")

    def test_api_key_in_the_config_is_refused_without_echoing_it(self):
        with self.assertRaises(config.ConfigError) as cm:
            self.configure(extra_args=["--api-key", "SECRET-VALUE"])
        self.assertIn("MINERU_API_KEY", str(cm.exception))
        self.assertNotIn("SECRET-VALUE", str(cm.exception))

    def test_unknown_tier_is_rejected_at_startup(self):
        with self.assertRaises(config.ConfigError):
            self.configure(tier="ultra")

    def test_missing_structured_content_fails_the_reader_with_its_role(self):
        os.environ["FAKE_MODE"] = "no_structured"
        with self.assertRaisesRegex(RuntimeError, r"primary_reader.*structured_content.json"):
            self.configure().read(self.pdf, self.out)

    def test_missing_markdown_fails_the_reader(self):
        os.environ["FAKE_MODE"] = "no_markdown"
        with self.assertRaisesRegex(RuntimeError, "no markdown file"):
            self.configure().read(self.pdf, self.out)

    def test_nonzero_exit_fails_the_reader(self):
        os.environ["FAKE_MODE"] = "exit"
        with self.assertRaisesRegex(RuntimeError, "exited with 2"):
            self.configure().read(self.pdf, self.out)

    def test_archive_member_outside_the_output_directory_is_refused(self):
        os.environ["FAKE_MODE"] = "unsafe"
        with self.assertRaisesRegex(RuntimeError, "outside the output directory"):
            self.configure().read(self.pdf, self.out)
        self.assertFalse((Path(self.tmp.name) / "escaped.txt").exists())

    def test_missing_program_fails_the_reader_by_name(self):
        with self.assertRaisesRegex(RuntimeError, "cannot run"):
            self.configure(command="/nonexistent/dir/mineru-kit").read(self.pdf, self.out)

    def test_description_names_the_command_and_no_path(self):
        self.configure(tier="standard")
        d = backends.describe("primary_reader")
        self.assertEqual(d["command"], "fake-mineru-kit")
        self.assertNotIn(self.tmp.name, json.dumps(d))


if __name__ == "__main__":
    unittest.main()
