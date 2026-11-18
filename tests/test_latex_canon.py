"""Canonical LaTeX: spellings LaTeX prints alike are the same; anything that prints other characters, another order,
another alphabet or another structure stays different."""
import pytest
from mineru_plus.check.latex_canon import canon

SAME = [
    (r"a \to b", r"a\rightarrow b"),
    (r"\gamma'^{d}", r"\gamma^ {\prime d}"),
    (r"x'", r"x^{\prime}"),
    (r"x'", r"x^\prime"),
    (r"x''", r"x^{\prime\prime}"),
    (r"x'_i", r"x^{\prime}_{i}"),
    (r"\max _ {j} \tau", r"\max_{j}\tau"),
    (r"\arg\max_{h} p", r"\operatorname{argmax}_{h} p"),
    (r"\arg\max_{h} p", r"\operatorname*{arg\,max}_h p"),
    (r"\mathrm{ROI}_{x}", r"\operatorname{ROI} _ {x}"),
    (r"\text{otherwise}", r"\mathrm{otherwise}"),
    (r"\text {Var} (Z)", r"\operatorname{Var}(Z)"),
    (r"\mathrm{2}x", r"2x"),
    (r"\mathrm{\Gamma}", r"\Gamma"),
    (r"\big( x \big)", r"(x)"),
    (r"\left[ x \right]", r"[x]"),
    (r"\left. x \right|_{0}", r"x|_0"),
    (r"M = \left( \begin{array}{c c} a & b \\ c & d \end{array} \right) \tag {5}",
     r"M=\begin{pmatrix}a&b\\c&d\end{pmatrix}\tag{5}"),
    (r"c = \left\{ \begin{array}{l l} u & , p > 1 \\ \emptyset & , \text {otherwise} \end{array} \right. \tag {9}",
     r"c=\begin{cases}u&,p>1\\\emptyset&,\text{otherwise}\end{cases}\tag{9}"),
    (r"\begin{array}{l} a \\ b \tag{2} \end{array}", r"\begin{array}{l}a\\b\end{array}\tag{2}"),
    (r"\begin{array}{l} a \\ b \\ \end{array}", r"\begin{array}{l}a\\b\end{array}"),
    (r"\begin{array}{l} a \\[2pt] b \end{array}", r"\begin{array}{l}a\\b\end{array}"),
    (r"\dfrac{a}{b}", r"\frac a b"),
    (r"p(x \mid y)", r"p(x|y)"),
    (r"a \le b", r"a\leq b"),
    (r"x_{i}", r"x_i"),
    (r"\hat{x}", r"\hat x"),
    (r"\displaystyle \sum\limits_{i} x_i", r"\sum_{i}x_i"),
    (r"a \, b \quad c", r"abc"),
    (r"\mathbf {u} _ {i}", r"\mathbf{u}_{i}"),
    (r"\mathop{\mathrm{argmax}}_h", r"\arg\max_h"),
]

DIFFER = [
    (r"\frac{ab}{c}", r"\frac{a}{bc}"),
    (r"x^{ab}", r"x^{a}b"),
    (r"x^\mathrm{ab}", r"x^{\mathrm{a}}\mathrm{b}"),
    (r"\mathbf{x}", r"x"),
    (r"\mathbf{x}", r"\boldsymbol{x}"),
    (r"\boldsymbol{\xi}", r"\xi"),
    (r"\max_j", r"max_j"),
    (r"\mathrm{x}", r"x"),
    (r"\mathrm{α}", r"α"),
    (r"\hat{x}", r"\widehat{x}"),
    (r"a, \dots, b", r"a,\ldots,b"),
    (r"\mathcal{N}", r"\boldsymbol{N}"),
    (r"\text{pot entials}", r"\text{potentials}"),
    (r"\mathbf{x}_i", r"\mathbf{x_i}"),
    (r"x \tag{1}", r"x\tag{2}"),
    (r"x \tag*{1}", r"x\tag{1}"),
    (r"a-b", r"\text{a-b}"),
    (r"x\prime", r"x'"),
    (r"x^{'d}", r"x^{\prime d}"),
    (r"\begin{array}{c|c} a & b \end{array}", r"\begin{array}{cc}a&b\end{array}"),
    (r"x^2", r"x_2"),
    (r"\frac{a}{b}", r"\frac{b}{a}"),
    (r"\sqrt{x}", r"x"),
    (r"x \tag{1}", r"x (1)"),
    (r"\bar{x}", r"\overline{x}"),
    # found by the review (11-18)
    (r"\begin{align} a \tag{1} \\ b \tag{2} \end{align}", r"\begin{align} a \tag{2} \\ b \tag{1} \end{align}"),
    (r"\begin{align} a \tag{1} \\ b \end{align}", r"\begin{align} a \\ b \tag{1} \end{align}"),
    (r"x \tag{1} \tag{2}", r"x \tag{2} \tag{1}"),
    (r"\begin{equation}x\nonumber\end{equation}", r"\begin{equation}x\end{equation}"),
    (r"\text{$x$}", r"\text{$\mathrm{x}$}"),
    (r"\textbf{-}", r"\text{-}"),
    (r"\begin{array}{c}a\\b\end{array}", "\\begin{array}{c}a¶b\\end{array}"),
    ("a\x1fb", "ab"),
    ("a　b", "ab"),
    (r"\begin {align} a \tag{1} \\ b \end{align}", r"\begin {align} a \\ b \tag{1} \end{align}"),
    (r"\begin{xalignat}{1} a \tag{1} \\ b \end{xalignat}", r"\begin{xalignat}{1} a \\ b \tag{1} \end{xalignat}"),
]

NONE = [r"x^{\prime}'", "{x", "{a}}", "\\end{array}", "\\begin{matrix} a", "\\text{$x}", "{" * 1200, "\\mathrm{" * 600 + "x" + "}" * 600]


@pytest.mark.parametrize("a,b", SAME)
def test_same(a, b):
    assert canon(a) == canon(b)


@pytest.mark.parametrize("a,b", DIFFER)
def test_differ(a, b):
    assert canon(a) != canon(b)


@pytest.mark.parametrize("s", NONE)
def test_not_printable(s):
    assert canon(s) is None


def test_empty():
    assert canon(None) == canon("") == canon(r"\displaystyle \,") == ""
