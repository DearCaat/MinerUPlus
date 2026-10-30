"""OpenAI-compatible chat-completions backend (urllib from the standard library, no SDK), for the two judge roles.

decision_judge options: base_url (e.g. "https://api.openai.com/v1"), model, api_key_env (optional: the name of the
environment variable that holds the key; absent for a server without auth), logprobs (default true), top_logprobs
(default 5), max_tokens (default 8), temperature (default 0), jobs (default 4), timeout_s (default 120).

page_judge options: base_url, model, api_key_env (optional), max_tokens (default 4096), temperature (default 0),
timeout_s (default 600).

The backend name in the config is "openai". Both roles use the same HTTP helper, chat_completion(), which the openai_vlm
backend also uses.
"""
import base64, json, math, re, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RETRY_CODES = (429, 500, 502, 503, 504)
ATTEMPTS, WAIT_S = 3, 5
PAGE_PREAMBLE = ("The attached images are sheets of strips cut from pages of a scientific paper, numbered as the items "
                 "below. Read every sheet before answering.")


def png_data_url(data):
    return "data:image/png;base64," + base64.b64encode(data).decode("ascii")


def chat_completion(base_url, key, body, timeout):
    """POST one chat-completions request and return the decoded response. Retries transient failures; raises
    RuntimeError with the server's message (never the key) when it gives up."""
    url = base_url.rstrip("/") + "/chat/completions"
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    last = None
    for k in range(ATTEMPTS):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode("utf-8"))
            if not isinstance(resp, dict) or not resp.get("choices"):
                raise RuntimeError("no choices in the response: " + str(resp)[:200])
            return resp
        except urllib.error.HTTPError as e:
            try:
                detail = e.read()[:300].decode("utf-8", "replace")
            except Exception:
                detail = ""
            last = f"HTTP {e.code}: {detail}"
            if e.code not in RETRY_CODES:
                break
        except RuntimeError as e:
            last = str(e)
            break
        except (urllib.error.URLError, OSError, ValueError) as e:
            last = repr(e)[:300]
        if k < ATTEMPTS - 1:
            time.sleep(WAIT_S * (k + 1))
    raise RuntimeError("chat completion failed: " + last)


def _auth(spec):
    return spec.secret("api_key_env")


class DecisionJudge:
    """Answers the requests of check/jev.py: one letter per request, read from the reply, with the option
    probabilities from the top logprobs of the first token when the server returns them."""

    def __init__(self, spec):
        self.base_url = spec.require("base_url")
        self.model = spec.require("model")
        self.key = _auth(spec)
        self.logprobs = bool(spec.get("logprobs", True))
        self.top_logprobs = int(spec.get("top_logprobs", 5))
        self.max_tokens = int(spec.get("max_tokens", 8))
        self.temperature = spec.get("temperature", 0)
        self.jobs = int(spec.get("jobs", 4))
        self.timeout = spec.get("timeout_s", 120)

    def info(self):
        return {"model": self.model}

    def run(self, fin, fout):
        fout = Path(fout)
        done = set()
        if fout.exists():
            for line in fout.read_text().splitlines():
                if line.strip():
                    rec = json.loads(line)
                    if rec.get("ok"):
                        done.add(rec["id"])
        todo = [json.loads(l) for l in Path(fin).read_text().splitlines() if l.strip()]
        todo = [r for r in todo if r.get("id") not in done]
        if not todo:
            return
        with ThreadPoolExecutor(max_workers=self.jobs) as ex:
            results = list(ex.map(self._one, todo))
        with open(fout, "a") as f:
            for rec in results:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _one(self, req):
        rid = req.get("id")
        try:
            which = req["questions"]["which"]
            crit = which["criteria"]
            keys = [("first", "A"), ("second", "B")] + ([("neither", "C")] if crit.get("neither") else [])
            letters = [letter for _, letter in keys]
            options = "\n".join(f"{letter}: {crit[k]}" for k, letter in keys)
            text = (f"{req.get('state', '')}\n\n{which['instructions']}\n\n{options}\n\n"
                    f"Answer with exactly one letter ({', '.join(letters)}) and nothing else.")
            content = [{"type": "text", "text": text}]
            content += [{"type": "image_url", "image_url": {"url": u}} for u in req.get("images", [])]
            body = {"model": self.model, "temperature": self.temperature, "max_tokens": self.max_tokens,
                    "messages": [{"role": "user", "content": content}]}
            if self.logprobs:
                body["logprobs"] = True
                body["top_logprobs"] = self.top_logprobs
            resp = chat_completion(self.base_url, self.key, body, self.timeout)
            probs = self._probabilities(resp["choices"][0], keys)
            return {"id": rid, "ok": True, "answers": {"which": {"probabilities": probs}}}
        except Exception as e:
            return {"id": rid, "ok": False, "error": str(e)[:300]}

    @staticmethod
    def _probabilities(choice, keys):
        letter_of = {letter: key for key, letter in keys}
        text = ((choice.get("message") or {}).get("content") or "").strip()
        m = re.match(r"[\s*(\[]*([A-Z])\b", text.upper())
        if not m or m.group(1) not in letter_of:
            raise RuntimeError(f"the answer is not one of {sorted(letter_of)}: {text[:80]!r}")
        chosen = letter_of[m.group(1)]
        content = (choice.get("logprobs") or {}).get("content") or []
        mass = {}
        if content and content[0].get("top_logprobs"):
            for alt in content[0]["top_logprobs"]:
                tok = str(alt.get("token", "")).strip().upper()
                if tok in letter_of:
                    k = letter_of[tok]
                    mass[k] = mass.get(k, 0.0) + math.exp(float(alt.get("logprob", -1e9)))
        total = sum(mass.values())
        if total > 0:
            return {k: mass.get(k, 0.0) / total for k, _ in keys}
        return {k: (1.0 if k == chosen else 0.0) for k, _ in keys}


class PageJudge:
    """Sends the page-judge prompt with the sheet images attached; returns the JSON object of the answer, as the
    agy backend does."""

    def __init__(self, spec):
        self.base_url = spec.require("base_url")
        self.model = spec.require("model")
        self.key = _auth(spec)
        self.max_tokens = int(spec.get("max_tokens", 4096))
        self.temperature = spec.get("temperature", 0)
        self.timeout = spec.get("timeout_s", 600)

    def info(self):
        return {"model": self.model}

    def session(self, body, sheets, cwd):
        content = [{"type": "text", "text": PAGE_PREAMBLE + "\n\n" + body}]
        for p in sheets:
            content.append({"type": "image_url", "image_url": {"url": png_data_url(Path(p).read_bytes())}})
        req = {"model": self.model, "temperature": self.temperature, "max_tokens": self.max_tokens,
               "messages": [{"role": "user", "content": content}]}
        try:
            resp = chat_completion(self.base_url, self.key, req, self.timeout)
        except RuntimeError as e:
            return None, None, str(e)[:300]
        usage = resp.get("usage")
        text = (resp["choices"][0].get("message") or {}).get("content") or ""
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None, usage, "no JSON in the answer: " + text[:200]
        try:
            return json.loads(m.group(0)), usage, None
        except ValueError as e:
            return None, usage, f"JSON in the answer does not parse: {e}"
