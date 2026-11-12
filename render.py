#!/usr/bin/env python3
"""Krayon Sports post renderer.

Usage:  python3 render.py posts/<slug>/spec.json
Writes  posts/<slug>/slide-1.jpg ... (1080x1350 JPEG, Instagram 4:5) and preview.png

All text is converted to vector outlines (fontTools), so output does not depend on
installed fonts. Only needs: python3, fonttools, pillow, rsvg-convert.

Spec format (JSON):
{
  "slug": "2026-11-12-ipl-retentions",          # folder name, also used in URLs
  "tag": "CRICKET",                             # sport label, top right
  "sport": "cricket",                           # colour key: cricket|football|f1|motorsport|indian|business|other
  "series": "05 / BREAKING",                    # running number + format
  "slides": [ { "type": "hero" | "stat" | "text" | "bars", ... } ],   # 1 = single post, 2-10 = carousel
  "concept": "...", "caption": "...", "sources": ["url", ...]   # not rendered; kept with the post
}
Slide types:
  hero:  kicker?, grey (muted line), white (main line), sub?, facts? [[big, small], [big, small]]
  stat:  kicker, big ("74%"), body, note?
  text:  kicker, title, bullets? [..], question?, footnote?
  bars:  kicker, title, rows [[name, subtitle, value_number, value_label?]], highlight_first? (bool), bracket? {from, to, label, sub}, note?
"""
import json, os, re, subprocess, sys
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen

HERE = os.path.dirname(os.path.abspath(__file__))
BOLD = TTFont(os.path.join(HERE, "fonts/LiberationSans-Bold.ttf"))
REG = TTFont(os.path.join(HERE, "fonts/LiberationSans-Regular.ttf"))
W, H = 1080, 1350
X0, XMAX = 80, 1000            # content column
CONTENT_BOTTOM = 1140
COLOURS = {"cricket": "#2e5bff", "football": "#22c55e", "f1": "#ff3b3b", "motorsport": "#ff3b3b",
           "indian": "#ff5436", "business": "#f5b301", "other": "#9a9a93"}
ACCENT = "#ff5436"
WHITE, OFF, GREY, MUTED, DIM, LINE = "#ffffff", "#f2f0ea", "#9a9a93", "#6e6e68", "#3a3a37", "#2a2a28"


# ---------------- text as outlines ----------------
def _glyphs(font):
    return font.getGlyphSet(), font.getBestCmap(), font["head"].unitsPerEm


def measure(text, font, size, ls=0.0):
    gs, cmap, upm = _glyphs(font)
    w = 0.0
    for ch in text:
        g = cmap.get(ord(ch)) or cmap.get(ord("?"))
        w += gs[g].width * size / upm + ls
    return w - (ls if text else 0)


def text_path(text, font, size, x, y, fill, ls=0.0, anchor="start"):
    gs, cmap, upm = _glyphs(font)
    s = size / upm
    if anchor != "start":
        tw = measure(text, font, size, ls)
        x = x - tw if anchor == "end" else x - tw / 2
    pen = SVGPathPen(gs)
    cx = x
    for ch in text:
        g = cmap.get(ord(ch)) or cmap.get(ord("?"))
        gs[g].draw(TransformPen(pen, (s, 0, 0, -s, cx, y)))
        cx += gs[g].width * s + ls
    d = pen.getCommands()
    return (f'<path d="{d}" fill="{fill}"/>' if d else ""), cx - ls


def wrap(text, font, size, maxw, ls=0.0):
    out = []
    for para in str(text).split("\n"):
        words, line = para.split(), ""
        for wd in words:
            t = (line + " " + wd).strip()
            if measure(t, font, size, ls) <= maxw or not line:
                line = t
            else:
                out.append(line); line = wd
        out.append(line)
    return out


