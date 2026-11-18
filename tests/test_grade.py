from mineru_plus.check import grade as GR

PAGES = {1: [(0, {"type": "text"}), (1, {"type": "table"}), (2, {"type": "aside_text"}), (3, {"type": "page_number"})]}


def g(issue):
    return GR.apply([issue], PAGES)[0]["grade"]["level"]


def test_levels():
    assert g({"kind": "table", "page": 1, "block": 1}) == "high"
    assert g({"kind": "text only the primary read", "page": 1, "block": 1, "text": "abc"}) == "high"
    assert g({"kind": "disagreement", "page": 1, "primary": "p = 0.05", "oxr": "p = 0.06"}) == "high"
    assert g({"kind": "disagreement", "page": 1, "primary": "Intern ational 2", "oxr": "International 2"}) == "medium"
    assert g({"kind": "text only the primary read", "page": 1, "block": 2, "text": "April 2023"}) == "low"
    assert g({"kind": "text only the primary read", "page": 1, "block": 3, "text": "12"}) == "low"
    assert g({"kind": "margin text differs from the text layer", "page": 1}) == "low"
    assert g({"kind": "display equation", "page": 1, "mineru": "x^2", "oxr": "x^3"}) == "medium"
    assert g({"kind": "text layer not in the parse", "page": 1, "layer": "N", "parse": ""}) == "medium"
    assert g({"kind": "text only the primary read", "page": 1, "block": "0.captions.1", "text": "Fig"}) == "medium"


def test_every_issue_gets_a_basis():
    out = GR.apply([{"kind": "sentence breaks off", "page": 2}], PAGES)[0]["grade"]
    assert out["level"] == "medium" and out["basis"]
