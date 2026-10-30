"""Primary reader through the mineru-kit command of the mineru package (MinerU 4.x), run as a local process.

The command is run as

    mineru-kit parse PDF -o WORK --format zip [--tier TIER] [extra_args...]

and writes WORK/<pdf stem>.zip with the files of ParseResult.save: markdown.md, middle_json.json, structured_content.json
and images/. The archive is extracted into the output directory, and structured_content.json and a markdown file must be
there afterwards.

Options (role primary_reader):
  command      the program name or path (default "mineru-kit"); run without a shell
  tier         flash, basic, standard or advanced; left out, the command uses standard
  extra_args   more arguments, a list of strings, e.g. ["--ocr-mode", "auto"]
  timeout_s    seconds (optional)

Not accepted in extra_args: --api-key. A credential is read from the environment variable MINERU_API_KEY.
--remote and --remote-url send the PDF to a remote service; reader_meta.json then records the route as remote.
The command runs with MINERU_TELEMETRY_DISABLED=1 unless the environment already sets it.
"""
import json, os, shutil, subprocess, time, zipfile
from pathlib import Path

TIERS = ("flash", "basic", "standard", "advanced")
REMOTE = ("--remote", "--remote-url")


class PrimaryReader:
    def __init__(self, spec):
        self.command = spec.get("command", "mineru-kit")
        if not isinstance(self.command, str) or not self.command:
            raise spec.fail("'command' must be the name or the path of the mineru-kit program")
        self.tier = spec.get("tier")
        if self.tier is not None and self.tier not in TIERS:
            raise spec.fail("'tier' must be one of " + ", ".join(TIERS))
        extra = spec.get("extra_args", [])
        if not isinstance(extra, list) or not all(isinstance(a, str) for a in extra):
            raise spec.fail("'extra_args' must be a list of strings")
        for a in extra:
            if a == "--api-key" or a.startswith("--api-key="):
                raise spec.fail("'--api-key' is not accepted in the config file; put the key in the environment "
                                "variable MINERU_API_KEY")
        self.extra = extra
        self.remote = any(a in REMOTE or a.startswith("--remote-url=") for a in extra)
        self.timeout = spec.get("timeout_s")

    def info(self):
        return {"command": Path(self.command).name, "tier": self.tier or "standard (command default)",
                "route": "remote" if self.remote else "local"}

    def read(self, pdf, out_dir):
        pdf, out_dir = Path(pdf), Path(out_dir)
        name = Path(self.command).name
        work = out_dir / "_mineru_kit"
        work.mkdir(parents=True, exist_ok=True)      # it exists before the call, so -o is read as a directory
        argv = [self.command, "parse", str(pdf), "-o", str(work), "--format", "zip"]
        if self.tier:
            argv += ["--tier", self.tier]
        argv += self.extra
        env = dict(os.environ)
        env.setdefault("MINERU_TELEMETRY_DISABLED", "1")
        t0 = time.time()
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=self.timeout, env=env)
        except OSError as e:
            raise RuntimeError(f"primary_reader: cannot run {name!r}: {e}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"primary_reader: {name!r} did not finish within {self.timeout} s")
        if p.returncode != 0:
            raise RuntimeError(f"primary_reader: {name!r} exited with {p.returncode}: {p.stderr[-500:]}")
        archive = work / f"{pdf.stem}.zip"
        if not archive.is_file():
            raise RuntimeError(f"primary_reader: {name!r} did not write {archive.name} (stdout: {p.stdout[-300:]})")
        _extract(archive, out_dir)
        shutil.rmtree(work, ignore_errors=True)
        _check(out_dir)
        meta = {"reader": "mineru_kit", **self.info(), "latency_s": round(time.time() - t0, 1)}
        (out_dir / "reader_meta.json").write_text(json.dumps(meta, indent=1))
        return meta


def _extract(archive, out_dir):
    root = out_dir.resolve()
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            target = (root / info.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"primary_reader: the archive has a member outside the output directory: "
                                   f"{info.filename!r}")
        z.extractall(root)


def _check(out_dir):
    path = out_dir / "structured_content.json"
    if not path.is_file():
        raise RuntimeError("primary_reader: the archive has no structured_content.json")
    try:
        s = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise RuntimeError(f"primary_reader: structured_content.json is not valid JSON: {e}")
    if not isinstance(s.get("pages"), list) or not all(isinstance(p, dict) and isinstance(p.get("blocks"), list)
                                                      and "page_idx" in p for p in s["pages"]):
        raise RuntimeError("primary_reader: structured_content.json has no pages with page_idx and blocks")
    if not list(out_dir.glob("*.md")):
        raise RuntimeError("primary_reader: the archive has no markdown file")
