"""Answers of the judges kept across runs: the same question asked again, with the same images and the same model, is
answered as it was the first time. A rerun of a document then changes only where the questions changed (11-03: two
full runs of the same 26 documents differed on 9 of them; jev answered 4 of 3,986 identical questions otherwise, all
with no option above 0.6, and Gemini gave other letters for the same sheets and items in 6 of the 9, which sent the
L1-3 executors new issues after every rerun; 文浩 11-04 chose this cache). Kept only where the role's config entry has
"cache": a directory; one file per answer, named by the hash of what was asked."""
import hashlib, json, os, threading
from pathlib import Path
from .. import config


def directory(role):
    try:
        d = config.role(role).get("cache")
    except config.ConfigError:
        return None
    return Path(d).expanduser() / role if d else None


def key(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def get(d, k):
    if d is None:
        return None
    p = d / k[:2] / (k + ".json")
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return None


def put(d, k, value):
    if d is None:
        return
    p = d / k[:2] / (k + ".json")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False))
    os.replace(tmp, p)
