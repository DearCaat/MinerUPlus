"""Page-judge backend through a CLI agent: one session per option order, which reads the sheet image files with its
file tool and answers with one JSON object.

Options: "command" (required: the name of the CLI, e.g. agy-min), "model" (optional: the model the CLI runs, as it
names it; the CLI chooses the model itself, so this is only reported), "timeout_s" (default 3600), "attempts" (default 3).
An empty answer with no tokens used is treated as the route failing (quota cooldown, too many sessions at once); it is
retried after a pause.
"""
import json, re, subprocess, time
from pathlib import Path


class PageJudge:
    def __init__(self, spec):
        self.command = spec.require("command")
        self.model = spec.get("model")
        self.timeout = spec.get("timeout_s", 3600)
        self.attempts = int(spec.get("attempts", 3))

    def info(self):
        return {"command": Path(self.command).name, **({"model": self.model} if self.model else {})}

    def session(self, body, sheets, cwd):
        prompt = ("The image files below contain strips cut from pages of a scientific paper. Read every image file "
                  "with your file reading tool (read them all; do not run any other command and do not write any "
                  "file).\n\nImage files:\n" + "\n".join(str(s) for s in sheets) + "\n\n" + body)
        err = None
        for k in range(self.attempts):
            try:
                p = subprocess.run([self.command, "--dangerously-skip-permissions", "--output-format", "json", "-p",
                                    prompt], capture_output=True, text=True, timeout=self.timeout, cwd=str(cwd))
                env = json.loads(p.stdout)
            except Exception as e:
                env, err = {}, repr(e)[:300]
            resp = env.get("response") or ""
            used = (env.get("usage") or {}).get("input_tokens", 0)
            if resp or used:
                (Path(cwd) / f"response_{abs(hash(prompt)) % 10**8}.txt").write_text(resp)
                m = re.search(r"\{.*\}", resp, re.S)
                if not m:
                    return None, env.get("usage"), "no JSON in the answer: " + resp[:200]
                return json.loads(m.group(0)), env.get("usage"), None
            err = err or ("empty answer, no tokens used (status %s): %s" % (env.get("status"), (p.stderr or "")[-200:]))
            time.sleep(60 * (k + 1))
        return None, None, err
