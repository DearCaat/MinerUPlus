"""agy page judge: an answer whose JSON does not parse is a failed session, not a crash (11-20)"""
import json

from mineru_plus.backends import agy


class Spec(dict):
    def require(self, k):
        return self[k]


def test_answers_with_a_line_break_in_a_string_or_no_json(monkeypatch, tmp_path):
    outs = iter(['{"1": "a\nb"}', '```json\n{\n "1": "x\n "2": "y"}\n```'])

    class P:
        stderr = ""

    def run(*a, **k):
        p = P()
        p.stdout = json.dumps({"response": next(outs), "usage": {"input_tokens": 5}})
        return p

    monkeypatch.setattr(agy.subprocess, "run", run)
    pj = agy.PageJudge(Spec(command="agy-min"))
    ans, use, err = pj.session("q", [], tmp_path)
    assert ans == {"1": "a\nb"} and err is None
    ans, use, err = pj.session("q", [], tmp_path)
    assert ans is None and err.startswith("no JSON in the answer")
