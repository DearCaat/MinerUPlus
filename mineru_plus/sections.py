"""sections.json and quote_index.json of a parse, in the pdf_parser schema, so a downstream consumer reads mineru_plus
output as it reads its own (10-29, consumer note: 'no sections and quote index, a conversion layer would be needed').

Sections are the headings of full.md. A heading's page is the page of the reader's title block with the same text,
taken in order; a section ends where the next one with a page starts. The level is the depth of the heading's
number where it has one ('2.1 Patients' is under '2 Patients', though the reader gives both the same level),
else its markdown level."""
import hashlib, json, re
from pathlib import Path
from .readers import mineru as MR

HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
NUMBER = re.compile(r"^((?:\d+|[A-Z])(?:\.\d+)*)\.?\s+\S")
WS = re.compile(r"\s+")
FRONT = "Front Matter"
TITLE = ("doc_title", "paragraph_title", "title")


def _key(t):
    return re.sub(r"[^a-z0-9]+", "", t.lower())


def _level(hashes, title):
    m = NUMBER.match(title)
    return 1 + m.group(1).count(".") + 1 if m and m.group(1)[0].isdigit() else len(hashes)


def _norm(t):
    return WS.sub(" ", t.replace(" ", " ").replace(" ", " ").replace(" ", " ")).strip()


def sections(md, mdir):
    titles = [(pg, b.get("content") or "") for pg, bl in sorted(MR.pages(mdir).items()) for _, b in bl
              if b["type"] in TITLE]
    page_count = len(MR.pages(mdir))
    used = [False] * len(titles)

    def page_of(title):
        k = _key(title)
        for i, (pg, t) in enumerate(titles):
            if not used[i] and k and _key(t) == k:
                used[i] = True
                return pg
        return None

    out, cur = [], {"index": 0, "title": FRONT, "level": 0, "page_start": 1, "lines": []}
    for line in md.splitlines():
        m = HEADING.match(line)
        if not m:
            cur["lines"].append(line)
            continue
        out.append(cur)
        title = m.group(2).rstrip("# ").strip()
        cur = {"index": len(out), "title": title, "level": _level(m.group(1), title), "page_start": page_of(title),
               "lines": []}
    out.append(cur)
    for s in out:
        s["text"] = re.sub(r"\n{3,}", "\n\n", "\n".join(s.pop("lines")).strip())
    for i, s in enumerate(out):
        if s["page_start"] is None:
            s["page_end"] = None
            continue
        nxt = next((t["page_start"] for t in out[i + 1:] if t["page_start"] is not None), None)
        s["page_end"] = max(s["page_start"], nxt - 1) if nxt else page_count
    if not out[0]["text"]:
        out = out[1:]
    return out, page_count


def write(pdf, md, mdir, out):
    """writes out/sections.json and out/quote_index.json; returns the number of sections"""
    out = Path(out)
    h = hashlib.sha256(Path(pdf).read_bytes()).hexdigest()
    secs, n_pages = sections(md, mdir)
    (out / "sections.json").write_text(json.dumps(
        {"paper_hash": h, "full_md_path": str(out / "full.md"), "page_count": n_pages, "section_count": len(secs),
         "sections": secs}, ensure_ascii=False, indent=2))
    rec = [{"index": s["index"], "title": s["title"],
            "aliases": list(dict.fromkeys([s["title"], re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", s["title"]).strip()])),
            "level": s["level"], "page_start": s["page_start"], "page_end": s["page_end"], "text": s["text"],
            "normalized_text": _norm(s["text"])} for s in secs]
    (out / "quote_index.json").write_text(json.dumps(
        {"paper_hash": h, "full_md_path": str(out / "full.md"), "sections_path": str(out / "sections.json"),
         "full_text": md, "normalized_full_text": _norm(md), "sections": rec}, ensure_ascii=False, indent=2))
    return len(secs)
