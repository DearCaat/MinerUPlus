"""Second reader through an OpenAI-compatible vision model. Each page is rendered to PNG with pymupdf, so the model
sees the page image only and never the text layer. The model transcribes the page as printed.

Options: base_url, model, api_key_env (optional), dpi (default 200), jobs (default 4: pages sent at once),
timeout_s (default 300), max_tokens (default 4096).

Output (see mineru_plus/backends/__init__.py): pages.json with one "Text" block per paragraph of the answer
(paragraphs are separated by blank lines), reader_meta.json, and raw/page_NNNN.txt holding each answer as received.
"""
import json, re, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pymupdf
from .openai_chat import chat_completion, png_data_url

PROMPT = ("Transcribe the text of this page exactly as it is printed, in reading order. Output plain text: paragraphs "
          "separated by one blank line, with no markdown and no commentary. Copy every character as printed, including "
          "typing errors; do not correct them.")


def paragraphs(text):
    t = text.strip()
    t = re.sub(r"^```[a-zA-Z]*\s*\n|\n```\s*$", "", t)          # a code fence around the whole answer
    return [p.strip() for p in re.split(r"\n\s*\n", t) if p.strip()]


class SecondReader:
    def __init__(self, spec):
        self.base_url = spec.require("base_url")
        self.model = spec.require("model")
        self.key = spec.secret("api_key_env")
        self.dpi = int(spec.get("dpi", 200))
        self.jobs = int(spec.get("jobs", 4))
        self.timeout = spec.get("timeout_s", 300)
        self.max_tokens = int(spec.get("max_tokens", 4096))

    def info(self):
        return {"model": self.model}

    def read(self, pdf, out_dir):
        out_dir = Path(out_dir)
        (out_dir / "raw").mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        doc = pymupdf.open(str(pdf))
        n = doc.page_count
        answers = {}
        try:
            for start in range(0, n, self.jobs):          # render a few pages, transcribe them at once
                idx = list(range(start, min(n, start + self.jobs)))
                pngs = {i: doc[i].get_pixmap(dpi=self.dpi).tobytes("png") for i in idx}
                with ThreadPoolExecutor(max_workers=self.jobs) as ex:
                    for i, text in zip(idx, ex.map(lambda i: self._transcribe(pngs[i]), idx)):
                        answers[i] = text
                        (out_dir / "raw" / f"page_{i + 1:04d}.txt").write_text(text, encoding="utf-8")
        finally:
            doc.close()
        pages = [{"page": i + 1, "blocks": [{"type": "Text", "content": p} for p in paragraphs(answers[i])]}
                 for i in range(n)]
        (out_dir / "pages.json").write_text(json.dumps({"pages": pages}, ensure_ascii=False, indent=1), encoding="utf-8")
        meta = {"reader": "openai_vlm", "model": self.model, "dpi": self.dpi, "pages": n,
                "route": "openai-compatible chat completions", "latency_s": round(time.time() - t0, 1)}
        (out_dir / "reader_meta.json").write_text(json.dumps(meta, indent=1))
        return meta

    def _transcribe(self, png):
        body = {"model": self.model, "temperature": 0, "max_tokens": self.max_tokens,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": png_data_url(png)}}]}]}
        resp = chat_completion(self.base_url, self.key, body, self.timeout)
        return (resp["choices"][0].get("message") or {}).get("content") or ""
