"""Backends: how each external role is served. The config file names one backend per role (mineru_plus/config.py).

Roles and their backends:
  primary_reader   gateway (tool-call.py, tool mineru), command, mineru_kit (mineru-kit, run locally)
  second_reader    gateway (tool-call.py, tool oxr), command, openai_vlm
  decision_judge   gateway (jev-call.py), openai
  page_judge       agy, openai

Contracts: what each role must produce, and what the checks read.

primary reader, directory out/ (written by the backend):
  structured_content.json  {"pages": [{"page_idx": 0, "blocks": [{"type": ..., "bbox": [x0, y0, x1, y1], "content": ...}]}]}
                           page_idx is zero-based; bbox is normalised to the page (0 to 1); other keys are optional
  full.md                  the markdown of the parse (markdown.md or any *.md is accepted)
  reader_meta.json         a JSON object describing the run
  middle_json.json, images/  optional: figure bodies (image_body, chart_body blocks) and the images the markdown links to

second reader, directory out/:
  pages.json               {"pages": [{"page": 1, "blocks": [{"type": "Text", "content": "..."}]}]}
                           page is one-based. The checks read the types Text, Title, Caption and Footnote as prose,
                           Formula and Table as formulas and tables, and the content of every block
  reader_meta.json         a JSON object describing the run

decision judge: a file of request lines in, a file of answer lines out (check/jev.py builds the requests):
  request  {"id", "model", "state", "questions": {"which": {"type": "choice", "instructions": ...,
            "criteria": {"first": text, "second": text, "neither": text (optional)}}}, "images": [data URL, ...]}
  answer   {"id", "ok": true, "answers": {"which": {"probabilities": {"first": p, "second": p, "neither": p}}}}
           or {"id", "ok": false, "error": "..."}
  A backend that resumes skips the requests whose answers are already ok in the out file.

page judge: session(body, sheets, cwd) returns (parsed JSON or None, usage or None, error or None). body is the question
  text; sheets are PNG files; the answer must contain one JSON object.
"""
import threading
from .. import config
from ..config import role as config_role
from . import agy, command, gateway, mineru_kit, openai_chat, openai_vlm

BACKENDS = {
    "primary_reader": {"gateway": gateway.PrimaryReader, "command": command.PrimaryReader,
                       "mineru_kit": mineru_kit.PrimaryReader},
    "second_reader": {"gateway": gateway.SecondReader, "command": command.SecondReader,
                      "openai_vlm": openai_vlm.SecondReader},
    "decision_judge": {"gateway": gateway.DecisionJudge, "openai": openai_chat.DecisionJudge},
    "page_judge": {"agy": agy.PageJudge, "openai": openai_chat.PageJudge},
}
_made = {}
_lock = threading.Lock()


def get(role):
    """The backend instance of a role, built from the config file on first use."""
    with _lock:
        if role not in _made:
            spec = config_role(role)
            table = BACKENDS[role]
            cls = table.get(spec["backend"])
            if cls is None:
                raise spec.fail(f"unknown backend '{spec['backend']}'; the backends of this role are {', '.join(table)}")
            _made[role] = cls(spec)
        return _made[role]


def describe(role):
    """What a role runs with, for the report: the backend name and its model, tier or command name. Holds no secret
    and no path (a command appears by its name only). A role that is not configured, or whose backend cannot be
    built, is described by its state."""
    try:
        spec = config_role(role)
    except config.ConfigError:
        return {"backend": None, "note": "not configured"}
    try:
        inst = get(role)
    except config.ConfigError:
        return {"backend": spec["backend"], "note": "not usable (the warning at the start of the run says why)"}
    return {"backend": spec["backend"], **inst.info()}


def reset():
    """Forget the backends built so far (after the config file changes)."""
    with _lock:
        _made.clear()
