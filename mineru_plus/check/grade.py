"""A suggested grade for each issue: how much a real error there would cost the paper's readers downstream (11-18,
文浩: 「mineru_plus 只给后果分级，在 issues.json 里标出来并写明依据；不做"可能性"分级」). mineru_plus only reports the
grade; how an issue is handled is not its business.

A grade says what is at stake, not how likely the issue is a real error. On the paper line's 448 settled issues no
observable feature told 'edit' from 'no change': edit rates ran from 10 to 30% across block types and character
classes, differences of punctuation or spaces only were edits more often than the rest (28%, words split by a space),
and only side notes had none (0 of 38). A low grade is therefore no sign that nothing is wrong.

  high    a table, or a number in the text: what results and methods are read from
  medium  other text, captions, lists and formulas, and issues that are not placed in a block
  low     page headers and footers, page numbers and side notes
The grade is read from the issue's kind, its block's type and the characters the two readings differ in; nothing is
guessed, and where neither tells, the grade is medium."""
import difflib

MARGIN = {"header", "footer", "page_number", "aside_text"}
TABLE = {"table"}
LOW_KINDS = {"margin text differs from the text layer"}
HIGH_KINDS = {"table", "second reader failed"}


def _type(issue, types):
    if issue.get("block_type"):
        return issue["block_type"]
    b = issue.get("block")
    if isinstance(b, int):
        return types.get((issue.get("page"), b))
    if isinstance(b, str) and b.split(".")[0].isdigit():     # a caption or footnote nested in block i
        return types.get((issue.get("page"), int(b.split(".")[0])))
    return None


def _differing(issue):
    """the characters the two readings of the issue differ in, or the issue's only text where there is one"""
    a = next((issue[k] for k in ("primary", "parse", "mineru") if isinstance(issue.get(k), str)), None)
    b = next((issue[k] for k in ("oxr", "layer") if isinstance(issue.get(k), str)), None)
    if a is not None and b is not None:
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        return "".join(a[i1:i2] + b[j1:j2] for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")
    return next((v for v in (a, b, issue.get("text")) if isinstance(v, str)), "")


def grade(issue, types):
    kind, typ = issue.get("kind"), _type(issue, types)
    if kind in HIGH_KINDS or typ in TABLE:
        return "high", f"{'a table' if kind == 'table' or typ in TABLE else kind}"
    if kind in LOW_KINDS or typ in MARGIN:
        return "low", f"a page header, footer, page number or side note ({typ or kind})"
    if kind != "display equation" and any(c.isdigit() for c in _differing(issue)):
        return "high", "a number in the text"
    return "medium", f"{typ or 'unplaced'} text" if kind != "display equation" else "a formula"


def apply(issues, pages):
    """pages: the primary reader's {page: [(block index, block), ...]}"""
    types = {(pg, bi): b.get("type") for pg, bs in pages.items() for bi, b in bs}
    for i in issues:
        level, basis = grade(i, types)
        i["grade"] = {"level": level, "basis": basis}
    return issues