class Canvas:
    def __init__(self):
        self.parts = []

    def add(self, s):
        self.parts.append(s)

    def text(self, text, font, size, x, y, fill, ls=0.0, anchor="start"):
        p, end = text_path(text, font, size, x, y, fill, ls, anchor)
        self.add(p)
        return end

    def block(self, text, font, size, y, fill, lh=1.25, maxw=XMAX - X0, ls=0.0, x=X0):
        """wrapped paragraph; y = first baseline; returns (next_y_after_block, last_line_end_x)"""
        end = x
        lines = wrap(text, font, size, maxw, ls)
        for i, ln in enumerate(lines):
            end = self.text(ln, font, size, x, y + i * size * lh, fill, ls)
        return y + (len(lines) - 1) * size * lh, end

    def fit_block(self, text, font, size, minsize, maxlines, y, fill, lh=1.08, ls_em=-0.03, maxw=XMAX - X0):
        """shrink headline until it fits maxlines; returns (last_baseline, end_x, size)"""
        s = size
        while s > minsize and len(wrap(text, font, s, maxw, ls_em * s)) > maxlines:
            s -= 4
        last, end = self.block(text, font, s, y + s * 0.8, fill, lh, maxw, ls_em * s, x=X0 - 8)
        return last, end, s


def motion_dot(x, y, r):
    s = r / 21
    return (f'<rect x="{x-r-6*s-46*s:.1f}" y="{y-11*s:.1f}" width="{46*s:.1f}" height="{7*s:.1f}" rx="{3.5*s:.1f}" fill="url(#trail)"/>'
            f'<rect x="{x-r-6*s-34*s:.1f}" y="{y+5*s:.1f}" width="{34*s:.1f}" height="{7*s:.1f}" rx="{3.5*s:.1f}" fill="url(#trail)"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="url(#dot)"/>')


def dot_after(c, end_x, baseline, size):
    r = max(14, size * 0.15)
    streak = (6 + 46) * r / 21
    cx = min(end_x + 14 + streak + r, XMAX - r)
    c.add(motion_dot(cx, baseline - r, r))


# ---------------- slide types ----------------
def kicker(c, text, y):
    c.text(text.upper(), BOLD, 30, X0, y, ACCENT, ls=4)
    return y + 40


def slide_hero(c, s):
    y = 300
    if s.get("kicker"):
        y = kicker(c, s["kicker"], 300) + 10
    if s.get("grey"):
        last, _, size = c.fit_block(s["grey"], BOLD, 100, 64, 2, y, MUTED)
        y = last + size * 0.3
    last, end, size = c.fit_block(s["white"], BOLD, 120 if not s.get("grey") else 100, 64, 3, y, WHITE)
    dot_after(c, end, last, size)
    y = last + 80
    if s.get("sub"):
        y, _ = c.block(s["sub"], REG, 32, y, GREY, 1.3)
        y += 40
    facts = s.get("facts") or []
    if facts:
        fy = max(y + 30, 1000)
        c.add(f'<rect x="{X0}" y="{fy-70}" width="{XMAX-X0}" height="2" fill="{LINE}"/>')
        colw = (XMAX - X0) / len(facts)
        for i, (big, small) in enumerate(facts):
            fx = X0 + i * colw
            c.text(big, BOLD, 42, fx, fy, WHITE)
            c.block(small, REG, 28, fy + 44, GREY, 1.25, maxw=colw - 30, x=fx)
        y = fy + 90
    return y


def slide_stat(c, s):
    y = kicker(c, s.get("kicker", ""), 300) if s.get("kicker") else 300
    size = 220
    while size > 90 and measure(s["big"], BOLD, size, -0.04 * size) > XMAX - X0:
        size -= 6
    end = c.text(s["big"], BOLD, size, X0 - 8, y + size * 0.78, WHITE, ls=-0.04 * size)
    if s.get("dot", True):
        dot_after(c, end, y + size * 0.78, size * 0.6)
    y = y + size * 0.78 + 90
    y, _ = c.block(s["body"], BOLD, 50, y, WHITE, 1.22, ls=-1)
    y += 90
    if s.get("note"):
        y, _ = c.block(s["note"], REG, 36, y, GREY, 1.35)
    return y


