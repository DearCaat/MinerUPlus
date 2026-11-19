import pytest
from mineru_plus.check import mathrender as M

needs_katex = pytest.mark.skipif(not M.available(), reason="node or the bundled KaTeX missing")


def test_find_formulas_and_stray_dollars():
    md = "a $x$ b \\$5 and $$\ny = 1\n$$\n\nEquation $(8): $r$$ across\n\n```\n$ not math\n```"
    fs, stray = M.find(md)
    assert [f["tex"] for f in fs] == ["x", "\ny = 1\n", "(8): "]
    assert [md[p] for p in stray] == ["$", "$"] and all(md.index("across") > p > md.index("Equation") for p in stray)


def test_no_stray_where_dollars_pair():
    assert M.find("cost \\$5 and $a$ and $$b$$")[1] == []


@needs_katex
def test_unscript_braces_the_second_script():
    (msg, pos), = M.errors([("W ^ {A} ^ {T}", True)])
    assert "Double superscript" in msg
    assert M.unscript("W ^ {A} ^ {T}", pos) == "W ^ {A} {}^ {T}"
    assert M.errors([("W ^ {A} {}^ {T}", True)]) == [None]


@needs_katex
def test_repair_braces_double_scripts_and_keeps_the_rest():
    md = "Text $a$.\n\n$$\nW _ {i} ^ {A} ^ {T} x\n$$\n\nMore."
    new, c, issues, done = M.repair(md, {}, None)
    assert new == "Text $a$.\n\n$$\nW _ {i} ^ {A} {}^ {T} x\n$$\n\nMore."
    assert c["scripts braced"] == 1 and not issues


OX = {12: [{"type": "Text", "content": "We reported two Pearson correlations, as given in Equation (8): $r_{cell}$"}],
      13: [{"type": "Text", "content": "across features within each cell and $r_{gene}$ across cells for each feature."}]}
PAGES = {12: [(4, {"type": "text", "content": "We reported two Pearson correlations, as given in Equation $(8): $r$$"})]}
MD = ("Intro. We reported two Pearson correlations, as given in Equation $(8): $r _ {cell}$$ across features within "
      "each cell and $r _ {gene}$ across cells for each feature. Next sentence.")


@needs_katex
def test_open_issue_carries_the_second_reading():
    new, c, issues, _ = M.repair(MD, PAGES, OX)
    assert new == MD and c["left open"] == 1 and len(issues) == 1
    assert issues[0]["kind"] == "formula that does not render"
    assert issues[0]["oxr"] == " (8): $r_{cell}$ " and issues[0]["stretch"] == " $(8): $r _ {cell}$$ "


@needs_katex
def test_reread_refused_when_the_second_reading_has_other_words():
    ox = {12: [{"type": "Text", "content": "We reported two Pearson values for every gene and protein in the whole "
                                           "dataset, measured once per slide across cells for each feature."}]}
    new, c, issues, _ = M.repair(MD, PAGES, ox)
    assert new == MD and c["left open"] >= 1
    assert all(i["kind"] == "formula that does not render" for i in issues)


@needs_katex
def test_reread_refused_when_the_first_words_occur_twice():
    ox = {12: OX[12] + OX[12], 13: OX[13]}
    new, c, issues, _ = M.repair(MD, PAGES, ox)
    assert new == MD and "oxr" not in issues[0]


def test_currency_and_code_are_not_formulas():
    assert M.find("The fee is \\$5 per day.") == ([], [])
    assert M.find("Run `$HOME/x` now.") == ([], [])
    fs, stray = M.find("Run this:\n```\n$HOME/bin\n```\nThen $x$.")
    assert [f["tex"] for f in fs] == ["x"] and stray == []
    assert [f["tex"] for f in M.find("```\ncode\n```\nWe have $y$ here.")[0]] == ["y"]


def test_escaped_dollar_inside_a_formula():
    fs, stray = M.find("The unit cost is $\\$5$ per slide.")
    assert [f["tex"] for f in fs] == ["\\$5"] and stray == []


