"""confirm.py's reading of display equations: where full.md's formula is, and what the readings decide"""
from mineru_plus.check import confirm as CF

MD = "Intro text.\n\n$$\na + b \\tag{1}\n$$\n\nwhere $x$ is.\n\n$$\nc = d\n$$\n\nEnd.\n"


def _at(md, s):
    a = md.index(s)
    return a, a + len(s)


def test_formula_at_the_whole_block_or_inside_it():
    a = MD.index("$$\na")
    b = MD.index("$$", a + 2) + 2
    assert CF._formula_at(MD, a, b) == r"a + b \tag{1}"
    assert CF._formula_at(MD, *_at(MD, "+ b")) == r"a + b \tag{1}"
    assert CF._formula_at(MD, a - 2, b + 1) == r"a + b \tag{1}"            # white space around the marks
    assert CF._formula_at(MD, *_at(MD, "c = d")) == "c = d"


def test_formula_at_nothing_but_one_formula():
    assert CF._formula_at(MD, MD.index("a + b"), MD.index("c = d") + 5) is None   # parts of two
    assert CF._formula_at(MD, *_at(MD, "where $x$")) is None                       # prose between two
    assert CF._formula_at(MD, MD.index("Intro"), MD.index("a + b") + 5) is None   # reaching out of one
    a = MD.index("\\tag{1}\n$$") + 8
    assert CF._formula_at(MD, a, MD.index("c = d")) is None                      # from a closing '$$' on
    assert CF._formula_at(MD, 3, 3) is None


def test_formula_at_pairs_from_the_start():
    md = "$$\nx\n$$\nwhere y\n$$\nz\n$$\n"                  # no blank lines around the '$$': nothing taken
    assert CF._formula_at(md, *_at(md, "where y")) is None
    assert CF._formula_at(md, *_at(md, "z")) is None
    assert CF._formula_at("$$\nx\n$$\n\n$$\ny\n\n z\n$$\n", 12, 16) is None     # a blank line inside


def _q(formula, parts=1):
    return {"parts": [{"formula": formula, "text": "", "crop": ""}] * parts}


def test_read_verdict():
    q, m = _q(r"\mathbf{0}_{N}"), r"\mathbf 0_N"
    assert CF.read_verdict(q, [r"\boldsymbol{0}_N", r"\mathbf 0_{N}"], None, m) == "close"
    assert CF.read_verdict(q, [r"\mathbf{0}_{N}"] * 2, None, r"\mathbf{0}") is None    # the formula is not the issue's
    assert CF.read_verdict(q, [r"\mathbf{0}_{N}"] * 2, None, None) is None
    assert CF.read_verdict(q, [r"\mathbf{0}_{N}", None], None, m) is None
    assert CF.read_verdict(q, [], r"\mathbf{0}_{M}", m) is None
    assert CF.read_verdict(q, [r"\mathbf{0}_{M}"] * 2, r"\mathbf{0}_M", m) == "suggest"
    assert CF.read_verdict(q, [r"\mathbf{0}_{M}"] * 2, r"\mathbf{0}_K", m) is None
    assert CF.read_verdict(q, [r"\mathbf{0}_{M}", r"\mathbf{0}_{K}"], r"\mathbf{0}_M", m) is None
    assert CF.read_verdict(q, [r"\mathbf{0}_{N}"] * 2, r"\mathbf{0}_N", m) == "close"
    assert CF.read_verdict(_q(None), ["x", "x"], None, "x") is None
    assert CF.read_verdict(_q(None), ["x", "x"], "x", "y") == "suggest"
    assert CF.read_verdict(_q("x", 2), ["x", "x"], None, "x") is None
    bad = r"\frac{a}{b"                                                       # prints nothing
    assert CF.read_verdict(_q(bad), [bad, bad], None, bad) is None
    assert not CF.same_tex(bad, bad)


def test_formula_at_trusts_no_pairing_it_cannot_make():
    md = "```\n$$\n```\n\n$$\nA\n$$\n\nHello there\n\n$$\nB\n$$\n"
    assert CF._formula_at(md, *_at(md, "Hello there")) is None
    assert CF._formula_at(md, *_at(md, "B")) == "B"                          # a '$$' in code is no formula's
    md = "- $$\nx\n  $$\n\n$$\ny\n$$\n"                                      # an opening '$$' not alone: odd count
    assert CF._formula_at(md, *_at(md, "y")) is None


def test_reading_asks_each_session_even_for_one_crop(monkeypatch, tmp_path):
    crop = tmp_path / "c.png"; crop.write_bytes(b"x")
    calls = []

    class Page:
        def info(self):
            return "fake"

        def session(self, body, sheets, work):
            calls.append(list(sheets))
            return {"1": f"a{len(calls)}"}, None, None
    monkeypatch.setattr(CF.backends, "get", lambda role: Page())
    monkeypatch.setattr(CF.JC, "directory", lambda role: tmp_path / "cache")
    monkeypatch.setattr(CF.G, "_sheets", lambda crops, d: list(crops))
    q = [{"id": "q", "parts": [{"crop": str(crop)}]}]
    assert CF.ask_reading(q, tmp_path / "w") == {"q": ["a1", "a2"]}
    assert CF.ask_reading(q, tmp_path / "w") == {"q": ["a1", "a2"]} and len(calls) == 2   # cached per session