def slide_text(c, s):
    y = kicker(c, s["kicker"], 300) if s.get("kicker") else 300
    last, end, size = c.fit_block(s["title"], BOLD, 92, 60, 3, y, WHITE)
    y = last + 90
    for b in s.get("bullets", []):
        y, _ = c.block("• " + b, REG, 36, y, OFF, 1.3)
        y += 56
    if s.get("question"):
        y += 30
        y, _ = c.block(s["question"], BOLD, 46, y, WHITE, 1.22)
        y += 50
    if s.get("footnote"):
        c.block(s["footnote"], REG, 22, max(y + 10, 1110), MUTED, 1.3)
    return y


def slide_bars(c, s):
    y = kicker(c, s["kicker"], 280) if s.get("kicker") else 280
    last, _, size = c.fit_block(s["title"], BOLD, 84, 56, 2, y, WHITE)
    y = last + 60
    if s.get("sub"):
        y, _ = c.block(s["sub"], REG, 30, y + 10, GREY, 1.3)
        y += 30
    rows = s["rows"]
    vmax = max(r[2] for r in rows)
    bx, bmax, rh = 330, 520, 66
    hl = s.get("highlight_first", False)
    ys = []
    for i, r in enumerate(rows):
        name, sub, val = r[0], r[1], r[2]
        label = r[3] if len(r) > 3 else str(val)
        ry = y + i * rh + (24 if hl and i else 0)
        ys.append(ry)
        w = max(8, bmax * val / vmax)
        champ = hl and i == 0
        c.text(name.upper(), BOLD, 26, X0, ry + 22, WHITE if champ else "#d8d6cf", ls=2)
        if sub:
            c.text(sub, REG, 20, X0, ry + 50, MUTED)
        if champ:
            c.add(f'<rect x="{bx}" y="{ry}" width="{w-30:.0f}" height="34" rx="6" fill="url(#barg)"/>'
                  f'<circle cx="{bx+w-10:.0f}" cy="{ry+17}" r="19" fill="url(#dot)"/>')
            c.text(label, BOLD, 30, bx + w + 22, ry + 28, WHITE)
        else:
            c.add(f'<rect x="{bx}" y="{ry}" width="{w:.0f}" height="34" rx="6" fill="{DIM}"/>')
            c.text(label, BOLD, 26, bx + w + 16, ry + 27, "#d8d6cf")
    br = s.get("bracket")
    if br:
        top, bot = ys[br["from"]] - 6, ys[br["to"]] + 40
        col = COLOURS.get(c.sport, ACCENT)
        c.add(f'<path d="M{XMAX-4},{top} H{XMAX+10} V{bot} H{XMAX-4}" fill="none" stroke="{col}" stroke-width="3"/>')
        c.text(br["label"], BOLD, 30, XMAX - 10, (top + bot) / 2 - 4, col, anchor="end")
        if br.get("sub"):
            c.text(br["sub"], REG, 20, XMAX - 10, (top + bot) / 2 + 26, GREY, anchor="end")
    y = ys[-1] + 80
    if s.get("note"):
        c.text(s["note"].upper(), REG, 24, X0, max(y + 20, 1100), MUTED, ls=4)
    return y


TYPES = {"hero": slide_hero, "stat": slide_stat, "text": slide_text, "bars": slide_bars}


# ---------------- frame ----------------
def logo_group():
    svg = open(os.path.join(HERE, "brand/krayon-sports-motion-white.svg")).read()
    inner = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
    inner = (inner.replace('id="kgrad"', 'id="lgrad"').replace("url(#kgrad)", "url(#lgrad)")
                  .replace('id="streak"', 'id="lstreak"').replace("url(#streak)", "url(#lstreak)"))
    return f'<g transform="translate(28 1060) scale(0.95)">{inner}</g>'


