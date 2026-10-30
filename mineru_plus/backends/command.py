"""Command backend: any program that leaves the documented files in the output directory.

The command is a list of arguments, run without a shell. Every argument has "{pdf}" and "{out}" replaced by the absolute
path of the PDF and of the output directory. The command must write the files of its role into {out}:

primary_reader   structured_content.json, a markdown file (full.md), and optionally middle_json.json and images/.
                 The format is the primary reader contract in mineru_plus/backends/__init__.py.
second_reader    pages.json: {"pages": [{"page": 1, "blocks": [{"type": "Text", "content": "..."}]}]}
                 (page one-based; the types Text, Title, Caption, Footnote, Formula, Table are the ones the checks read)

Options: "command" (required, a list of strings), "timeout_s" (optional, seconds).
A command that exits non-zero, or does not leave its files, fails the reader; the run reports it.
"""
import json, subprocess, time
from pathlib import Path


def _argv(spec):
    cmd = spec.require("command")
    if not isinstance(cmd, list) or not cmd or not all(isinstance(a, str) for a in cmd):
        raise spec.fail("'command' must be a non-empty list of strings, e.g. [\"tool\", \"{pdf}\", \"{out}\"]")
    return cmd


def _run(spec, pdf, out_dir):
    template = _argv(spec)
    Path(out_dir).mkdir(parents=True, exist_ok=True)      # the command writes into it
    argv = [a.replace("{pdf}", str(pdf)).replace("{out}", str(out_dir)) for a in template]
    t0 = time.time()
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=spec.get("timeout_s"))
    except OSError as e:
        raise RuntimeError(f"{spec.role}: cannot run {argv[0]!r}: {e}")
    if p.returncode != 0:
        raise RuntimeError(f"{spec.role}: {argv[0]!r} exited with {p.returncode}: {p.stderr[-500:]}")
    return {"command": template, "returncode": 0, "latency_s": round(time.time() - t0, 1)}


def _json(spec, path, what):
    if not path.exists():
        raise RuntimeError(f"{spec.role}: the command did not write {what} into {path.parent} "
                           "(format: mineru_plus/backends/command.py)")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise RuntimeError(f"{spec.role}: {what} is not valid JSON: {e}")


class PrimaryReader:
    def __init__(self, spec):
        self.spec = spec
        _argv(spec)

    def info(self):
        return {"command": Path(self.spec["command"][0]).name}

    def read(self, pdf, out_dir):
        out_dir = Path(out_dir)
        meta = _run(self.spec, Path(pdf).resolve(), out_dir.resolve())
        s = _json(self.spec, out_dir / "structured_content.json", "structured_content.json")
        if not isinstance(s.get("pages"), list) or not all(isinstance(p, dict) and isinstance(p.get("blocks"), list)
                                                          and "page_idx" in p for p in s["pages"]):
            raise RuntimeError(f"{self.spec.role}: structured_content.json has no pages with page_idx and blocks")
        if not list(out_dir.glob("*.md")):
            raise RuntimeError(f"{self.spec.role}: the command did not write a markdown file (full.md) into {out_dir}")
        meta = {"reader": "command", **meta}
        (out_dir / "reader_meta.json").write_text(json.dumps(meta, indent=1))
        return meta


class SecondReader:
    def __init__(self, spec):
        self.spec = spec
        _argv(spec)

    def info(self):
        return {"command": Path(self.spec["command"][0]).name}

    def read(self, pdf, out_dir):
        out_dir = Path(out_dir)
        meta = _run(self.spec, Path(pdf).resolve(), out_dir.resolve())
        p = _json(self.spec, out_dir / "pages.json", "pages.json")
        if not isinstance(p.get("pages"), list) or not all(isinstance(x, dict) and isinstance(x.get("blocks"), list)
                                                          and "page" in x for x in p["pages"]):
            raise RuntimeError(f"{self.spec.role}: pages.json has no pages with page and blocks")
        meta = {"reader": "command", **meta}
        (out_dir / "reader_meta.json").write_text(json.dumps(meta, indent=1))
        return meta
