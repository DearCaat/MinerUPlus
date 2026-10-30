"""Line-break hyphens: a word split across two lines with a hyphen at the end of the first line.

Whether the hyphen belongs to the word ('long-term') or only marks the break ('pre-served' -> 'preserved') is not
visible on the page: both print a hyphen at the line end. So the question for these items is a spelling question,
not "which reading does the page print".

  breaks(page)             the split words of a page, from the text layer: (first part with hyphen, next part)
  is_linebreak(item, bk)   True when the two readings differ only by spaces and hyphens and the letters equal a
                           split word of that page (both criteria from the text layer geometry; no thresholds)
  usage(word, docs)        how the documents spell the word where it is not split: counts of 'long-term' and
                           'longterm' in mid-line words of the text layer
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
