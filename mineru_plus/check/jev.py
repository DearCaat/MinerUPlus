"""jev closed choices asked in both option orders; an item is decided only when both orders agree.
The requests go to the decision_judge backend (mineru_plus/backends): a gateway helper, or an OpenAI-compatible chat
endpoint, as the config file says. The question, the option order and the caching by question hash are here; the
backend only answers."""
import hashlib, json
from pathlib import Path
from .. import backends
from . import judge_cache as JC


def ask(questions, work, tag):
    """questions: [{"id", "state", "instructions", "options": {key: text, key2: text}, "images"?}] with two options.
    Returns {id: key | "undecided" | "not judged: request failed"}. Answers are cached in work under the id and a
    hash of the question (state, instructions, options, images): a rerun asks again only what changed."""
    work = Path(work); work.mkdir(parents=True, exist_ok=True)
    judge = backends.get("decision_judge")
    fin, fout = work / f"{tag}_in.jsonl", work / f"{tag}_out.jsonl"
    key = {q["id"]: q["id"] + "~" + hashlib.md5(json.dumps([q["state"], q["instructions"], q["options"],
                                                             q.get("neither"), q.get("images")]).encode()).hexdigest()[:10]
           for q in questions}
    lines = []
    for q in questions:
        keys = list(q["options"])
        for order in (keys, keys[::-1]):
            line = {"id": f"{key[q['id']]}|{order[0]}", "model": judge.model, "state": q["state"],
                    "questions": {"which": {"type": "choice", "instructions": q["instructions"], "criteria": {
                        "first": q["options"][order[0]], "second": q["options"][order[1]],
                        **({"neither": q["neither"]} if q.get("neither") else {})}}}}
            if q.get("images"):
                line["images"] = q["images"]
            lines.append(line)
    with open(fin, "w") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    cache = JC.directory("decision_judge")
    ck = lambda line: JC.key(line["model"], line["state"], line["questions"], line.get("images"))
    if lines and cache is not None:      # answers kept from earlier runs go into the out file, which the backend resumes
        have = {x["id"] for x in map(json.loads, fout.read_text().splitlines()) if x.get("ok")} if fout.exists() else set()
        with open(fout, "a") as f:
            for line in lines:
                a = None if line["id"] in have else JC.get(cache, ck(line))
                if a is not None:
                    f.write(json.dumps({"id": line["id"], "ok": True, "answers": a, "cached": True}) + "\n")
    if questions:
        judge.run(fin, fout)     # resumes from the out file; failed requests are asked again
    if lines and cache is not None and fout.exists():
        asked = {line["id"]: line for line in lines}
        for x in map(json.loads, fout.read_text().splitlines()):
            if x.get("ok") and not x.get("cached") and x["id"] in asked:
                JC.put(cache, ck(asked[x["id"]]), x["answers"])
    per, failed = {}, set()
    keys_of = {key[q["id"]]: list(q["options"]) for q in questions}
    if fout.exists():
        for l in fout.read_text().splitlines():
            x = json.loads(l)
            qid, first = x["id"].rsplit("|", 1)
            if qid not in keys_of:
                continue
            if not x.get("ok"):
                failed.add(qid); continue
            pr = x["answers"]["which"]["probabilities"]
            top = max(pr, key=pr.get)
            ks = keys_of[qid]
            second = ks[1] if first == ks[0] else ks[0]
            per.setdefault(qid, {})[first] = {"first": first, "second": second}.get(top, top)
    out = {}
    for q in questions:
        v = per.get(key[q["id"]], {})
        if len(v) == 2:
            a, b = v.values()
            out[q["id"]] = a if a == b else "undecided"
        else:
            out[q["id"]] = "not judged: request failed"
    return out
