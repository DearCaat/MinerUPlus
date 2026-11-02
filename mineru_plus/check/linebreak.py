"""Line-break hyphens: a word split across two lines with a hyphen at the end of the first line.

Whether the hyphen belongs to the word ('long-term') or only marks the break ('pre-served' -> 'preserved') is not
visible on the page: both print a hyphen at the line end. So the question for these items is a spelling question,
not "which reading does the page print".

  breaks(page)             the split words of a page, from the text layer: (first part with hyphen, next part)
  is_linebreak(item, bk)   True when the two readings differ only by spaces and hyphens and the letters equal a
                           split word of that page (both criteria from the text layer geometry; no thresholds)
  usage(word, docs)        how the documents spell the word where it is not split: counts of 'long-term' and
                           'longterm' in mid-line words of the text layer
  source_splits(...)       split words both readers spell alike that a source document spells the other way
"""
import re
from .. import layer as LY

HY = ("-", "­", "‐", "‑")
EDGE = re.compile(r"^[^\w]+|[^\w]+$")
DASH = re.compile("[-\u00ad\u2010\u2011\u2012\u2013\u2014]")


def breaks(page):
    words = LY.words(page)
    lines = {}
    for w in words:
        lines.setdefault((w[5], w[6]), []).append(w)
    keys = sorted(lines)
    out = []
    for k, nk in zip(keys, keys[1:]):
        last, first = lines[k][-1][4], lines[nk][0][4]
        if last.endswith(HY) and len(last) > 1:
            out.append((EDGE.sub("", last[:-1]), EDGE.sub("", first)))
    return out


def letters(s):
    return re.sub("[\\s" + re.escape("".join(HY)) + "]", "", s)


def is_linebreak(item, bk):
    """(left, right, full left word) when the readings differ only in one hyphen and that hyphen sits at a line
    break; left may be the last segment of a hyphenated first part, the full word is for the usage lookup"""
    a, b = letters(item["primary"]), letters(item["oxr"])
    if a != b:
        return None
    ha, hb = item["primary"].replace(" ", ""), item["oxr"].replace(" ", "")
    hyph = [h for h in (ha, hb) if any(c in h for c in HY)]
    if len(hyph) != 1:
        return None
    h = hyph[0]
    for c in HY[1:]:
        h = h.replace(c, "-")
    for left, right in bk:
        if not (left and right):
            continue
        # 'leave-one-patient-|out', 'results—Onco-|type', 'sub-|typing-based': the readings may hold only the
        # segment next to the break on either side
        segl, segr = DASH.split(left)[-1], DASH.split(right)[0]
        for l, r in ((left, right), (segl, right), (left, segr), (segl, segr)):
            if l and r and (l + "-" + r) in h:
                return l, r, left
    return None


def midline_index(docs):
    """lower-cased mid-line words of the documents' text layers with their counts (words split at a line end excluded)"""
    idx = {}
    for doc in docs:
        for i in range(doc.page_count):
            pg = LY.page(doc, i)
            lines = {}
            for w in LY.words(pg):
                lines.setdefault((w[5], w[6]), []).append(w)
            for ws in lines.values():
                for i, w in enumerate(ws):
                    if i == len(ws) - 1 and w[4].endswith(HY):
                        continue
                    t = EDGE.sub("", w[4]).lower()
                    idx[t] = idx.get(t, 0) + 1
    return idx


def usage(left, right, idx):
    """how the indexed documents spell the split word where it is not split"""
    return {"hyphen": idx.get((left + "-" + right).lower(), 0), "joined": idx.get((left + right).lower(), 0)}


SKIP_TYPES = {"image", "chart", "equation", "interline_equation"}


def source_splits(pdf_path, mdir, subs, src):
    """Split words of the text layer that both readers spell alike while the source document spells them the other
    way: no disagreement brings them to the line-break route (11-02: 'under-|represented', 'under-|specified'
    joined by both readers, the JATS or arXiv HTML source has the hyphen). Each becomes a line-break item with the
    source's spelling as OXR's, where the page's blocks hold the word once and no item of the page already covers it;
    settle() takes the source's spelling for it."""
    import pymupdf
    from ..readers import mineru as MR
    pdf = pymupdf.open(pdf_path)
    A = MR.pages(mdir)
    covered = {}
    for x in subs:
        covered.setdefault(x["page"], []).append(letters(x.get("primary") or "") + "|" + letters(x.get("oxr") or ""))
    out = []
    for pg_no in sorted(A):
        if not 0 < pg_no <= pdf.page_count:
            continue
        seen = set()
        for left, right in breaks(LY.page(pdf, pg_no - 1)):
            right = re.match(r"[^\W\d_]*", right or "").group()     # a reference mark may follow ('data-|set3')
            if not (left and right) or not left.isalpha() or (left, right) in seen:
                continue
            seen.add((left, right))
            if any(left + right in c for c in covered.get(pg_no, [])):
                continue
            pat = re.compile(r"(?<![^\W_])" + re.escape(left) + r"(\s*[-­‐‑]\s*)?" + re.escape(right)
                             + r"(?![^\W_])")
            hits = []
            for uid, typ, part in MR.units(A[pg_no]):
                raw = part.get("content")
                if typ in SKIP_TYPES or not isinstance(raw, str):
                    continue
                hits += [(uid, typ, part, raw, m) for m in pat.finditer(raw)]
            if len(hits) != 1:
                continue                                         # not in the page's text, or more than once
            uid, typ, part, raw, m = hits[0]
            prim = m.group()
            other = left + right if m.group(1) else left + "-" + right
            lo, hi = m.span()
            lft, rgt = raw[:lo].split()[-8:], raw[hi:].split()[:8]
            if src.hyphen(lft, prim, other, rgt) != 1:
                continue                                         # the source writes the primary's spelling, or neither
            out.append({"kind": "content", "page": pg_no, "blocks": [uid], "bbox": part.get("bbox"), "block_type": typ,
                        "pos_in_block": round(lo / max(1, len(raw)), 3), "primary": prim, "oxr": other,
                        "primary_text": prim, "oxr_text": other, "raw_span": [lo, hi], "primary_toks": [prim],
                        "oxr_toks": [other], "left": lft, "right": rgt,
                        "context": " ".join(lft) + " [...] " + " ".join(rgt),
                        "source": "a line-break word both readers spell alike, the source document the other way"})
    return out