@needs_katex
def test_reread_refused_when_the_last_words_occur_twice():
    md = "We fit $\\foo x$ and then tested the model on the cohort in the study group."
    ox = {1: [{"type": "Text", "content": "We fit x and then tested the model in the study group on the cohort in "
                                         "the study group."}]}
    new, c, _, _ = M.repair(md, {}, ox)
    assert new == md and c["left open"] == 1


@needs_katex
def test_reread_refused_when_a_number_differs():
    md = "The AUC was 0.9371 for $\\foo x$ and the cohort in this study."
    ox = {1: [{"type": "Text", "content": "The AUC was 0.9372 for $x$ and the cohort in this study."}]}
    new, c, _, _ = M.repair(md, {}, ox)
    assert new == md and c["left open"] == 1
    md = "The AUC was 0.9371 for x$ and the cohort in this study."          # a stray '$': only the '$' move
    ox = {1: [{"type": "Text", "content": "The AUC was 0.9371 for $x$ and the cohort in this study."}]}
    new, c, issues, _ = M.repair(md, {}, ox)
    assert new == md and c["left open"] == 1 and len(issues) == 1
    assert issues[0]["kind"] == "formula that does not render" and issues[0]["oxr"] == " $x$ " and issues[0]["stretch"] == " x$ "
    ox = {1: [{"type": "Text", "content": "The AUC was 0.9372 for $x$ and the cohort in this study."}]}
    new, c, _, _ = M.repair(md, {}, ox)
    assert new == md and c["left open"] == 1


@needs_katex
def test_reread_keeps_words_outside_the_stretch():
    md = "We tested the drug and it did not reduce mortality in x$ for the trial group."
    ox = {1: [{"type": "Text", "content": "We tested the drug and it did reduce mortality in $x$ for the trial group."}]}
    new, c, issues, _ = M.repair(md, {}, ox)
    assert new == md and c["left open"] == 1 and len(issues) == 1
    assert issues[0]["kind"] == "formula that does not render" and issues[0]["oxr"] == " $x$ " and issues[0]["stretch"] == " x$ "


@needs_katex
def test_reread_never_swaps_the_primarys_words_or_signs():
    for mine, theirs in [("it did not reduce $\\foo x$", "it did reduce $x$"),
                         ("with p < $\\foo x$", "with p > $x$"),
                         ("a loss of -5 $\\foo x$", "a loss of 5 $x$"),
                         ("of 1,000 $\\foo x$", "of 1.000 $x$"),
                         ("doped with Co $\\foo x$", "doped with CO $x$"),
                         ("not and not $\\foo x$", "not and $x$")]:
        md = f"Alpha beta gamma {mine} delta epsilon zeta."
        ox = {1: [{"type": "Text", "content": f"Alpha beta gamma {theirs} delta epsilon zeta."}]}
        new, c, _, _ = M.repair(md, {}, ox)
        # the primary's words and signs stay: either nothing changes or only the broken formula does
        assert new in (md, md.replace("$\\foo x$", "$x$")), mine


@needs_katex
def test_html_tags_hide_nothing():
    md = "Alpha beta gamma p < 0.05 and q > 0.1 $\\foo x$ delta epsilon zeta."
    ox = {1: [{"type": "Text", "content": "Alpha beta gamma p < 0.5 and q > 0.1 $x$ delta epsilon zeta."}]}
    new, c, _, _ = M.repair(md, {}, ox)
    assert new in (md, md.replace("$\\foo x$", "$x$"))
    assert "0.05" in new


@needs_katex
def test_reread_refused_when_a_number_is_added():
    md = "The cohort in 2019 used $\\foo x$ for the trial group in Europe."
    ox = {1: [{"type": "Text", "content": "The cohort in 2019 used $x$ for the 1 trial group in Europe."}]}
    new, c, _, _ = M.repair(md, {}, ox)
    assert new == md and c["left open"] == 1


