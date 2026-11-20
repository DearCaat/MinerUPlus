"""Measure the closing rule for 'disagreement' issues on parses with no settled answers (11-20). An issue closes
where the page's text layer, character for character (spaces aside), holds the primary's reading and not OXR's
between the same neighbours (check/resolve._layer_says, exact) and every page-judge transcription of the crop holds
it and not OXR's (tools/reread_text_eval: tokens, two words of context, a line-end hyphen both ways). The rule was
fixed on 11-19 from the paper line's 98 settled disagreements before any held-out run; its closes are to be checked
against the page by eye. Listed too: where both say OXR's (the edit the rule would suggest).

    python tools/text_close_eval.py DOCS.jsonl WORK_DIR [--workers 4]

DOCS: lines {parse_dir, pdf}. Writes WORK/rows.jsonl; copies the crop of every close and suggestion to WORK/view/.

Outcome (11-20), not adopted: on the development parses (32, the paper line's; PTA-000123's main is among them twice) 17 closes at 12 places, all printing what
the page prints (five em dashes the layer holds as U+2014, six hollow-circle bullets, one drug name); on 10 held-out
papers (seed 20261120, holdout_1120/draw.json) 88 disagreements, 24 askable, 0 closes: there the primary was mostly
wrong or the difference a matter of convention ('STAR★METHODS' where the primary and a symbol font's layer both have
'+', small capitals, a line-break hyphen). Too few closes for a route in the product; the two-source requirement
did keep the layer's '+' and the judge's 'visualisation' for a printed 'visualidation' from closing anything.
"""
import argparse, json, re, shutil, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pymupdf                                                              # noqa: E402
from mineru_plus import layer as LY                                          # noqa: E402
from mineru_plus.check import confirm as CF, resolve as RS                   # noqa: E402
import reread_text_eval as T                                                 # noqa: E402


def doc(pdir, pdf, work):
    pdir = Path(pdir)
    issues = json.loads((pdir / "issues.json").read_text(encoding="utf-8"))
    subs = {s["id"]: s for s in json.loads((pdir / "checks" / "disagreements.json").read_text(encoding="utf-8"))}
    own = work / "__".join(pdir.parts[-3:])
    qs, skipped = CF.items(str(pdir), pdf, issues, own, kinds=(T.KIND,))
    qs = [q for q in qs if len(q["parts"]) == 1]
    vr = T.read(qs, own / "reading") if qs else {}
    d = pymupdf.open(pdf)
    at = {q["n"]: q for q in qs}
    rows = []
    for n, iss in enumerate(issues):
        if iss.get("kind") != T.KIND:
            continue
        row = {"doc": str(pdir), "n": n, "id": iss.get("id"), "page": iss.get("page"), "why": iss.get("why"),
               "primary": iss.get("primary"), "oxr": iss.get("oxr")}
        rows.append(row)
        s = subs.get(iss.get("id"))
        row["layer"] = (RS._layer_says(LY.page(d, s["page"] - 1), s, exact=True)
                        if s and s.get("left") is not None and s.get("page") else None)
        q = at.get(n)
        if q is None:
            row["skipped"] = skipped.get(n, "not one crop"); continue
        t = q["parts"][0]["text"]
        a, b = t.find("⟦"), t.find("⟧")
        L, M, R = T.toks(t[:a])[-T.CONTEXT:], T.toks(t[a + 1:b]), T.toks(t[b + 1:])[:T.CONTEXT]
        P, O = T.toks(row["primary"]), T.toks(row["oxr"])
        row.update(marked=t[a + 1:b], readings=vr.get(q["id"]) or [])
        i = T.once(M, P)
        if i is None or P == O:
            row["skipped"] = "the primary's text is not once in the marked place"; continue
        lp, lo = L + M + R, L + M[:i] + O + M[i + len(P):] + R
        vs = [T.versions(r) if r else None for r in row["readings"]]
        ok = len(vs) == T.SESSIONS and all(vs)
        keep = ok and all(any(T.holds(v, lp) for v in x) and not any(T.holds(v, lo) for v in x) for x in vs)
        oxr = ok and all(any(T.holds(v, lo) for v in x) and not any(T.holds(v, lp) for v in x) for x in vs)
        row["read_primary"], row["read_oxr"] = keep, oxr
        row["close"] = keep and row["layer"] == "primary"
        row["suggest_oxr"] = oxr and row["layer"] == "oxr"
        if row["close"] or row["suggest_oxr"]:
            dst = work / "view" / f"{own.name}__{n}.png"
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(q["parts"][0]["crop"], dst)
            row["view"] = str(dst)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("docs"); ap.add_argument("work"); ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    work = Path(a.work); work.mkdir(parents=True, exist_ok=True)
    docs = [json.loads(x) for x in open(a.docs, encoding="utf-8") if x.strip()]
    with ThreadPoolExecutor(a.workers) as ex:
        parts = list(ex.map(lambda x: doc(x["parse_dir"], x["pdf"], work), docs))
    rows = [r for p in parts for r in p]
    with open(work / "rows.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    asked = [r for r in rows if "read_primary" in r]
    print(f"docs {len(docs)}; disagreements {len(rows)}; asked {len(asked)}; layer says primary "
          f"{sum(r['layer'] == 'primary' for r in rows)}, oxr {sum(r['layer'] == 'oxr' for r in rows)}, "
          f"neither {sum(r['layer'] is None for r in rows)}")
    print(f"readings say primary {sum(r['read_primary'] for r in asked)}, oxr {sum(r['read_oxr'] for r in asked)}; "
          f"close (both primary) {sum(r['close'] for r in asked)}; suggest (both oxr) {sum(r['suggest_oxr'] for r in asked)}; "
          f"readings against the layer {sum((r['read_primary'] and r['layer'] == 'oxr') or (r['read_oxr'] and r['layer'] == 'primary') for r in asked)}")
    for r in asked:
        if r["close"] or r["suggest_oxr"] or (r["read_primary"] and r["layer"] == "oxr") or (r["read_oxr"] and r["layer"] == "primary"):
            tag = "CLOSE" if r["close"] else "SUGGEST" if r["suggest_oxr"] else "AGAINST"
            print(f"  {tag} {(re.search(r'PTA-[0-9]+', r['doc']) or [r['doc']])[0]} n{r['n']} p{r['page']} {r['primary']!r} vs {r['oxr']!r} "
                  f"layer={r['layer']} | {r['why']} | {r.get('view', '')}")


if __name__ == "__main__":
    main()
