"""Release check for mineru_plus (文浩 11-05: every update keeps the first layer's accepted edits recalled).
For each accepted L1-3 edit: the new output either has it already (its new text, without the old) or raises an
issue covering its old text (same page, sharing a stretch of characters with the old text or with the issue the
edit answered). Anything else is a miss, i.e. a regression.
usage: release_check.py RUNDIR --l13 DIR [--prev PREVROOT]   (DIR: the L1-3 claims.jsonl, gate.json, items.jsonl, revoked.json)
With --prev, the previous version's own edits (checks/edits.json) are checked the same way: still made, or
raised as an issue (listed: fixed before, an open issue now), else a miss.   (claims in revoked.json are left out)"""
import collections, json, re, sys, difflib
from pathlib import Path

args = sys.argv[1:]
R = Path(args[0]); L = Path(args[args.index("--l13") + 1])
gate = json.load(open(L / "gate.json"))["final"]
revoked = {r["id"] for r in json.load(open(L / "revoked.json"))} if (L / "revoked.json").exists() else set()
items = {json.loads(l)["id"]: json.loads(l) for l in open(L / "items.jsonl")}
claims = [json.loads(l) for l in open(L / "claims.jsonl")]
ws = lambda s: re.sub(r"\s+", " ", s or "").strip()
an = lambda s: re.sub(r"[\W_]+", "", s or "").lower()


def docdir(root, pta, doc):
    a = root / f"{pta}__{doc}"
    return a if a.exists() else root / pta / "parse" / doc


