"""Gateway backend: calls through a tool gateway by its helper scripts. tool-call.py serves the two readers and
jev-call.py serves the decision judge. The helpers resolve the route and the credential themselves; nothing here reads
a key.

Options:
  primary_reader   {"backend": "gateway", "tool_call": PATH, "tier": "advanced"}   tier is optional
  second_reader    {"backend": "gateway", "tool_call": PATH}
  decision_judge   {"backend": "gateway", "jev_call": PATH, "model": NAME, "jobs": 24}   jobs is optional
"""
import json, shutil, subprocess, sys, time, zipfile
from pathlib import Path

# The second reader's service parses one file at a time, and the gateway does not replay 502/504; several runs at once
# broke the upload (10-28: 3 of 15 files, 'Broken pipe'; all 3 passed when sent alone). Transient failures are retried
# after a wait.
TRANSIENT = ("network error", "Broken pipe", "502", "503", "504", "429", "timed out", "Connection reset")
ATTEMPTS, WAIT_S = 4, 90


def _tool(tool_call, tool, pdf, out_dir, *extra, row=None):
    """One file through tool-call.py. row: extra fields of the JSONL input line (e.g. output_formats), sent with --in;
    without row the file goes with --file. Returns the call record (ok, error, result_file, ...)."""
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    rec = out_dir / "call.jsonl"
    if row is not None:
        inp = out_dir / "call_in.jsonl"
        inp.write_text(json.dumps({"id": Path(pdf).stem, "file": str(Path(pdf).resolve()), **row}) + "\n")
        args = ["--in", str(inp)]
    else:
        args = ["--file", str(pdf)]
    p = subprocess.run([sys.executable, tool_call, tool, *args, "--out-dir", str(out_dir), "--out", str(rec), *extra],
                       capture_output=True, text=True)
    lines = [json.loads(l) for l in rec.read_text().splitlines() if l.strip()] if rec.exists() else []
    if not lines or not lines[-1].get("ok"):
        raise RuntimeError(f"{tool} failed on {pdf}: {(lines[-1].get('error') if lines else p.stderr[-500:])}")
    return lines[-1]


class PrimaryReader:
    def __init__(self, spec):
        self.tool_call = spec.require("tool_call")
        self.tier = spec.get("tier", "advanced")

    def info(self):
        return {"tool": "mineru", "tier": self.tier}

    def read(self, pdf, out_dir):
        out_dir = Path(out_dir)
        work = out_dir / "_call"
        rec = _tool(self.tool_call, "mineru", pdf, work, row={"tier": self.tier, "output_formats": ["markdown", "zip"]})
        zipfile.ZipFile(Path(rec["result_file"])).extractall(out_dir)
        meta = {"reader": "mineru", "tier": self.tier, "route": "tool gateway", "task_id": rec.get("task_id"),
                "latency_s": rec.get("latency_s")}
        (out_dir / "reader_meta.json").write_text(json.dumps(meta, indent=1))
        shutil.rmtree(work, ignore_errors=True)
        return meta


class SecondReader:
    def __init__(self, spec):
        self.tool_call = spec.require("tool_call")

    def info(self):
        return {"tool": "oxr"}

    def read(self, pdf, out_dir):
        out_dir = Path(out_dir)
        for k in range(ATTEMPTS):
            try:
                rec = _tool(self.tool_call, "oxr", pdf, out_dir)
                break
            except RuntimeError as e:
                if k == ATTEMPTS - 1 or not any(m in str(e) for m in TRANSIENT):
                    raise
                (out_dir / "call.jsonl").unlink(missing_ok=True)
                time.sleep(WAIT_S * (k + 1))
        meta = {"reader": "oxr", "route": "tool gateway (local deployment)", "pages": rec.get("pages"),
                "processing_time_ms": rec.get("processing_time_ms"), "latency_s": rec.get("latency_s")}
        (out_dir / "reader_meta.json").write_text(json.dumps(meta, indent=1))
        return meta


class DecisionJudge:
    def __init__(self, spec):
        self.jev_call = spec.require("jev_call")
        self.model = spec.require("model")
        self.jobs = int(spec.get("jobs", 24))

    def info(self):
        return {"model": self.model}

    def run(self, fin, fout):
        # two passes: the helper resumes from the out file, and the second pass retries the failures
        for _ in range(2):
            subprocess.run([sys.executable, self.jev_call, "--api", "jev", "--in", str(fin), "--out", str(fout),
                            "-j", str(self.jobs)], capture_output=True, text=True)
