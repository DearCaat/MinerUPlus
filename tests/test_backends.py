"""Tests of the backends that talk to OpenAI-compatible endpoints, the command backends, and the config lookup.

The endpoints are a mock HTTP server on localhost; no real service is called.
Run from the repository root: python3 -m unittest discover -s tests -v
"""
import base64, io, json, os, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymupdf  # noqa: E402
from PIL import Image  # noqa: E402
from mineru_plus import backends, config  # noqa: E402
from mineru_plus.backends import openai_chat  # noqa: E402
from mineru_plus.check import jev  # noqa: E402
from mineru_plus.readers import mineru as MR, oxr  # noqa: E402

KEY = "mock-key-not-a-real-credential"
os.environ["MP_TEST_API_KEY"] = KEY

MOCK = {"requests": [], "reply": None, "fail_first": 0}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or b"{}")
        MOCK["requests"].append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        if MOCK["fail_first"] > 0:
            MOCK["fail_first"] -= 1
            return self._send(500, {"error": "temporary"})
        status, reply = MOCK["reply"](body)
        self._send(status, reply)

    def _send(self, status, obj):
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def choice(text, top=None):
    """A chat completion whose answer is text. top: [(token, logprob)] for its first token, or None for no logprobs."""
    ch = {"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}
    if top is not None:
        ch["logprobs"] = {"content": [{"token": text, "logprob": top[0][1],
                                       "top_logprobs": [{"token": t, "logprob": lp} for t, lp in top]}]}
    return {"id": "mock", "object": "chat.completion", "choices": [ch],
            "usage": {"prompt_tokens": 7, "completion_tokens": 1, "total_tokens": 8}}


def user_text(body):
    return "\n".join(p["text"] for p in body["messages"][0]["content"] if p["type"] == "text")


def marked_option(body):
    """Answers the letter of the option whose text contains MARK (for the ask() test)."""
    options = {}
    for line in user_text(body).splitlines():
        if len(line) > 2 and line[0] in "ABC" and line[1] == ":":
            options[line[0]] = line[3:]
    letter = next(k for k, v in options.items() if "MARK" in v)
    other = "B" if letter == "A" else "A"
    return 200, choice(letter, top=[(letter, -0.02), (other, -4.0)])


def start_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/v1"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.base = start_server()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        MOCK["requests"].clear()
        MOCK["fail_first"] = 0
        MOCK["reply"] = lambda body: (200, choice("A", top=[("A", -0.05), ("B", -3.0)]))
        openai_chat.WAIT_S = 0
        config.reset(); backends.reset()
        self.addCleanup(config.reset)
        self.addCleanup(backends.reset)

    def configure(self, doc):
        p = Path(self.tmp.name) / "mineru_plus.json"
        p.write_text(json.dumps(doc))
        config.reset(); backends.reset()
        config.load(p)
        return p

    def openai(self, backend="openai", **extra):
        return {"backend": backend, "base_url": self.base, "model": "mock-model", "api_key_env": "MP_TEST_API_KEY",
                **extra}


class DecisionJudgeTest(Base):
    def setUp(self):
        super().setUp()
        self.configure({"decision_judge": self.openai()})
        self.judge = backends.get("decision_judge")
        self.fin = Path(self.tmp.name) / "in.jsonl"
        self.fout = Path(self.tmp.name) / "out.jsonl"
        self.img = "data:image/png;base64," + base64.b64encode(b"\x89PNG-test").decode()

    def request(self, rid, with_image=True):
        q = {"id": rid, "model": "mock-model", "state": "A strip of a paper.",
             "questions": {"which": {"type": "choice", "instructions": "Which option is printed?",
                                     "criteria": {"first": "the first text", "second": "the second text"}}}}
        if with_image:
            q["images"] = [self.img]
        return q

    def write_fin(self, rows):
        self.fin.write_text("".join(json.dumps(r) + "\n" for r in rows))

    def answers(self):
        return [json.loads(l) for l in self.fout.read_text().splitlines() if l.strip()]

    def test_logprobs_give_option_probabilities(self):
        self.write_fin([self.request("q1|first")])
        self.judge.run(self.fin, self.fout)
        (rec,) = self.answers()
        self.assertTrue(rec["ok"])
        probs = rec["answers"]["which"]["probabilities"]
        self.assertAlmostEqual(probs["first"], 0.95, places=2)
        self.assertAlmostEqual(probs["second"], 0.05, places=2)
        req = MOCK["requests"][-1]
        self.assertEqual(req["auth"], "Bearer " + KEY)
        self.assertEqual(req["body"]["model"], "mock-model")
        self.assertTrue(req["body"]["logprobs"])
        self.assertEqual(req["body"]["top_logprobs"], 5)
        content = req["body"]["messages"][0]["content"]
        self.assertEqual(content[1], {"type": "image_url", "image_url": {"url": self.img}})
        text = content[0]["text"]
        self.assertIn("A: the first text", text)
        self.assertIn("B: the second text", text)

    def test_no_logprobs_gives_probability_one_to_the_answer(self):
        MOCK["reply"] = lambda body: (200, choice("B"))
        self.write_fin([self.request("q2|second", with_image=False)])
        self.judge.run(self.fin, self.fout)
        (rec,) = self.answers()
        self.assertEqual(rec["answers"]["which"]["probabilities"], {"first": 0.0, "second": 1.0})

    def test_neither_option_is_letter_c(self):
        MOCK["reply"] = lambda body: (200, choice("C"))
        q = self.request("q3|first", with_image=False)
        q["questions"]["which"]["criteria"]["neither"] = "neither text"
        self.write_fin([q])
        self.judge.run(self.fin, self.fout)
        (rec,) = self.answers()
        self.assertEqual(rec["answers"]["which"]["probabilities"]["neither"], 1.0)
        self.assertIn("C: neither text", MOCK["requests"][-1]["body"]["messages"][0]["content"][0]["text"])

    def test_unreadable_answer_fails_that_request_only(self):
        MOCK["reply"] = lambda body: (200, choice("Maybe"))
        self.write_fin([self.request("q4|first", with_image=False)])
        self.judge.run(self.fin, self.fout)
        (rec,) = self.answers()
        self.assertFalse(rec["ok"])
        self.assertIn("not one of", rec["error"])

    def test_resume_asks_only_requests_without_an_ok_answer(self):
        self.write_fin([self.request("done|first", with_image=False), self.request("new|first", with_image=False)])
        self.fout.write_text(json.dumps({"id": "done|first", "ok": True, "answers": {"which": {
            "probabilities": {"first": 1.0, "second": 0.0}}}}) + "\n")
        before = len(MOCK["requests"])
        self.judge.run(self.fin, self.fout)
        self.assertEqual(len(MOCK["requests"]) - before, 1)
        self.assertEqual([r["id"] for r in self.answers()], ["done|first", "new|first"])

    def test_transient_server_error_is_retried(self):
        MOCK["fail_first"] = 2
        self.write_fin([self.request("q5|first", with_image=False)])
        self.judge.run(self.fin, self.fout)
        (rec,) = self.answers()
        self.assertTrue(rec["ok"])
        self.assertEqual(len(MOCK["requests"]), 3)

    def test_client_error_is_not_retried_and_the_key_is_not_written(self):
        MOCK["reply"] = lambda body: (401, {"error": {"message": "invalid api key"}})
        self.write_fin([self.request("q6|first", with_image=False)])
        self.judge.run(self.fin, self.fout)
        (rec,) = self.answers()
        self.assertFalse(rec["ok"])
        self.assertIn("HTTP 401", rec["error"])
        self.assertEqual(len(MOCK["requests"]), 1)
        self.assertNotIn(KEY, self.fout.read_text())

    def test_missing_key_variable_fails_at_startup_and_names_only_the_variable(self):
        os.environ.pop("MP_TEST_UNSET_KEY", None)
        self.configure({"decision_judge": self.openai(api_key_env="MP_TEST_UNSET_KEY")})
        with self.assertRaises(config.ConfigError) as cm:
            backends.get("decision_judge")
        self.assertIn("MP_TEST_UNSET_KEY", str(cm.exception))
        self.assertIn("decision_judge", str(cm.exception))


class JevAskTest(Base):
    """check/jev.ask() with the openai decision judge from a config file: both option orders, the decided answer,
    and the cache by question hash."""

    def test_ask_decides_in_both_orders_and_caches(self):
        self.configure({"decision_judge": self.openai()})
        MOCK["reply"] = marked_option
        qs = [{"id": "c1", "state": "A quoted passage.", "instructions": "Which one is printed?",
               "options": {"yes": "MARK the printed form", "no": "the other form"}}]
        work = Path(self.tmp.name) / "work"
        self.assertEqual(jev.ask(qs, work, "unit"), {"c1": "yes"})
        asked = len(MOCK["requests"])
        self.assertEqual(asked, 2)
        self.assertEqual(jev.ask(qs, work, "unit"), {"c1": "yes"})
        self.assertEqual(len(MOCK["requests"]), asked)


class PageJudgeTest(Base):
    def setUp(self):
        super().setUp()
        self.configure({"page_judge": self.openai()})
        self.judge = backends.get("page_judge")
        self.cwd = Path(self.tmp.name)
        self.sheets = []
        for i in range(2):
            p = self.cwd / f"sheet{i}.png"
            Image.new("RGB", (30, 20), (255, i * 100, 0)).save(p)
            self.sheets.append(str(p))

    def test_sheets_are_attached_and_the_json_is_returned(self):
        MOCK["reply"] = lambda body: (200, {**choice('```json\n{"1": "A", "2": "neither"}\n```'),
                                             "usage": {"prompt_tokens": 9}})
        obj, usage, err = self.judge.session("Items:\n#1 ...", self.sheets, self.cwd)
        self.assertEqual(obj, {"1": "A", "2": "neither"})
        self.assertIsNone(err)
        self.assertEqual(usage, {"prompt_tokens": 9})
        content = MOCK["requests"][-1]["body"]["messages"][0]["content"]
        self.assertIn("Items:\n#1 ...", content[0]["text"])
        urls = [p["image_url"]["url"] for p in content[1:]]
        self.assertEqual(len(urls), 2)
        for url, path in zip(urls, self.sheets):
            self.assertTrue(url.startswith("data:image/png;base64,"))
            self.assertEqual(base64.b64decode(url.split(",", 1)[1]), Path(path).read_bytes())

    def test_answer_without_json_is_reported(self):
        MOCK["reply"] = lambda body: (200, choice("I cannot tell."))
        obj, usage, err = self.judge.session("body", self.sheets, self.cwd)
        self.assertIsNone(obj)
        self.assertIn("no JSON in the answer", err)

    def test_server_failure_is_reported_not_raised(self):
        MOCK["reply"] = lambda body: (400, {"error": "bad request"})
        obj, usage, err = self.judge.session("body", self.sheets, self.cwd)
        self.assertIsNone(obj)
        self.assertIn("HTTP 400", err)


class VlmSecondReaderTest(Base):
    def setUp(self):
        super().setUp()
        self.configure({"second_reader": self.openai("openai_vlm", dpi=100, jobs=2)})
        doc = pymupdf.open()
        for i in range(3):
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 100), f"Printed text of page {i + 1}")
        self.pdf = Path(self.tmp.name) / "paper.pdf"
        doc.save(str(self.pdf))
        doc.close()

    def test_pages_are_rendered_sent_and_written_as_text_blocks(self):
        MOCK["reply"] = lambda body: (200, choice("First paragraph,\nwrapped line.\n\nSecond paragraph.\n\n"))
        out = Path(self.tmp.name) / "oxr"
        meta = oxr.read(self.pdf, out)
        self.assertEqual(meta["reader"], "openai_vlm")
        self.assertEqual(len(MOCK["requests"]), 3)
        for req in MOCK["requests"]:
            content = req["body"]["messages"][0]["content"]
            self.assertIn("exactly as it is printed", content[0]["text"])
            url = content[1]["image_url"]["url"]
            png = base64.b64decode(url.split(",", 1)[1])
            self.assertEqual(Image.open(io.BytesIO(png)).size, (850, 1100))     # 612 x 792 pt at 100 dpi
        pages = json.loads((out / "pages.json").read_text())["pages"]
        self.assertEqual([p["page"] for p in pages], [1, 2, 3])
        self.assertEqual(pages[0]["blocks"], [
            {"type": "Text", "content": "First paragraph,\nwrapped line."},
            {"type": "Text", "content": "Second paragraph."}])
        self.assertEqual(len(list((out / "raw").glob("page_*.txt"))), 3)
        self.assertEqual(sorted(oxr.pages(out)), [1, 2, 3])

    def test_code_fence_around_the_answer_is_removed(self):
        MOCK["reply"] = lambda body: (200, choice("```text\nOnly paragraph.\n```"))
        out = Path(self.tmp.name) / "oxr2"
        oxr.read(self.pdf, out)
        self.assertEqual(json.loads((out / "pages.json").read_text())["pages"][0]["blocks"],
                         [{"type": "Text", "content": "Only paragraph."}])