def test_confirm_routes_display_equations(monkeypatch, tmp_path):
    issues = [{"kind": CF.DISPLAY, "oxr": o, "mineru": "x"} for o in "yzw"] + [{"kind": "table"}]
    qs = [{"n": n, "id": f"c{n}", "kind": CF.DISPLAY, "parts": [{"formula": "x", "text": "", "crop": ""}],
           "suspect": ""} for n in range(3)]
    qs.append({"n": 3, "id": "c3", "kind": "table", "parts": [{"text": "", "crop": ""}], "suspect": ""})
    seen = {}
    monkeypatch.setattr(CF, "items", lambda *a, **k: (qs, {}))
    monkeypatch.setattr(CF, "ask_reading", lambda q, w: {"c0": ["x", "x"], "c1": ["z", "z"], "c2": ["x", "q"]})
    monkeypatch.setattr(CF, "ask_jev", lambda q, w, p: seen.setdefault("jev", [x["id"] for x in q]) and {})
    monkeypatch.setattr(CF, "ask_model", lambda q, w: {})
    left, closed, st = CF.confirm("out", "pdf", issues, tmp_path)
    assert seen["jev"] == ["c3"]                                            # display equations are not asked jev
    assert [(c["closed_by"], c["readings"]) for c in closed] == [("the page judge's readings", ["x", "x"])]
    assert [i.get("page_reads_as_oxr") for i in left] == [["z", "z"], None, None]
    assert "page_reads_as_oxr" not in issues[1]                              # the caller's list is not changed
    assert (st["closed by reading"], st["readings attached"], st["left open"]) == (1, 1, 3)


def test_formula_at_a_shifted_pairing_meets_a_blank_line():
    md = "- $$\nx\n  $$\n\nP1\n\n$$\nB\n$$\n\nP2\n\n- $$\nq\n  $$\n\nP3\n\n$$\nC\n$$"     # two openers not alone
    assert CF._formula_at(md, *_at(md, "P1")) is None
    md = "$$ a\n$$\n\nP1\n\n$$\nB\n$$\n\nP2\n\n$$ c\n$$\n\nP3\n\n$$\nD\n$$"
    assert CF._formula_at(md, *_at(md, "P1")) is None
    md = "~~~\n$$\nq\n$$\n~~~\n\nP\n\n$$\nB\n$$\n"
    assert CF._formula_at(md, *_at(md, "q")) is None
    assert CF._formula_at(md, *_at(md, "B")) == "B"


def test_formula_at_no_blank_line_around_or_a_dollar_inside():
    md = "- $$\nx\n  $$\nP1\n$$\nB\n$$\n- $$\nq\n  $$\nP3\n$$\nC\n$$"
    assert CF._formula_at(md, *_at(md, "P1")) is None
    md = "$$ a\nb\n$$\nP1\n$$\nB\n$$\n$$ c\nd\n$$\nP2"
    assert CF._formula_at(md, *_at(md, "P1")) is None
    md = "$$ a\nb\n$$\nP1\n$$ c\nd\n$$\nP2"
    assert CF._formula_at(md, *_at(md, "P1")) is None
    md = "<table>\n<tr><td>\n$$\nx\n$$</td></tr>\n<tr><td>\n$$\ny\n$$</td></tr>\n</table>\n\nP\n\n$$\nB\n$$"
    assert CF._formula_at(md, *_at(md, "x")) is None
    assert CF._formula_at(md, *_at(md, "B")) == "B"


def test_formula_at_fences_as_commonmark():
    for md in ("````\n```\n$$\nq\n$$\n````\n\nP\n\n$$\nB\n$$", "~~~~\n~~~\n$$\nq\n$$\n~~~~\n\nP\n\n$$\nB\n$$"):
        assert CF._formula_at(md, *_at(md, "q")) is None
        assert CF._formula_at(md, *_at(md, "B")) == "B"
    md = "```\n$$\nq\n$$\n\nP\n\n$$\nB\n$$"                                  # unclosed: code to the end
    assert CF._formula_at(md, *_at(md, "q")) is None


def test_formula_at_indented_code_and_a_fence_closed_only_by_its_run():
    md = "text\n\n    $$\n    q\n    $$\n\nP\n\n$$\nB\n$$"
    assert CF._formula_at(md, *_at(md, "q")) is None
    assert CF._formula_at(md, *_at(md, "B")) == "B"
    md = "```\n$$\nq\n$$\n```python\n\nP\n\n$$\nB\n$$"                       # an info string closes nothing
    assert CF._formula_at(md, *_at(md, "q")) is None
    assert CF._formula_at(md, *_at(md, "B")) is None
    md = "```\n$$\nq\n$$\n`````\n\nP\n\n$$\nB\n$$"                            # a longer run closes
    assert CF._formula_at(md, *_at(md, "B")) == "B"
