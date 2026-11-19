"""Measure confirm.py's reading of display equations against the paper line's settled answers (11-19).

    python tools/reread_eval.py ITEMS.jsonl WORK_DIR

ITEMS: lines {id, parse_dir, pdf, issue_index, issue, decision, edits} (issue: a "display equation" issue, with the
primary's LaTeX in "mineru" and OXR's in "oxr"; decision: edit | no_change, the paper line's settled answer; edits:
its accepted edits). Each parse goes through the code confirm() runs: CF.items crops every display equation of the
parse, CF.ask_reading has the page judge write them out (same sheets, order and sessions as in a run), and
CF.read_verdict decides. The settled reading is the primary's with the accepted edits applied (the primary's where
nothing was to change).

Writes WORK/readings.jsonl, one line per item, and prints how many items 'close' settles and how many of those
wrongly (full.md's formula there is not the settled reading), and for 'suggest' how often the reading attached is
the settled one. Nothing here decides a rule goes in: 0 wrong on held-out data does (mineru_plus.md, 解-9).
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mineru_plus.check import confirm as CF, mathrender as MRN          # noqa: E402
from mineru_plus.check.latex_canon import canon                         # noqa: E402

def _settled(item):
    """the settled LaTeX: the primary's with the accepted edits applied; None where an edit is not found in it once"""
    tex = str(item["issue"].get("mineru") or "")
    if item["decision"] == "no_change":
        return tex
    for e in item.get("edits") or []:
        old = next((e[k] for k in ("old", "from", "before", "find") if isinstance(e, dict) and k in e), None)
        new = next((e[k] for k in ("new", "to", "after", "replace") if isinstance(e, dict) and k in e), None)
        if old is None or new is None or tex.count(old) != 1:
            return None
        tex = tex.replace(old, new)
    return tex


def _same(a, b):
    if a is None or b is None:
        return False
    ca, cb = canon(a), canon(b)
    return a.strip() == b.strip() if ca is None or cb is None else ca == cb


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("items"); ap.add_argument("work")
    a = ap.parse_args(argv)
    work = Path(a.work); work.mkdir(parents=True, exist_ok=True)
    items = [json.loads(x) for x in open(a.items, encoding="utf-8") if x.strip()]
    rows, by_dir = [], {}
    for it in items:
        by_dir.setdefault((it["parse_dir"], it["pdf"]), []).append(it)
    for (pdir, pdf), its in by_dir.items():
        issues = json.loads((Path(pdir) / "issues.json").read_text(encoding="utf-8"))
        own = work / "__".join(Path(pdir).parts[-3:])
        qs, skipped = CF.items(pdir, pdf, issues, own, kinds=(CF.DISPLAY,))
        vr = CF.ask_reading(qs, own / "reading") if qs else {}   # as confirm() asks: every display equation of the parse
        at = {q["n"]: q for q in qs}
        for it in its:
            q = at.get(it["issue_index"])
            row = {"id": it["id"], "decision": it["decision"], "primary": it["issue"].get("mineru"),
                   "oxr": it["issue"].get("oxr"), "settled": _settled(it)}
            if q is None or len(q["parts"]) != 1:
                row["skipped"] = skipped.get(it["issue_index"], "not one crop")
                rows.append(row); continue
            row["formula"] = q["parts"][0].get("formula")
            row["model"] = vr.get(q["id"]) or []
            v = CF.read_verdict(q, row["model"], row["oxr"], row["primary"])
            row["close"], row["suggest"] = v == "close", v == "suggest"
            row["formula_is_settled"] = _same(row["formula"], row["settled"])
            row["oxr_is_settled"] = _same(row["oxr"], row["settled"])
            row["oxr_renders"] = bool(row["oxr"]) and MRN.errors([(row["oxr"], True)]) == [None]
            rows.append(row)
    with open(work / "readings.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    done = [r for r in rows if "model" in r]
    known = [r for r in done if r["settled"] is not None]
    print(f"items {len(rows)}; cropped {len(done)}; full.md formula found {sum(r['formula'] is not None for r in done)}; "
          f"settled reading known {len(known)} (edit {sum(r['decision'] == 'edit' for r in known)}, "
          f"no_change {sum(r['decision'] == 'no_change' for r in known)})")
    hit = [r for r in known if r["close"]]
    print(f"close: {len(hit)} of {len(known)} (no_change {sum(r['decision'] == 'no_change' for r in hit)}, "
          f"edit {sum(r['decision'] == 'edit' for r in hit)}); wrong {[r['id'] for r in hit if not r['formula_is_settled']]}")
    print("  edit items closed (full.md already prints the settled reading):",
          [r["id"] for r in hit if r["decision"] == "edit"])
    print("  closed where the settled reading is unknown:", [r["id"] for r in done if r["settled"] is None and r["close"]])
    sg = [r for r in known if r["suggest"]]
    print(f"suggest (OXR's): {len(sg)} of {len(known)}; OXR's is the settled one {sum(r['oxr_is_settled'] for r in sg)}; "
          f"{[(r['id'], r['oxr_is_settled']) for r in sg]}")
    print("  suggested where the settled reading is unknown:", [r["id"] for r in done if r["settled"] is None and r["suggest"]])


if __name__ == "__main__":
    main()