@needs_katex
def test_unescaped_currency_is_reported_not_reread():
    md = "The fee is $5 per day for every patient in the study."
    ox = {1: [{"type": "Text", "content": "The fee is 5 per day for every patient in the study."}]}
    new, c, issues, _ = M.repair(md, {}, ox)
    assert new == md and c["stray dollars"] == 1 and c["left open"] == 1
    assert "currency" in issues[0]["found"]


@needs_katex
def test_backtick_inside_a_formula_is_braced_or_reported():
    md = "Use $W ^ {`A`} ^ {T}$ here."
    new, c, issues, _ = M.repair(md, {}, None)
    assert (new != md and c["scripts braced"] == 1) or (new == md and c["left open"] == 1 and issues)


@needs_katex
def test_open_issue_names_its_page():
    md = "Intro.\n\n$$\n\\foo {z}\n$$\n\nMore."
    pages = {3: [(7, {"type": "equation", "content": "$$\n\\foo {z}\n$$"})]}
    _, _, issues, _ = M.repair(md, pages, None)
    assert [(i["kind"], i["page"], i["block"]) for i in issues] == [("formula that does not render", 3, 7)]


@needs_katex
def test_reread_refused_when_the_stretch_loses_a_word_sign_or_number():
    for mine, theirs in [("$\\foo x$ not", "$x$"), ("$\\foo x$ <", "$x$ >"), ("$\\foo x$ - 5", "$x$ 5"),
                         ("$\\foo x$", "$x$ 7"),
                         ("$\\foo x$ not not", "$x$ not"), ("$\\foo x$ <b>", "$x$ β")]:
        md = f"Alpha beta gamma {mine} delta epsilon zeta."
        ox = {1: [{"type": "Text", "content": f"Alpha beta gamma {theirs} delta epsilon zeta."}]}
        new, c, _, _ = M.repair(md, {}, ox)
        assert new == md and c["left open"] == 1, mine


@needs_katex
def test_round4_probes_are_refused():
    cases = [
        ("the dose was rose by 1,000 $\\foo x$ units in all.",
         ["The sum by 1.000 in cases. The dose rose by 1.000 units in all."]),
        ("We saw the effect for $\\foo x$ –5 units in the study group.",
         ["We saw the effect for x 5 units in the study group."]),
        ("Alpha beta gamma $\\foo x$ delta epsilon zeta.",
         ["Alpha beta gamma $\\text{reported}$ delta epsilon zeta."]),
        ("The dose was $\\foo x$ in the group today.",
         ["The dose was $ a", "patients b$ in the group today."]),
        ("The dose was $\\foo 5$ in the group today.",
         ["The dose was in the group today."]),
        ("Alpha beta gamma $\\foo x$ well-known delta epsilon zeta.",
         ["Alpha beta gamma $x$ wellknown delta epsilon zeta."]),
    ]
    for md, blocks in cases:
        ox = {1: [{"type": "Text", "content": b} for b in blocks]}
        new, c, _, _ = M.repair(md, {}, ox)
        assert new == md or "$\\foo" not in md.replace(new, ""), md
        assert new == md and c["left open"] == 1, md


def test_tokens_keep_numbers_whole():
    assert [w for w, _, _ in M._tokens("by 1,000 and 0.05 units")] == ["by", "1,000", "and", "0.05", "units"]


@needs_katex
def test_round5_probes_are_refused():
    cases = [("The effect was $p<0.05\\foo$ in the group today.", "The effect was p 0.05 in the group today."),
             ("The effect was $\\text{not}\\foo x$ in the group today.", "The effect was x in the group today."),
             ("The change was $\\foo x$ +5 units in the group.", "The change was x 5 units in the group."),
             ("The rate was $\\foo x$ ⁻5 mol in the group.", "The rate was x 5 mol in the group.")]
    for md, ox in cases:
        new, c, _, _ = M.repair(md, {}, {1: [{"type": "Text", "content": ox}]})
        assert new == md and c["left open"] == 1, md