GLOWS = [(900, 760), (880, 450), (900, 820), (860, 520), (900, 900), (880, 620)]


def render_slide(spec, i, n):
    s = spec["slides"][i]
    c = Canvas()
    c.sport = spec.get("sport", "other")
    tagcol = COLOURS.get(c.sport, GREY)
    gx, gy = GLOWS[i % len(GLOWS)]
    # header
    c.text("KRAYON SPORTS", BOLD, 26, X0, 128, OFF, ls=6)
    tag = spec.get("tag", "").upper()
    tw = measure(tag, REG, 22, 5)
    c.add(f'<circle cx="{XMAX-tw-24:.0f}" cy="105" r="7" fill="{tagcol}"/>')
    c.text(tag, REG, 22, XMAX, 112, MUTED, ls=5, anchor="end")
    c.text(spec.get("series", "").upper(), REG, 22, XMAX, 140, MUTED, ls=5, anchor="end")
    c.add(f'<rect x="{X0}" y="170" width="{XMAX-X0}" height="2" fill="{LINE}"/>')
    bottom = TYPES[s["type"]](c, s)
    if bottom > CONTENT_BOTTOM:
        print(f"WARNING slide {i+1}: content runs to y={bottom:.0f} (limit {CONTENT_BOTTOM}) - shorten text", file=sys.stderr)
    # footer
    c.add(f'<rect x="{X0}" y="1170" width="{XMAX-X0}" height="2" fill="{LINE}"/>')
    if i == n - 1:
        c.add(logo_group())
        c.text("FOLLOW  →", BOLD, 28, XMAX, 1258, OFF, ls=4, anchor="end")
    else:
        c.text(f"{i+1:02d} / {n:02d}", REG, 26, X0, 1258, MUTED, ls=5)
        c.text("SWIPE  →", BOLD, 26, XMAX, 1258, OFF, ls=5, anchor="end")
    body = "\n".join(c.parts)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">
<defs>
 <radialGradient id="dot" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#2e5bff"/><stop offset=".5" stop-color="#ff5436"/><stop offset="1" stop-color="#7c3aed"/></radialGradient>
 <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#ff5436" stop-opacity=".22"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>
 <linearGradient id="trail" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#7c3aed" stop-opacity="0"/><stop offset="1" stop-color="#ff5436"/></linearGradient>
 <linearGradient id="barg" x1="0" x2="1"><stop offset="0" stop-color="#7c3aed" stop-opacity=".15"/><stop offset="1" stop-color="#ff5436"/></linearGradient>
</defs>
<rect width="{W}" height="{H}" fill="#0e0e0e"/>
<circle cx="{gx}" cy="{gy}" r="500" fill="url(#glow)"/>
{body}
</svg>"""


def main(spec_path):
    spec = json.load(open(spec_path))
    outdir = os.path.dirname(os.path.abspath(spec_path))
    n = len(spec["slides"])
    assert 1 <= n <= 10, "1 to 10 slides"
    from PIL import Image
    files = []
    for i in range(n):
        svg = render_slide(spec, i, n)
        sp = os.path.join(outdir, f"slide-{i+1}.svg")
        open(sp, "w").write(svg)
        png = sp.replace(".svg", ".png")
        subprocess.run(["rsvg-convert", sp, "-o", png], check=True)
        jpg = sp.replace(".svg", ".jpg")
        Image.open(png).convert("RGB").save(jpg, quality=92)
        os.remove(png); os.remove(sp)
        files.append(jpg)
    # contact sheet for previews
    ims = [Image.open(f).resize((432, 540)) for f in files]
    sheet = Image.new("RGB", (432 * len(ims), 540), "#0e0e0e")
    for k, im in enumerate(ims):
        sheet.paste(im, (k * 432, 0))
    sheet.save(os.path.join(outdir, "preview.jpg"), quality=85)
    print("\n".join(files))


if __name__ == "__main__":
    main(sys.argv[1])
