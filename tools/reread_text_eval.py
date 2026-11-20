"""Measure a page-judge transcription route for 'disagreement' issues (the two readers' text differs) against the
paper line's settled answers (11-19). The rule below was fixed before the run.

    python tools/reread_text_eval.py ITEMS.jsonl WORK_DIR [--workers 4]

Each issue's place is cropped as check/confirm.py crops it (CF.items); the page judge, not shown the parse, writes
the text of every crop exactly, in two sessions (the second with the strips in reverse order), a document's crops on
their own sheets as a run would have them. Readings are cut into tokens (words, single other characters); a line-end
hyphen counts both ways (joined, kept). With L and R the CONTEXT tokens full.md has on each side of the marked place,
M the marked tokens, P the primary's and O OXR's (O put in for P in M):
  keep    every reading holds L M R (either way) and none holds L M[P->O] R: full.md prints the page, the issue closes
  oxr     every reading holds L M[P->O] R and none holds L M R: OXR's text is the page's, a suggestion
Wrong for keep: the paper line edited the issue (decision 'edit'). For oxr the edits are printed to be checked.
"""
import argparse, json, re, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mineru_plus import backends                                                    # noqa: E402
from mineru_plus.check import confirm as CF, gemini as G, judge_cache as JC        # noqa: E402

KIND = "disagreement"
CONTEXT = 2
SESSIONS = 2
ASK = ("Each numbered strip on the sheets is cut from a printed page of a scientific paper. Write for each strip the "
       "text it prints, exactly, character by character, in reading order: every letter, digit and punctuation mark "
       "as printed; each dash as printed (hyphen -, en dash –, em dash —, minus −); a space where the "
       "page leaves one and none where it does not; a comma or a point in a number as printed; superscript text as "
       "^{...} and subscript text as _{...}. Where a word is broken at the end of a line by a hyphen, write the hyphen "
       "and then a line break; join other lines with a space. Do not correct, complete or modernise anything. Where "
       "a strip shows no text, answer null for it.\n\n"
       "Answer with JSON only, one key per strip: {\"1\": \"text\" or null, \"2\": ...}")
TOK = re.compile(r"\w+|[^\w\s]")


def toks(s):
    return TOK.findall(s or "")


def versions(reading):
    """the reading's tokens with each line-end hyphen joined, and kept"""
    br = re.sub(r"-[ \t]*\n\s*", "\x00", reading)
    return [toks(br.replace("\x00", "")), toks(br.replace("\x00", "-"))]


def holds(seq, sub):
    n = len(sub)
    return n > 0 and any(seq[i:i + n] == sub for i in range(len(seq) - n + 1))


def once(seq, sub):
    n = len(sub)
    at = [i for i in range(len(seq) - n + 1) if n and seq[i:i + n] == sub]
    return at[0] if len(at) == 1 else None


def read(qs, work):
    """{id: [reading or None, one a session]}, as confirm.ask_reading asks, with ASK"""
    work = Path(work)
    page, cache = backends.get("page_judge"), JC.directory("page_judge")
    got = {q["id"]: [None] * SESSIONS for q in qs}
    per = CF.PER_SHEET * 4
    for s0 in range(0, len(qs), per):
        chunk = qs[s0:s0 + per]
        for s in range(SESSIONS):
            order = chunk if s % 2 == 0 else chunk[::-1]
            sd = work / "sheets" / f"{s0}_{s}"; sd.mkdir(parents=True, exist_ok=True)
            sheets = G._sheets([q["parts"][0]["crop"] for q in order], sd)
            k = JC.key(page.info(), ASK, [JC.file_hash(x) for x in sheets])
            hit = JC.get(cache, k)
            if hit is not None:
                ans = hit["answer"]
            else:
                ans, use, err = page.session(ASK, sheets, work)
                if ans is not None:
                    JC.put(cache, k, {"answer": ans, "usage": use})
                else:
                    print(f"session failed {work} ({s0}, {s}): {err}", file=sys.stderr)
            for pos, q in enumerate(order, 1):
                v = (ans or {}).get(str(pos))
                got[q["id"]][s] = v if isinstance(v, str) and v.strip() else None
    return got