@needs_katex
def test_second_reading_is_a_candidate_only():
    for md, ox in [
            ("Alpha beta gamma x$ -5 units delta epsilon.", "Alpha beta gamma $x$ −5 units delta epsilon.")]:
        new, c, issues, _ = M.repair(md, {}, {1: [{"type": "Text", "content": ox}]})
        assert new == md and c["left open"] == 1 and len(issues) == 1, md
        assert issues[0]["kind"] == "formula that does not render" and issues[0]["oxr"] == " $x$ −", md
        assert issues[0]["stretch"] == " x$ -", md


@needs_katex
def test_reread_never_rewrites_a_formula():
    """a reading of the failed formula other than the primary's is left to the open issue, even a likely one"""
    for md, ox in [("Alpha beta gamma $\\foo x$ delta epsilon zeta.", "Alpha beta gamma $x$ delta epsilon zeta."),
                   ("Alpha beta gamma $\\foo n$ delta epsilon zeta.", "Alpha beta gamma $m$ delta epsilon zeta."),
                   ("Alpha beta gamma $\\foo x \\not\\in S$ delta epsilon.", "Alpha beta gamma $x \\in S$ delta epsilon."),
                   ("Alpha beta gamma $\\foo y$ $\\mathbb{R}$ delta epsilon.", "Alpha beta gamma $y$ $R$ delta epsilon."),
                   ("Alpha beta gamma x$ delta epsilon zeta.", "Alpha beta gamma $x$\n\ndelta epsilon zeta.")]:
        new, c, _, _ = M.repair(md, {}, {1: [{"type": "Text", "content": ox}]})
        assert new == md and c["left open"] == 1, md


@needs_katex
def test_round6_probes_are_refused():
    cases = [  # failures at a paragraph's edge: the second reader's block edge says nothing of where its reading ends
        ("$\\foo x$ is the rate in the cohort group today.", ["$x$ is the rate in the cohort group today."]),
        ("The rate was high in the cohort $\\foo x$.", ["The rate was high in the cohort", "x."]),
        ("$\\foo y$ hnnqj wcplfh pepqva asy ilkez txq rfoa riump.",
         ["y", "hnnqj wcplfh pepqva asy ilkez txq rfoa riump."]),
        # a formula KaTeX renders is dropped; the failed one is dropped
        ("The dose was high $\\foo x$ $\\frac{a}{b}$ in the group today.", ["The dose was high x in the group today."]),
        ("The rate was $\\foo x$ high in the cases.", ["The rate was high in the cases."]),
        # '<y and z>' in a formula is no markup; operator names; '~'; the order of words
        ("The rate was $\\foo <y and z>$ high in cases.", ["The rate was $<y or z>$ high in cases."]),
        ("We want to minimize $\\foo \\min_{x} f(x)$ over the set today.",
         ["We want to minimize $\\max_{x} f(x)$ over the set today."]),
        ("The patients were ~$\\foo x$ 5 mg in cases today.", ["The patients were $x$ 5 mg in cases today."]),
        ("a b c $\\foo x$ d not e f g.", ["a b c x not d e f g."])]
    for md, ox in cases:
        new, c, _, _ = M.repair(md, {}, {1: [{"type": "Text", "content": x} for x in ox]})
        assert new == md and c["left open"] == 1, md