def texts(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for k, v in x.items():
            if k not in ("crop", "kind", "why", "crop_placed_by", "id", "page_image", "pdf"):
                yield from texts(v)
    elif isinstance(x, list):
        for v in x:
            yield from texts(v)


def overlap(a, b):
    a, b = an(a), an(b)
    if not a or not b:
        return False
    m = difflib.SequenceMatcher(None, a, b, autojunk=False).find_longest_match(0, len(a), 0, len(b))
    return m.size >= min(12, len(a), len(b)) and m.size >= 4


def flat(s):
    return re.sub(r"\\(?:begin|end)\{[A-Za-z*]+\}|\\[A-Za-z]+|[{}$\s]", "", s or "")


def fixed_alike(it, e, md, side=20):
    try:
        prev = ws(Path(it["fullmd"]).read_text())
    except OSError:
        return False
    old, new = ws(e["old"]), ws(e["new"])
    i = prev.find(old)
    if i < 0 or not old:
        return False
    after = flat(prev[max(0, i - side):i] + new + prev[i + len(old):i + len(old) + side])
    before = flat(prev[max(0, i - side):i + len(old) + side])
    m = flat(md)
    return after in m and before not in m


rows, miss, DETAIL, LOGO = [], [], {}, []
for c in claims:
    if c["decision"] != "edit" or not gate.get(c["id"], "").startswith("accepted") or c["id"] in revoked:
        continue
    it = items[c["id"]]
    d = docdir(R, it["pta"], it["doc"])
    if not (d / "full.md").exists():
        rows.append((c["id"], "no output")); miss.append((c["id"], "no output", "")); continue
    md = ws((d / "full.md").read_text())
    issues = json.loads((d / "issues.json").read_text()) if (d / "issues.json").exists() else []
    page = it["issue"].get("page")
    orig = list(texts(it["issue"]))
    states = []
    for e in c["edits"]:
        old, new = ws(e["old"]), ws(e["new"])
        if (not new or new in md) and (old not in md or old in new):
            states.append("fixed"); continue
        # fixed another way: L1-3's edit applied to the parse it read, the text around it equals the new output's
        # once formula markup is set aside ('std , } \end{array}$ with' and 'std } \end{array}$ , with' read alike)
        if fixed_alike(it, e, md):
            states.append("fixed (alike)"); continue
        cover = [i for i in issues if (page is None or i.get("page") in (page, None) or page in (i.get("pages") or []))
                 and any(overlap(t, old) or any(ws(t) and ws(t) == ws(o) for o in orig)
                         for t in texts(i))]
        if cover:
            states.append("issue: " + cover[0]["kind"]); continue
        if old not in md and re.match(r"- p\d+ (header|footer|side note): ", old):
            states.append("margin line left out (logo rule)"); continue
        states.append("MISS" if old in md else "changed (old text gone, new text absent)")
    # margin logos left out are no regression (文浩 11-05, pathtrove-docs mineru_plus.md 解-6): listed, not counted as misses
    bad = [s for s in states if s == "MISS" or s.startswith("changed")]
    if any(s.startswith("margin line") for s in states):
        LOGO.append(c["id"])
    st = "recalled" if not bad else bad[0]
    rows.append((c["id"], st)); DETAIL[c["id"]] = states
    if bad:
        e = c["edits"][states.index(bad[0])]
        miss.append((c["id"], bad[0], ws(e["old"])[:90] + "  →  " + ws(e["new"])[:60]))
n = len(rows)
print(f"accepted edit claims: {n}; recalled {sum(1 for _, s in rows if s == 'recalled')} "
      f"(of them {len(LOGO)} with margin logo lines left out by the logo rule); misses {len(miss)}")
for m in miss:
    print("  ", *m, sep=" | ")
if "--detail" in args:
    import collections
    print(collections.Counter(s for v in DETAIL.values() for s in v))
    for k, v in DETAIL.items():
        if any(s.startswith("issue") for s in v): print("   ", k, v)


# the previous version's own edits: kept, or raised as an issue; never silently lost (解-6: a fix that turns into an
# issue is recalled but listed, 11-05 PTA-11 MOESM1 d0012: Gemini settled it in one version, undecided in the next).
# An edit carries no position, and a short one ('-' to '–' in a table) occurs all over: each place in the previous
# output that holds the edit's new text is taken with the text around it; the new output either still has that
# stretch (kept), has it with the old text back (reverted), or neither (changed otherwise). Equal edits are counted
# together: (old, new) made n times is reverted min(n, places reverted) times.
if "--prev" in args:
    P = Path(args[args.index("--prev") + 1])
    SIDE = 25
    docs = sorted({(it["pta"], it["doc"]) for it in items.values()})
    tot = collections.Counter()
    out = []
    for pta, doc in docs:
        pd, nd = docdir(P, pta, doc), docdir(R, pta, doc)
        if not (pd / "checks" / "edits.json").exists() or not (nd / "full.md").exists():
            continue
        pmd, nmd = ws((pd / "full.md").read_text()), ws((nd / "full.md").read_text())
        issues = json.loads((nd / "issues.json").read_text()) if (nd / "issues.json").exists() else []
        groups = collections.defaultdict(list)
        for e in json.loads((pd / "checks" / "edits.json").read_text()):
            groups[ws(e["old"]), ws(e["new"])].append(e)
        for (old, new), es in groups.items():
            if old == new:
                tot["kept"] += len(es); continue
            if not new:          # a deletion: kept where the old text with its surroundings is gone; not placed here
                # kept unless the new output has the deleted text more often than the previous one did
                tot["kept" if nmd.count(old) <= pmd.count(old) else "deletion reverted?"] += len(es); continue
            starts = [m.start() for m in re.finditer(re.escape(new), pmd)]
            reverted = []
            for st in starts:
                left, right = pmd[max(0, st - SIDE):st], pmd[st + len(new):st + len(new) + SIDE]
                if flat(left + new + right) in flat(nmd):
                    continue
                if flat(left + old + right) in flat(nmd):
                    reverted.append(left + "⟦" + old + "⟧" + right)
            n_rev = min(len(es), len(reverted))
            tot["kept"] += len(es) - n_rev
            for r in reverted[:n_rev]:
                cover = [i for i in issues if any(overlap(t, r.replace("⟦", "").replace("⟧", "")) for t in texts(i))
                         and (i.get("page") in (es[0].get("page"), None) or es[0].get("page") in (i.get("pages") or []))]
                k = "fixed before, issue now" if cover else "MISS"
                tot[k] += 1
                out.append((k, pta, doc, es[0].get("route"), r[-90:], "→ " + new[:30], cover[0]["kind"] if cover else ""))
    print("previous version's own edits:", dict(tot))
    for o in out:
        print("  ", *o, sep=" | ")