def doc(pdir, pdf, its, work):
    issues = json.loads((Path(pdir) / "issues.json").read_text(encoding="utf-8"))
    own = work / "__".join(Path(pdir).parts[-3:])
    qs, skipped = CF.items(pdir, pdf, issues, own, kinds=(KIND,))
    qs = [q for q in qs if len(q["parts"]) == 1]
    vr = read(qs, own / "reading") if qs else {}
    at = {q["n"]: q for q in qs}
    rows = []
    for it in its:
        iss = it["issue"]
        row = {"id": it["id"], "decision": it["decision"], "edits": it.get("edits"), "why": iss.get("why"),
               "primary": iss.get("primary"), "oxr": iss.get("oxr")}
        rows.append(row)
        q = at.get(it["issue_index"])
        if q is None:
            row["skipped"] = skipped.get(it["issue_index"], "not one crop"); continue
        t = q["parts"][0]["text"]
        a, b = t.find("⟦"), t.find("⟧")
        L, M, R = toks(t[:a])[-CONTEXT:], toks(t[a + 1:b]), toks(t[b + 1:])[:CONTEXT]
        P, O = toks(row["primary"]), toks(row["oxr"])
        row.update(marked=t[a + 1:b], L=L, R=R, readings=vr.get(q["id"]) or [])
        i = once(M, P)
        if i is None or P == O:
            row["skipped"] = "the primary's text is not once in the marked place"; continue
        lp, lo = L + M + R, L + M[:i] + O + M[i + len(P):] + R
        vs = [versions(r) if r else None for r in row["readings"]]
        ok = len(vs) == SESSIONS and all(vs)
        row["keep"] = ok and all(any(holds(v, lp) for v in x) and not any(holds(v, lo) for v in x) for x in vs)
        row["oxr_read"] = ok and all(any(holds(v, lo) for v in x) and not any(holds(v, lp) for v in x) for x in vs)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("items"); ap.add_argument("work"); ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    work = Path(a.work); work.mkdir(parents=True, exist_ok=True)
    items = [json.loads(x) for x in open(a.items, encoding="utf-8") if x.strip()]
    items = [it for it in items if it.get("issue") and it.get("pdf")]
    by = {}
    for it in items:
        by.setdefault((it["parse_dir"], it["pdf"]), []).append(it)
    with ThreadPoolExecutor(a.workers) as ex:
        parts = list(ex.map(lambda kv: doc(kv[0][0], kv[0][1], kv[1], work), by.items()))
    rows = [r for p in parts for r in p]
    with open(work / "readings.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    asked = [r for r in rows if "keep" in r]
    print(f"items {len(rows)}; asked {len(asked)} (edit {sum(r['decision'] == 'edit' for r in asked)}, "
          f"no_change {sum(r['decision'] == 'no_change' for r in asked)}); skipped "
          f"{dict((k, sum(r.get('skipped') == k for r in rows)) for k in {r.get('skipped') for r in rows if r.get('skipped')})}")
    keep = [r for r in asked if r["keep"]]
    print(f"keep: {len(keep)} (no_change {sum(r['decision'] == 'no_change' for r in keep)}); "
          f"wrong (edit) {[r['id'] for r in keep if r['decision'] == 'edit']}")
    ox = [r for r in asked if r["oxr_read"]]
    print(f"oxr: {len(ox)} (edit {sum(r['decision'] == 'edit' for r in ox)}); not edited {[r['id'] for r in ox if r['decision'] != 'edit']}")
    for r in ox:
        print("  OXR", r["id"], r["decision"], repr(r["primary"]), "->", repr(r["oxr"]), "| edits", r["edits"])
    for r in keep:
        print("  KEEP", r["id"], r["decision"], repr(r["primary"]), "vs", repr(r["oxr"]), "| why", r["why"])
    print("by why (asked / keep / oxr):")
    for w in sorted({r["why"] for r in asked}):
        g = [r for r in asked if r["why"] == w]
        print(f"  {w}: {len(g)} / {sum(r['keep'] for r in g)} / {sum(r['oxr_read'] for r in g)}")


if __name__ == "__main__":
    main()