@needs_katex
def test_round7_probes_are_refused():
    cases = [("The dose was $\\foo x$ ~5 mg in cases now.", "The dose was x 5 mg in cases now."),
             ("The dose was $\\foo x$ ~ 5 mg in cases now.", "The dose was x 5 mg in cases now."),
             ("The dose was $\\foo x$ 5 mg in cases now.", "The dose was x ~5 mg in cases now."),
             ("The rate was high $\\foo x$\n~~~\nfoo bar baz\n~~~\nthen low today here.",
              "The rate was high x foo bar baz then low today here."),
             ("The dose was $\\foo x$ $\\text{cohort}$ $\\text{treated}$ and here now.",
              "The dose was x treated cohort and here now."),
             ("The dose was $\\foo x$ $n=2$ $m=3$ and here now.", "The dose was x m=3 n=2 and here now."),
             ("The rate was high $\\foo q$ <x and y ∈ S> in cases today now.",
              "The rate was high q <x or y ∈ S> in cases today now."),
             ("The dose was $\\foo x$ ~(5 mg) in cases now.", "The dose was x (5 mg) in cases now."),
             ("The dose was $\\foo x$ × high low in cases now.", "The dose was x high low in cases now."),
             # round 8
             ("The dose was $\\foo x$ ~ high low in cases now.", "The dose was x high low in cases now."),
             ("The dose was $\\foo x$ high low in cases now.", "The dose was x ~ high low in cases now."),
             ("The rate was high $\\foo q$ <i 5=6> in cases today now.",
              "The rate was high q <i 5=7> in cases today now."),
             ("The dose was $\\foo x$ · high low in cases now.", "The dose was x high low in cases now."),
             ("The dose was $\\foo x$ * high low in cases now.", "The dose was x high low in cases now."),
             ("The dose was a b $\\foo x$ c in cases now.", "The dose was $b$ a x c in cases now."),
             # round 9: marks the second reader drops
             ("The dose was $\\foo x$ $x \\in S$ high low in cases now.",
              "The dose was x $x \\notin S$ high low in cases now."),
             ("The dose was $\\foo x$ $A \\cup B$ high low in cases now.",
              "The dose was x $A \\cap B$ high low in cases now."),
             ("The dose was $\\foo x$ ∪ high low in cases now.", "The dose was x ∩ high low in cases now."),
             ("The dose was $\\foo x$ ° high low in cases now.", "The dose was x high low in cases now."),
             ("The dose was $\\foo x$ $y^2$ high low in cases now.", "The dose was x $y_2$ high low in cases now."),
             ("The dose was $\\foo x$ $f'(y)$ high low in cases now.", "The dose was x $f(y)$ high low in cases now."),
             ("The dose was $\\foo x$ $\\bar{y}$ high low in cases now.", "The dose was x $y$ high low in cases now."),
             ("The dose was $\\foo x$ $\\sqrt{2}$ high low in cases now.", "The dose was x $2$ high low in cases now."),
             ("The dose was $\\foo x$ $y \\not\\in S$ high low in cases now.",
              "The dose was x $y \\in S$ high low in cases now."),
             ("The dose was $\\foo x$ high low in cases now.", "The dose was x `not` high low in cases now.")]
    for md, ox in cases:
        new, c, _, _ = M.repair(md, {}, {1: [{"type": "Text", "content": ox}]})
        assert new == md and c["left open"] == 1, md


@needs_katex
def test_round12_probes():
    # every failure of a sentence is named in its one issue
    new, c, issues, _ = M.repair("The rate $\\foo n$ and $\\goo m$ was high low in cases now.", {}, None)
    assert c["rejected by KaTeX"] == 2 and c["left open"] == 1 and len(issues) == 1
    assert "\\foo n" in issues[0]["parse"] and "\\goo m" in issues[0]["found"]
    # odd second-reader pages do not stop the run
    md = "The rate was $\\foo n$ high low in cases now."
    for oxp in ({1: None}, {1: [{"content": "The rate was $n$ high low in cases now."}], "2": []}):
        new, c, issues, _ = M.repair(md, {}, oxp)
        assert new == md and c["left open"] == 1
    # the issue points at the block that holds the failure, or nowhere: never at another block with the same words
    pages = {1: [(0, {"content": "The rate was high in the first study."})],
             2: [(0, {"content": "The rate was $\\foo n$ high low in cases now."})]}
    (i,) = M.repair(md, pages, None)[2]
    assert (i["page"], i["block"]) == (2, 0)
    pages = {1: [(0, {"content": "Figure 1 shows the x axis."})], 2: [(0, {"content": "y x."})]}
    (i,) = M.repair("$\\foo n$ x.", pages, None)[2]
    assert (i["page"], i["block"]) == (None, None)