class CommandBackendTest(Base):
    WRITE_PRIMARY = (
        "import json,sys,pathlib;"
        "out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True);"
        "(out/'structured_content.json').write_text(json.dumps({'pages':[{'page_idx':0,'blocks':"
        "[{'type':'text','bbox':[0.1,0.1,0.9,0.2],'content':'Hello'}]}]}));"
        "(out/'full.md').write_text('Hello')")
    WRITE_SECOND = (
        "import json,sys,pathlib;out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True);"
        "(out/'pages.json').write_text(json.dumps({'pages':[{'page':1,'blocks':[{'type':'Text','content':'x'}]}]}))")

    def test_primary_command_output_is_read_in_the_documented_format(self):
        self.configure({"primary_reader": {"backend": "command",
                                           "command": [sys.executable, "-c", self.WRITE_PRIMARY, "{pdf}", "{out}"]}})
        pdf = Path(self.tmp.name) / "p.pdf"; pdf.write_bytes(b"%PDF-1.4 test")
        out = Path(self.tmp.name) / "mineru"
        meta = MR.read(pdf, out)
        self.assertEqual(meta["reader"], "command")
        self.assertEqual(MR.pages(out), {1: [(0, {"type": "text", "bbox": [0.1, 0.1, 0.9, 0.2], "content": "Hello"})]})
        self.assertEqual(MR.markdown(out), "Hello")
        self.assertEqual(MR.figure_bodies(out), [])          # no middle_json.json: no declared figure bodies

    def test_second_command_output_is_read(self):
        self.configure({"second_reader": {"backend": "command",
                                          "command": [sys.executable, "-c", self.WRITE_SECOND, "{pdf}", "{out}"]}})
        pdf = Path(self.tmp.name) / "p.pdf"; pdf.write_bytes(b"%PDF-1.4 test")
        out = Path(self.tmp.name) / "oxr"
        oxr.read(pdf, out)
        self.assertEqual(oxr.pages(out), {1: [{"type": "Text", "content": "x"}]})

    def test_missing_output_fails_the_reader_with_its_role(self):
        self.configure({"primary_reader": {"backend": "command", "command": [sys.executable, "-c", "pass", "{pdf}", "{out}"]}})
        pdf = Path(self.tmp.name) / "p.pdf"; pdf.write_bytes(b"%PDF-1.4 test")
        with self.assertRaises(RuntimeError) as cm:
            MR.read(pdf, Path(self.tmp.name) / "m")
        self.assertIn("primary_reader", str(cm.exception))
        self.assertIn("structured_content.json", str(cm.exception))

    def test_nonzero_exit_fails_the_reader(self):
        self.configure({"second_reader": {"backend": "command", "command": [sys.executable, "-c", "import sys; sys.exit(3)"]}})
        pdf = Path(self.tmp.name) / "p.pdf"; pdf.write_bytes(b"%PDF-1.4 test")
        with self.assertRaises(RuntimeError) as cm:
            oxr.read(pdf, Path(self.tmp.name) / "o")
        self.assertIn("exited with 3", str(cm.exception))


