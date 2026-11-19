"""How often would confirm.py's 'close' (read_verdict) close a display equation whose formula in full.md is wrong?
Seeded errors, no new model calls (11-19).

    python tools/reread_mutants.py WORK_DIR/readings.jsonl

For every item whose formula in full.md is the settled one (the page judge's readings were made from the page, never
from the parse), each seeded error turns the formula into one that prints otherwise (latex_canon tells) and still
renders; the item would be closed wrongly if every session's reading is that wrong one. The errors are those the
paper line found in display equations and those readers make: dots, letter styles, accents, primes, a digit or a
letter in a script, a sign, an upright word in italics or the reverse.
"""
import json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mineru_plus.check import confirm as CF, mathrender as MRN          # noqa: E402
from mineru_plus.check.latex_canon import canon                         # noqa: E402

SWAPS = [(r"\cdots", r"\ldots"), (r"\ldots", r"\cdots"), (r"\dots", r"\cdots"),
         (r"\boldsymbol", r"\mathbf"), (r"\mathbf", r"\boldsymbol"), (r"\mathbf", r"\mathrm"), (r"\boldsymbol", ""),
         (r"\mathcal", r"\mathbb"), (r"\mathbb", r"\mathcal"), (r"\mathcal", r"\mathscr"), (r"\mathcal", ""),
         (r"\widehat", r"\widetilde"), (r"\hat", r"\tilde"), (r"\hat", r"\bar"), (r"\bar", r"\overline"),
         (r"\prime", ""), ("'", ""), (r"\leq", "<"), (r"\geq", ">"), (r"\leq", r"\le"),
         (r"\text", r"\mathit"), (r"\mathrm", r"\mathit"), (r"\operatorname", r"\mathit"),
         ("+", "-"), ("-", "+"), (r"\times", r"\cdot"), (r"\cdot", r"\times"), (r"\in", r"\notin"),
         (r"\sum", r"\prod"), (r"\rightarrow", r"\to"), (r"\to", r"\mapsto"), (r"\phi", r"\varphi"),
         (r"\epsilon", r"\varepsilon"), (r"\theta", r"\vartheta"), (r"\rho", r"\varrho")]


def _swaps(tex):
    for old, new in SWAPS:
        for m in re.finditer(re.escape(old) + (r"(?![A-Za-z])" if old[:1] == "\\" else ""), tex):
            yield f"{old}->{new or 'nothing'}", tex[:m.start()] + new + tex[m.end():]


def _scripts(tex):
    """a digit or a letter in a subscript or superscript changed"""
    for m in re.finditer(r"([_^])\s*\{\s*([0-9A-Za-z])", tex):
        c = m.group(2)
        new = str((int(c) + 1) % 10) if c.isdigit() else (c.upper() if c.islower() else c.lower())
        yield f"script {c}->{new}", tex[:m.start(2)] + new + tex[m.end(2):]


def main(argv=None):
    rows = [json.loads(x) for x in open((argv or sys.argv[1:])[0], encoding="utf-8") if x.strip()]
    base = [r for r in rows if r.get("model") and r.get("formula") and r.get("settled") is not None
            and r.get("formula_is_settled")]
    n_mut, wrong, by_kind = 0, [], {}
    for r in base:
        cp = canon(r["formula"])
        seen = set()
        for how, mut in list(_swaps(r["formula"])) + list(_scripts(r["formula"])):
            cm = canon(mut)
            if cm is None or cm == cp or cm in seen or MRN.errors([(mut, True)]) != [None]:
                continue
            seen.add(cm)
            n_mut += 1
            kind = how.split()[0] if how.startswith("script") else how
            by_kind.setdefault(kind, [0, 0])[0] += 1
            if all(CF.same_tex(x, mut) for x in r["model"]):
                wrong.append((r["id"], how, mut))
                by_kind[kind][1] += 1
    print(f"items {len(base)} (full.md's formula is the settled reading); seeded errors that print otherwise and render {n_mut}; "
          f"closed wrongly {len(wrong)}")
    for k, (n, w) in sorted(by_kind.items(), key=lambda x: -x[1][0]):
        print(f"  {k}: {n} seeded, {w} closed")
    for w in wrong:
        print("  WRONG", w)


if __name__ == "__main__":
    main()