@needs_katex
def test_where_by_the_blocks_own_failures():
    """an issue's (page, block) is the one block that holds every failure of its kind, as many as md has"""
    place = lambda md, pages: [(i["page"], i["block"]) for i in M.repair(md, pages, None)[2]]
    md = "We measured the rate $\\foo n$ in men."
    # the one block that holds the failure, wherever the paragraph's words run
    assert place(md, {1: [(0, {"content": "We measured the rate"}), (1, {"content": "$\\foo n$ in"})],
                      2: [(0, {"content": "men were studied."})]}) == [(1, 1)]
    # two blocks hold it, md once: no place (C1, round 13's B1')
    assert place(md, {1: [(0, {"content": "Earlier we measured the rate $\\foo n$"})],
                      2: [(0, {"content": "$\\foo n$ in"})]}) == [(None, None)]
    # no block holds it (a caption, kept outside 'content'): no place, not a block with the same words (B8)
    assert place(md, {4: [(0, {"content": "We measured the rate in men."})]}) == [(None, None)]
    # MinerU spaces a formula as it likes: 'c e l l' is md's 'cell' (PTA-726), and md's '$$' are the block's two
    md = "We reported two, as given in Equation $(8): $r _ { \\mathrm { cell } }$$ across features within each cell."
    pages = {12: [(12, {"content": "We reported two, as given in Equation $(8): $r _ { \\mathrm { c e l l } }$$"})],
             13: [(0, {"type": "header", "content": "bioRxiv preprint"}),
                  (1, {"content": "across features within each cell and $r$ across cells."})]}
    assert place(md, pages) == [(12, 12)]
    # a stray '$' in two blocks, md one: no place (round 20's BD1)
    md = "We report the test $ slides five."
    assert place(md, {1: [(0, {"content": "We report the test $"}), (1, {"content": "$ slides five."})]}) == [(None, None)]
    # an edit of md's beside the failure does not matter (PTA-570)
    md = "and \\~η;&lt;sup&gt;~&lt;/sup&gt; $\\vec t$ span; $\\begin{aligned} x \\end{T}$ and so on."
    assert place(md, {7: [(15, {"content": "and \\~η; $\\vec t$ span; $\\begin{aligned} x \\end{T}$ and so on."})]}) \
        == [(7, 15)]
    # an equation block's content is its display formula; md's display formula twice, the blocks' once: no place
    assert place("$$\\foo n$$", {2: [(0, {"type": "equation", "content": "\\foo{n}"})]}) == [(2, 0)]
    assert place("$$\\foo n$$\n\nText here.\n\n$$\\foo n$$", {2: [(0, {"type": "equation", "content": "\\foo{n}"})]}) \
        == [(None, None), (None, None)]
    # pages and second readings of other shapes do not stop the run
    for pages, oxp in ((None, [5]), ([(0, {})], [None]), ({}, "abc")):
        assert M.repair("The rate $\\foo n$ high low.", pages, oxp)[1]["left open"] == 1
    md = "The rate $\\foo n$ high low."
    for pages in ({1: [(0, None)]}, {1: None}, {1: [(0, "x")]}, {1: [{"content": "x"}]}, {1: [(0, {})], "2": []},
                  {"²": [(0, {"content": md})], 1: [(0, {"content": "x"})]}):
        assert M.repair(md, pages, None)[1]["left open"] == 1
    for oxp in ({1: 5}, {1: None, 2: 7}, {1: ["x", None, 3]}):
        assert M.repair(md, {}, oxp)[1]["left open"] == 1


@needs_katex
def test_one_issue_a_sentence():
    md = "We saw in Equation $(8): $r _ { \\mathrm { cell } }$$ across all cells today."
    OXR = "We saw in Equation (8): $r_{\\text{cell}}$ across all cells today."
    new, c, issues, _ = M.repair(md, {}, {1: [{"type": "Text", "content": OXR}]})
    assert new == md and c["stray dollars"] == 2 and c["left open"] == 1 and len(issues) == 1
