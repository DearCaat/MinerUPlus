"""Layer characters that are not content the parse lacks: look-alikes, another order, a font map's punctuation."""
import difflib
from mineru_plus.check import dropped as DR


def plain(raw):
    return "".join(c for c, _ in DR.plain_map(raw))


def test_double_bar_and_lookalikes():
    # '\|' is a double bar inside a formula and an escaped bar outside; '‖' and two bars compare alike
    assert plain(r"$\| W _ { l } \| _ { 2 }$") == plain("‖Wl‖2") == "||Wl||2"
    assert plain(r"$\left\| x \right\|$") == plain("∣∣x∣∣")
    assert plain(r"a \| b") == "a|b"
    assert plain(r"$\sqrt { d _ { k } }$") == "√dk"
    assert plain("∆") == plain("Δ") and plain("⋅") == plain("·")


def ops_of(lay, prim):
    L = [(c, 0) for c in lay]
    return L, list(prim), difflib.SequenceMatcher(None, lay, prim, autojunk=False).get_opcodes()


def test_moved():
    # x_i^loc: the layer lists 'x loc i', the reading 'x i loc'
    L, P, ops = ops_of("xlociand", "xilocand")
    n = next(k for k, o in enumerate(ops) if o[0] == "delete")
    assert DR._moved(ops, L, P, n)
    # a letter the parse has nowhere near is a drop
    L, P, ops = ops_of("andqjLthe", "andqLthe")
    n = next(k for k, o in enumerate(ops) if o[0] == "delete")
    assert not DR._moved(ops, L, P, n)
    # nor is a letter the parse has far away
    L, P, ops = ops_of("ab" + "c" * 20 + "x", "axb" + "c" * 20)
    n = next(k for k, o in enumerate(ops) if o[0] == "delete")
    assert not DR._moved(ops, L, P, n)


def _f(**kw):
    f = {"id": "r1.0.1", "page": 1, "uid": 0, "verdict": "undecided", "layer_words": "𝑥!", "prim": "xi",
         "lay": "x!", "insert": "!", "replaces": "i", "raw_span": [3, 4], "raw_after": 2, "raw_next": 4,
         "crop": "c.png", "moved": False}
    f.update(kw)
    return f


def test_font_map_not_raised():
    second = {1: [{"content": "where $x _ { i }$ is"}]}
    _, _, issues, n = DR.apply("", {}, [_f()], second)
    assert issues == [] and any("font map" in k for k in n)
    # the second reading has the layer's punctuation: raised
    _, _, issues, _ = DR.apply("", {}, [_f()], {1: [{"content": "where x! is"}]})
    assert len(issues) == 1
    # no second reading of the page: raised
    _, _, issues, _ = DR.apply("", {}, [_f()], {})
    assert len(issues) == 1
    # a dropped character (no parse characters replaced) is not a font map
    _, _, issues, _ = DR.apply("", {}, [_f(raw_span=None, replaces="")], second)
    assert len(issues) == 1


def test_moved_not_raised():
    _, _, issues, n = DR.apply("", {}, [_f(moved=True, insert="i", replaces="", raw_span=None)], None)
    assert issues == [] and any("another order" in k for k in n)


def test_symbol_is_not_a_font_map():
    # a symbol both readings take for a letter can be what is printed (PTA-724: '⊮' printed, both readings '1')
    second = {1: [{"content": r"where $\mathbb{1} [ \cdot ]$ is"}]}
    _, _, issues, _ = DR.apply("", {}, [_f(layer_words="⊮[·]", lay="⊩[·]", insert="⊩", replaces="1")], second)
    assert len(issues) == 1