class ConfigTest(Base):
    def test_unconfigured_role_names_the_role_and_the_file(self):
        p = self.configure({"primary_reader": {"backend": "command", "command": ["x", "{pdf}", "{out}"]}})
        with self.assertRaises(config.ConfigError) as cm:
            backends.get("decision_judge")
        self.assertIn("decision_judge", str(cm.exception))
        self.assertIn(str(p), str(cm.exception))

    def test_unknown_backend_name_is_rejected(self):
        self.configure({"decision_judge": {"backend": "carrier-pigeon", "model": "m"}})
        with self.assertRaises(config.ConfigError) as cm:
            backends.get("decision_judge")
        self.assertIn("carrier-pigeon", str(cm.exception))

    def test_unknown_role_key_is_rejected(self):
        p = Path(self.tmp.name) / "bad.json"
        p.write_text(json.dumps({"primary_reader": {"backend": "command"}, "decision_judg": {"backend": "openai"}}))
        with self.assertRaises(config.ConfigError) as cm:
            config.load(p)
        self.assertIn("decision_judg", str(cm.exception))

    def test_environment_variable_selects_the_file(self):
        p = self.configure({"page_judge": {"backend": "agy", "command": "agy-min"}})
        old = os.environ.get(config.ENV)
        os.environ[config.ENV] = str(p)
        self.addCleanup(lambda: os.environ.pop(config.ENV) if old is None else os.environ.__setitem__(config.ENV, old))
        self.assertEqual(config.find(), p)
        self.assertEqual(config.find("/elsewhere.json"), Path("/elsewhere.json"))


if __name__ == "__main__":
    unittest.main()


class UserConfig(unittest.TestCase):
    def test_user_level_config_is_found(self):
        import os, tempfile
        from pathlib import Path
        from mineru_plus import config
        with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as cwd:
            user = Path(home) / "mineru_plus" / "config.json"
            user.parent.mkdir(parents=True)
            user.write_text("{}")
            old = (os.getcwd(), os.environ.pop(config.ENV, None), os.environ.get("XDG_CONFIG_HOME"))
            try:
                os.chdir(cwd); os.environ["XDG_CONFIG_HOME"] = home
                self.assertEqual(config.find(), user)
                (Path(cwd) / config.DEFAULT_NAME).write_text("{}")
                self.assertEqual(config.find(), Path(cwd) / config.DEFAULT_NAME)
            finally:
                os.chdir(old[0])
                if old[1] is not None: os.environ[config.ENV] = old[1]
                if old[2] is None: os.environ.pop("XDG_CONFIG_HOME", None)
                else: os.environ["XDG_CONFIG_HOME"] = old[2]
