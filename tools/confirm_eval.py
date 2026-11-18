"""Measure the confirmation of open issues (mineru_plus/check/confirm.py) on parses whose issues a caller has settled.

    python tools/confirm_eval.py <parse dir> <work dir> [--pdf PDF] [--no-model]

Asks jev about every issue of the kinds confirm.py handles and, unless --no-model, the page judge about every one as
well (not only those jev leaves open), so that each layer's closings can be counted against the settled answers.
Writes <work dir>/answers.jsonl: one line per issue (index in issues.json, kind, jev, model, or why it was not asked).
The judges' answers are cached as in a parse (--cache, MINERU_PLUS_CACHE or the config file)."""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from mineru_plus.check import confirm as CF, judge_cache as JC


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("parse"); ap.add_argument("work")
    ap.add_argument("--pdf"); ap.add_argument("--no-model", action="store_true"); ap.add_argument("--cache")
    a = ap.parse_args(argv)
    out, work = Path(a.parse), Path(a.work)
    work.mkdir(parents=True, exist_ok=True)
    if a.cache:
        JC.use(a.cache)
    pdf = a.pdf or json.loads((out / "report.json").read_text())["input"]
    issues = json.loads((out / "issues.json").read_text())
    issues = issues if isinstance(issues, list) else issues["issues"]
    qs, skipped = CF.items(out, pdf, issues, work)
    vj = CF.ask_jev(qs, work / "jev")
    vm = {} if a.no_model else CF.ask_model(qs, work / "model")
    asked = {q["n"]: q for q in qs}
    with open(work / "answers.jsonl", "w") as f:
        for n, i in enumerate(issues):
            row = {"issue_index": n, "kind": i.get("kind")}
            if n in asked:
                q = asked[n]
                row.update(jev=vj.get(q["id"]), model=vm.get(q["id"]), crops=[p["crop"] for p in q["parts"]],
                           text=[p["text"] for p in q["parts"]])
            else:
                row["not_asked"] = skipped.get(n, "kind not confirmed")
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"issues": len(issues), "asked": len(qs), "skipped": len(skipped)}))


if __name__ == "__main__":
    main()
