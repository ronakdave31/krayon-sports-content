#!/usr/bin/env python3
"""Krayon Sports KINETIC reel: visual news with kinetic motion graphics, built from a post's spec.json.

Usage:  python3 render_kinetic.py posts/<slug>/spec.json
Writes  posts/<slug>/reel.mp4  (1080x1920, 30 fps, H.264 + AAC) and posts/<slug>/reel-cover.jpg

What it does:
- 1 s opening hook: the sport name slams in over a sport-colour wipe.
- Every slide becomes a scene: headlines punch in word by word, big numbers count up, bars grow,
  bullets slide in on an accent bar; a sport visual (cricket pitch, football pitch, race line, rings)
  draws itself behind the text while the camera slowly pushes in.
- Whip cuts between scenes, landed on the beat; a top progress bar and a scrolling news ticker.
- Ends on the Krayon Sports end card. Original synthesised beat + whooshes + count-up ticks
  (no licensed or trending music).
Photo slides are shown as text scenes (the photo is added by hand on the feed post only).
Needs: python3, numpy, pillow, fonttools, rsvg-convert, ffmpeg.
"""
import io, json, math, os, re, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R

W, H, FPS = 1080, 1920, 30
BPM = 116
BEAT = 60 / BPM
X0, XMAX = 80, 1000
BG = (14, 14, 14)
ACCENT = "#ff5436"
SPORT_NAMES = {"cricket": "CRICKET", "football": "FOOTBALL", "f1": "FORMULA 1", "motorsport": "MOTORSPORT",
               "indian": "INDIAN SPORT", "business": "SPORTS BUSINESS", "other": "SPORT"}

DEFS = """<defs>
 <radialGradient id="dot" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#2e5bff"/><stop offset=".5" stop-color="#ff5436"/><stop offset="1" stop-color="#7c3aed"/></radialGradient>
 <linearGradient id="trail" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#7c3aed" stop-opacity="0"/><stop offset="1" stop-color="#ff5436"/></linearGradient>
 <linearGradient id="barg" x1="0" x2="1"><stop offset="0" stop-color="#7c3aed" stop-opacity=".25"/><stop offset="1" stop-color="#ff5436"/></linearGradient>
</defs>"""


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---------------- easing ----------------
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(p):
    p = clamp(p)
    return 1 - (1 - p) ** 3


def ease_in_out(p):
    p = clamp(p)
    return 4 * p ** 3 if p < .5 else 1 - (-2 * p + 2) ** 3 / 2


def back_out(p, s=1.9):
    p = clamp(p)
    return 1 + (s + 1) * (p - 1) ** 3 + s * (p - 1) ** 2


# ---------------- rasterising (cached) ----------------
_cache = {}


def svg_img(body, w, h):
    key = (body, w, h)
    if key in _cache:
        return _cache[key]
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{int(w)}" height="{int(h)}">{DEFS}{body}</svg>'
    out = subprocess.run(["rsvg-convert"], input=svg.encode(), capture_output=True, check=True).stdout
    im = Image.open(io.BytesIO(out)).convert("RGBA")
    _cache[key] = im
    return im


def text_sprite(text, font, size, fill, ls=0.0):
    """returns (img, baseline_y_in_img, width)"""
    w = R.measure(text, font, size, ls) + 24
    h = size * 1.45
    p, _ = R.text_path(text, font, size, 8, size * 1.1, fill, ls)
    return svg_img(p, w, h), size * 1.1, w - 24


def paste(frame, img, x, y, alpha=1.0, scale=1.0):
    if alpha <= 0.01 or img is None:
        return
    if abs(scale - 1) > 0.01:
        nw, nh = max(1, int(img.width * scale)), max(1, int(img.height * scale))
        img2 = img.resize((nw, nh), Image.BILINEAR)
        x -= (nw - img.width) / 2
        y -= (nh - img.height) / 2
        img = img2
    if alpha < 0.99:
        a = np.asarray(img).copy()
        a[..., 3] = (a[..., 3] * alpha).astype(np.uint8)
        img = Image.fromarray(a, "RGBA")
    frame.alpha_composite(img, (int(x), int(y)))


# ---------------- kinetic text ----------------
class Words:
    """A paragraph laid out word by word; each word punches in on its own."""

    def __init__(self, text, font, size, fill, y, start, stagger=0.07, maxw=XMAX - X0, lh=1.12, ls_em=-0.025, x=X0):
        self.items = []
        ls = ls_em * size
        lines = R.wrap(text, font, size, maxw, ls)
        space = R.measure(" ", font, size)
        k = 0
        for li, line in enumerate(lines):
            cx = x
            base = y + size * 0.82 + li * size * lh
            for wd in line.split():
                img, by, ww = text_sprite(wd, font, size, fill, ls)
                self.items.append({"img": img, "x": cx - 8, "y": base - by, "t": start + k * stagger})
                cx += ww + space
                k += 1
        self.bottom = y + size * 0.82 + (len(lines) - 1) * size * lh + size * 0.3
        self.last_end = cx - space
        self.last_base = y + size * 0.82 + (len(lines) - 1) * size * lh
        self.end_t = start + k * stagger + 0.3

    def draw(self, fr, lt, out=0.0):
        for it in self.items:
            p = (lt - it["t"]) / 0.28
            if p <= 0:
                continue
            a = clamp(p * 1.6) * (1 - out)
            sc = 1.35 - 0.35 * back_out(p)
            dy = 30 * (1 - ease_out(p)) - 40 * out
            paste(fr, it["img"], it["x"], it["y"] + dy, a, sc)


class Fade:
    """A block that slides up and fades in as one piece."""

    def __init__(self, text, font, size, fill, y, start, lh=1.3, maxw=XMAX - X0, x=X0):
        c = R.Canvas()
        last, _ = c.block(text, font, size, size * 1.05, fill, lh, maxw, x=8)
        h = last + size * 0.6
        self.img = svg_img("".join(c.parts), maxw + 30, h)
        self.x, self.y, self.t = x - 8, y, start
        self.bottom = y + h
        self.end_t = start + 0.4

    def draw(self, fr, lt, out=0.0, dx_from=0):
        p = ease_out((lt - self.t) / 0.45)
        if p <= 0:
            return
        paste(fr, self.img, self.x + dx_from * (1 - p), self.y + 40 * (1 - p) - 40 * out, p * (1 - out))


def parse_num(s):
    m = re.match(r"^(\D*?)(\d[\d,]*(?:\.\d+)?)(\D*)$", str(s).strip())
    if not m:
        return None
    pre, num, suf = m.groups()
    if re.match(r"^(st|nd|rd|th)\b", suf.strip().lower()):
        return None          # ordinals ("10th") pop in instead of counting through "2th"
    if re.fullmatch(r"(18|19|20)\d\d", num) and not pre.strip() and not suf.strip():
        return None          # years ("1968") pop in instead of counting through "1919"
    dec = len(num.split(".")[1]) if "." in num else 0
    return pre, float(num.replace(",", "")), suf, dec, "," in num


def fmt_num(v, dec, commas):
    s = f"{v:,.{dec}f}" if commas else f"{v:.{dec}f}"
    return s


class Counter:
    """A big number that counts up (or pops in when it isn't a plain number)."""

    def __init__(self, text, size, y, start, fill="#ffffff", x=X0, dur=0.9):
        self.text, self.size, self.y, self.t, self.fill, self.x, self.dur = text, size, y, start, fill, x, dur
        self.num = parse_num(text)
        img, by, w = text_sprite(text, R.BOLD, size, fill, -0.04 * size)
        self.final, self.by, self.w = img, by, w
        self.base = y + size * 0.8
        self.end_t = start + dur
        self.ticks = []
        if self.num:
            steps = 8
            self.ticks = [start + dur * (i / steps) ** 0.6 for i in range(1, steps + 1)]

    def current(self, lt):
        if not self.num:
            return self.final
        pre, v, suf, dec, commas = self.num
        p = ease_out((lt - self.t) / self.dur)
        if p >= 1:
            return self.final
        s = pre + fmt_num(v * p, dec, commas) + suf
        return text_sprite(s, R.BOLD, self.size, self.fill, -0.04 * self.size)[0]

    def draw(self, fr, lt, out=0.0):
        p = (lt - self.t) / 0.3
        if p <= 0:
            return
        sc = 1.4 - 0.4 * back_out(p) if not self.num else 1.0
        paste(fr, self.current(lt), self.x - 8, self.base - self.by - 40 * out, clamp(p * 2) * (1 - out), sc)


class DotFly:
    """The Krayon motion dot flying in to land after a headline."""

    def __init__(self, x, base, size, start):
        r = max(14, size * 0.15)
        s = r / 21
        self.r, self.t = r, start
        self.cx = min(x + 14 + (6 + 46) * s + r, XMAX - r)
        self.cy = base - r
        body = (f'<rect x="{4}" y="{r-11*s:.1f}" width="{46*s:.1f}" height="{7*s:.1f}" rx="{3.5*s:.1f}" fill="url(#trail)"/>'
                f'<rect x="{4+12*s:.1f}" y="{r+5*s:.1f}" width="{34*s:.1f}" height="{7*s:.1f}" rx="{3.5*s:.1f}" fill="url(#trail)"/>'
                f'<circle cx="{4+(52)*s+r:.1f}" cy="{r:.1f}" r="{r:.1f}" fill="url(#dot)"/>')
        self.img = svg_img(body, 4 + 52 * s + 2 * r + 4, 2 * r + 2)
        self.end_t = start + 0.45

    def draw(self, fr, lt, out=0.0):
        p = ease_out((lt - self.t) / 0.45)
        if p <= 0:
            return
        x = self.cx - (self.img.width - self.r) + (-500) * (1 - p)
        paste(fr, self.img, x, self.cy - self.r - 40 * out, clamp(p * 3) * (1 - out))


class Kicker:
    def __init__(self, text, y, start, col=ACCENT):
        self.img, by, self.w = text_sprite(text.upper(), R.BOLD, 34, col, 4)
        self.y, self.t, self.by, self.col = y, start, by, hex_rgb(col)
        self.end_t = start + 0.4

    def draw(self, fr, lt, out=0.0):
        p = ease_out((lt - self.t) / 0.4)
        if p <= 0:
            return
        d = ImageDraw.Draw(fr)
        bw = int(60 * p)
        d.rectangle([X0, self.y - 52, X0 + bw, self.y - 46], fill=self.col + (int(255 * (1 - out)),))
        # wipe reveal from the left
        img = self.img.crop((0, 0, max(1, int(self.img.width * p)), self.img.height))
        paste(fr, img, X0 - 8, self.y - self.by + 4 - 40 * out, 1 - out)


class Bars:
    def __init__(self, rows, y, start, hl, sport_col):
        self.rows, self.t, self.hl = rows, start, hl
        vmax = max(r[2] for r in rows)
        self.items = []
        bx, bmax, rh = 360, 500, 92
        for i, r in enumerate(rows):
            ry = y + i * rh
            champ = hl and i == 0
            name_img, nby, _ = text_sprite(r[0].upper(), R.BOLD, 30, "#ffffff" if champ else "#d8d6cf", 2)
            sub_img = text_sprite(r[1], R.REG, 22, R.MUTED)[0] if r[1] else None
            w = max(10, bmax * r[2] / vmax)
            label = r[3] if len(r) > 3 else str(r[2])
            self.items.append({"y": ry, "name": name_img, "nby": nby, "sub": sub_img, "w": w, "bx": bx,
                               "champ": champ, "label": label, "t": start + 0.18 * i})
        self.bottom = y + len(rows) * rh
        self.end_t = start + 0.18 * len(rows) + 0.8
        self.ticks = [it["t"] + 0.1 for it in self.items]

    def draw(self, fr, lt, out=0.0):
        d = ImageDraw.Draw(fr)
        a_out = 1 - out
        for it in self.items:
            p = ease_out((lt - it["t"]) / 0.8)
            if p <= 0:
                continue
            y = it["y"] - 40 * out
            paste(fr, it["name"], X0 - 8, y + 26 - it["nby"], clamp(p * 2) * a_out)
            if it["sub"]:
                paste(fr, it["sub"], X0 - 8, y + 34, clamp(p * 2) * a_out)
            w = it["w"] * p
            col = (255, 84, 54) if it["champ"] else (70, 70, 66)
            if w > 4:
                if it["champ"]:
                    # gradient bar
                    bar = Image.new("RGBA", (int(w), 40))
                    g = np.linspace(0, 1, int(w))[None, :, None]
                    c1, c2 = np.array([124, 58, 237]), np.array([255, 84, 54])
                    rgb = (c1 * (1 - g) + c2 * g).astype(np.uint8).repeat(40, axis=0)
                    alpha = np.full((40, int(w), 1), int(255 * a_out), np.uint8)
                    bar = Image.fromarray(np.concatenate([rgb, alpha], 2), "RGBA")
                    fr.alpha_composite(bar, (it["bx"], int(y)))
                else:
                    d.rounded_rectangle([it["bx"], y, it["bx"] + w, y + 40], 7, fill=col + (int(255 * a_out),))
            num = parse_num(it["label"])
            txt = it["label"]
            if num and p < 1:
                pre, v, suf, dec, commas = num
                txt = pre + fmt_num(v * p, dec, commas) + suf
            li = text_sprite(txt, R.BOLD, 32 if it["champ"] else 28, "#ffffff" if it["champ"] else "#d8d6cf")[0]
            paste(fr, li, it["bx"] + w + 14, y - 6, clamp(p * 2) * a_out)


# ---------------- sport visuals (line drawings that draw themselves) ----------------
def polyline_ellipse(cx, cy, rx, ry, n=120):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n + 1)]


def motif(sport):
    L = []
    if sport == "cricket":
        L.append(polyline_ellipse(540, 960, 600, 860))
        L.append(polyline_ellipse(540, 960, 330, 520))
        L.append([(470, 560), (610, 560), (610, 1360), (470, 1360), (470, 560)])
        for y in (640, 1280):
            L.append([(430, y), (650, y)])
        for y in (575, 1345):
            for x in (526, 540, 554):
                L.append([(x, y - 30), (x, y + 30)])
    elif sport == "football":
        L.append([(120, 340), (960, 340), (960, 1580), (120, 1580), (120, 340)])
        L.append([(120, 960), (960, 960)])
        L.append(polyline_ellipse(540, 960, 150, 150))
        L.append([(320, 340), (320, 560), (760, 560), (760, 340)])
        L.append([(320, 1580), (320, 1360), (760, 1360), (760, 1580)])
        L.append([(440, 340), (440, 410), (640, 410), (640, 340)])
        L.append([(440, 1580), (440, 1510), (640, 1510), (640, 1580)])
    elif sport in ("f1", "motorsport"):
        pts = []
        for i in range(161):
            t = i / 160
            x = 540 + 380 * math.sin(2 * math.pi * t) * math.cos(math.pi * t * 0.5)
            y = 300 + 1320 * t + 90 * math.sin(4 * math.pi * t)
            pts.append((x, y))
        L.append(pts)
        L.append([(p[0] + 70, p[1]) for p in pts])
        for i in range(10):
            x0 = 90 + i * 90
            L.append([(x0, 1650), (x0 + 45, 1650)])
    else:
        for r in (260, 420, 580):
            L.append(polyline_ellipse(540, 960, r, r))
    return L


def draw_motif(fr, lines, p, alpha=40):
    if p <= 0:
        return
    ov = Image.new("RGBA", fr.size)
    d = ImageDraw.Draw(ov)
    total = sum(len(l) - 1 for l in lines)
    budget = total * p
    for l in lines:
        n = len(l) - 1
        k = min(n, budget)
        budget -= n
        if k <= 0:
            break
        pts = l[: int(k) + 1]
        if int(k) < n:
            f = k - int(k)
            a, b = l[int(k)], l[int(k) + 1]
            pts = pts + [(a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f)]
        if len(pts) > 1:
            d.line(pts, fill=(255, 255, 255, alpha), width=3)
    fr.alpha_composite(ov)


# ---------------- scenes ----------------
def as_slide(s):
    if s["type"] == "photo":
        s = {k: v for k, v in s.items() if k not in ("image", "credit")}
        s["type"] = "hero"
    return s


def wordcount(*texts):
    return sum(len(str(t).split()) for t in texts if t)


class Scene:
    kind = "slide"

    def __init__(self, spec, s, idx):
        self.spec, self.s, self.idx = spec, s, idx
        self.items, self.ticks = [], []
        sport = spec.get("sport", "other")
        self.sport_col = R.COLOURS.get(sport, R.GREY)
        self.lines = motif(sport)
        t0, y = 0.15, 420
        typ = s["type"]
        if s.get("kicker"):
            self.items.append(Kicker(s["kicker"], y, t0)); y += 50; t0 += 0.15
        words = 0
        if typ == "hero":
            if s.get("grey"):
                g = Words(s["grey"], R.BOLD, 86, "#8f8d86", y, t0, 0.06); self.items.append(g)
                y, t0 = g.bottom + 10, g.end_t
                words += wordcount(s["grey"])
            wv = Words(s["white"], R.BOLD, 104, "#ffffff", y, t0, 0.08); self.items.append(wv)
            self.items.append(DotFly(wv.last_end, wv.last_base, 104, wv.end_t - 0.1))
            y, t0 = wv.bottom + 40, wv.end_t + 0.2
            words += wordcount(s["white"])
            if s.get("sub"):
                f = Fade(s["sub"], R.REG, 38, "#bdbbb4", y, t0); self.items.append(f)
                y, t0 = f.bottom + 30, t0 + 0.3
                words += wordcount(s["sub"])
            facts = s.get("facts") or []
            if facts:
                fy = max(y + 20, 1180)
                colw = (XMAX - X0) / len(facts)
                for i, (big, small) in enumerate(facts):
                    c = Counter(big, 64, fy, t0 + 0.15 * i, x=X0 + i * colw, dur=0.8)
                    self.items.append(c); self.ticks += c.ticks
                    self.items.append(Fade(small, R.REG, 28, "#9a9a93", fy + 84, t0 + 0.15 * i + 0.2, maxw=colw - 30, x=X0 + i * colw))
                words += wordcount(*[f[1] for f in facts])
                y = fy + 150
        elif typ == "stat":
            c = Counter(s["big"], 250 if len(s["big"]) <= 6 else 160, y, t0, dur=1.0)
            self.items.append(c); self.ticks += c.ticks
            if s.get("dot", True) and not c.num:
                self.items.append(DotFly(X0 + c.w, c.base, 150, t0 + 0.4))
            y = c.base + 70; t0 += 0.9
            wv = Words(s["body"], R.BOLD, 56, "#ffffff", y, t0, 0.045); self.items.append(wv)
            y, t0 = wv.bottom + 40, wv.end_t
            words += wordcount(s["body"])
            if s.get("note"):
                fn = Fade(s["note"], R.REG, 36, "#9a9a93", y, t0); self.items.append(fn); words += wordcount(s["note"])
                y = fn.bottom
        elif typ == "text":
            wv = Words(s["title"], R.BOLD, 92, "#ffffff", y, t0, 0.07); self.items.append(wv)
            y, t0 = wv.bottom + 50, wv.end_t
            words += wordcount(s["title"])
            for b in s.get("bullets", []):
                f = Fade(b, R.REG, 40, "#f2f0ea", y, t0, maxw=XMAX - X0 - 40, x=X0 + 34)
                self.items.append(f); self.items.append(BulletBar(y, f.bottom, t0, self.sport_col))
                y, t0 = f.bottom + 34, t0 + 0.45
                words += wordcount(b)
            if s.get("question"):
                wq = Words(s["question"], R.BOLD, 52, "#ffffff", y + 20, t0, 0.05); self.items.append(wq)
                words += wordcount(s["question"])
                y = wq.bottom
        elif typ == "bars":
            wv = Words(s["title"], R.BOLD, 84, "#ffffff", y, t0, 0.07); self.items.append(wv)
            y, t0 = wv.bottom + 60, wv.end_t
            b = Bars(s["rows"], y, t0, s.get("highlight_first", False), self.sport_col)
            self.items.append(b); self.ticks += b.ticks
            words += wordcount(s["title"]) + 3 * len(s["rows"])
            y = b.bottom
            if s.get("note"):
                self.items.append(Fade(s["note"].upper(), R.REG, 26, "#6e6e68", b.bottom + 30, b.end_t))
                y = b.bottom + 70
        # centre the content block in the safe area between the progress bar and the ticker
        self.dy = int(clamp((380 + 1440) / 2 - (400 + y) / 2, 0, 320))
        appear = max(getattr(i, "end_t", 0) for i in self.items)
        hold = max(1.6, words / 4.5)
        dur = clamp(appear + hold, 3.2, 8.0)
        self.dur = math.ceil(dur / BEAT) * BEAT

    def frame(self, lt, bg):
        fr = bg.copy()
        p = ease_out(lt / 1.6)
        draw_motif(fr, self.lines, p)
        out = clamp((lt - (self.dur - 0.25)) / 0.25)
        layer = Image.new("RGBA", (W, H))
        for it in self.items:
            it.draw(layer, lt, out)
        fr.alpha_composite(layer, (0, self.dy))
        return fr


class BulletBar:
    def __init__(self, y0, y1, start, col):
        self.y0, self.y1, self.t, self.col = y0 + 8, y1 - 8, start, hex_rgb(col)
        self.end_t = start + 0.4

    def draw(self, fr, lt, out=0.0):
        p = ease_out((lt - self.t) / 0.35)
        if p <= 0:
            return
        d = ImageDraw.Draw(fr)
        d.rectangle([X0, self.y0, X0 + 8, self.y0 + (self.y1 - self.y0) * p], fill=self.col + (int(255 * (1 - out)),))


class Intro:
    kind = "intro"

    def __init__(self, spec):
        sport = spec.get("sport", "other")
        self.col = hex_rgb(R.COLOURS.get(sport, ACCENT))
        name = SPORT_NAMES.get(sport, spec.get("tag", "SPORT"))
        size = 150
        while R.measure(name, R.BOLD, size, -4) > 900 and size > 80:
            size -= 6
        self.word, self.by, self.w = text_sprite(name, R.BOLD, size, "#0e0e0e", -0.03 * size)
        self.size = size
        self.label = text_sprite("KRAYON SPORTS  ·  " + spec.get("series", "").upper(), R.BOLD, 30, "#0e0e0e", 5)
        self.dur = 2 * BEAT
        self.ticks = []

    def frame(self, lt, bg):
        fr = bg.copy()
        d = ImageDraw.Draw(fr)
        p = ease_in_out(lt / 0.35)
        d.rectangle([0, 0, int(W * p), H], fill=self.col + (255,))
        q = (lt - 0.18) / 0.3
        if q > 0:
            sc = 1.6 - 0.6 * back_out(q)
            paste(fr, self.word, (W - self.word.width) / 2, 900 - self.by, clamp(q * 2), sc)
            img = self.label[0]
            paste(fr, img, (W - img.width) / 2, 1010, clamp((lt - 0.4) / 0.3))
        return fr


class EndCard:
    kind = "end"

    def __init__(self):
        svg = open(os.path.join(R.HERE, "brand/krayon-sports-motion-white.svg")).read()
        inner = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
        inner = (inner.replace('id="kgrad"', 'id="egrad"').replace("url(#kgrad)", "url(#egrad)")
                      .replace('id="streak"', 'id="estreak"').replace("url(#streak)", "url(#estreak)"))
        sc = 760 / (378 - 58)
        self.logo = svg_img(f'<g transform="translate({-58*sc+10:.1f} {-160*sc:.1f}) scale({sc:.3f})">{inner}</g>', 800, 240)
        self.follow = Words("Follow for the why behind the score.", R.BOLD, 46, "#ffffff", 1080, 0.35, 0.05, maxw=900, x=150)
        self.handle = text_sprite("@KRAYON_SPORTS", R.BOLD, 34, ACCENT, 6)
        self.dur = 6 * BEAT
        self.ticks = []

    def frame(self, lt, bg):
        fr = bg.copy()
        p = ease_out(lt / 0.6)
        paste(fr, self.logo, (W - 800) / 2 + 10 - 300 * (1 - p), 760, clamp(p * 2))
        self.follow.draw(fr, lt)
        img = self.handle[0]
        paste(fr, img, (W - img.width) / 2, 1230, clamp((lt - 0.7) / 0.3))
        return fr


# ---------------- global overlays ----------------
def make_ticker(spec):
    heads = []
    for s in spec["slides"]:
        for k in ("white", "title"):
            if s.get(k):
                heads.append(s[k])
                break
    txt = "   •   ".join(heads) + "   •   "
    img, by, w = text_sprite(txt, R.BOLD, 30, "#f2f0ea", 1)
    label = text_sprite("KRAYON SPORTS", R.BOLD, 26, "#0e0e0e", 4)[0]
    return img, label


def overlays(fr, t, total, ticker, show):
    d = ImageDraw.Draw(fr)
    # progress bar
    d.rectangle([X0, 300, XMAX, 304], fill=(42, 42, 40, 255))
    d.rectangle([X0, 300, X0 + (XMAX - X0) * clamp(t / total), 304], fill=(255, 84, 54, 255))
    if not show:
        return
    strip, label = ticker
    y = 1470
    d.rectangle([0, y, W, y + 64], fill=(24, 24, 23, 235))
    off = int((t * 140) % strip.width)
    view = Image.new("RGBA", (W, 64))
    for k in range(3):
        view.alpha_composite(strip, (k * strip.width - off + 340, int((64 - strip.height) / 2) + 2))
    fr.alpha_composite(view, (0, y))
    d.rectangle([0, y, 330, y + 64], fill=(255, 84, 54, 255))
    fr.alpha_composite(label, (24, y + int((64 - label.height) / 2) + 2))


def background():
    bg = Image.new("RGBA", (W, H), BG + (255,))
    glow = Image.new("RGBA", (W, H))
    g = ImageDraw.Draw(glow)
    g.ellipse([300, 500, 1500, 1700], fill=(255, 84, 54, 40))
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    bg.alpha_composite(glow)
    return bg


# ---------------- audio ----------------
def soundtrack(scenes, cuts, ticks, total, path, sr=44100):
    n = int(total * sr) + sr
    mix = np.zeros(n)
    rng = np.random.default_rng(11)

    def add(sig, at):
        i = int(at * sr)
        if i < 0 or i >= n:
            return
        j = min(n, i + len(sig))
        mix[i:j] += sig[: j - i]

    tt = lambda d: np.arange(int(d * sr)) / sr
    kt = tt(0.3)
    kick = np.sin(2 * np.pi * (48 * kt + 90 * (1 - np.exp(-kt * 28)) / 28)) * np.exp(-kt * 10)
    ht = tt(0.05)
    hat = np.diff(rng.standard_normal(len(ht) + 1)) * np.exp(-ht * 100) * 0.16
    st = tt(0.18)
    snare = (rng.standard_normal(len(st)) * 0.5 + np.sin(2 * np.pi * 190 * st)) * np.exp(-st * 22) * 0.35
    roots = [55.0, 43.65, 65.41, 49.0]
    beats = int(total / BEAT) + 1
    for b in range(beats):
        at = b * BEAT
        add(kick * (1.0 if b % 4 == 0 else 0.75), at)
        add(hat, at + BEAT / 2)
        if b % 2 == 1:
            add(snare, at)
        if b % 4 == 0:
            f = roots[(b // 4) % 4]
            bt = tt(BEAT * 4)
            env = np.minimum(1, bt / 0.03) * np.exp(-bt * 0.5)
            add((np.sin(2 * np.pi * f * bt) + 0.35 * np.sin(2 * np.pi * 2 * f * bt)) * env * 0.33, at)
            pad = sum(np.sin(2 * np.pi * f * m * bt + ph) for m, ph in ((4, 0), (6, 1.3), (8, 2.1)))
            add(pad * np.minimum(1, bt / 0.8) * np.minimum(1, (BEAT * 4 - bt) / 0.5) * 0.03, at)
    # whoosh into every cut
    for c in cuts:
        wt = tt(0.4)
        nz = np.convolve(rng.standard_normal(len(wt)), np.ones(20) / 20, mode="same")
        add(nz * (wt / 0.4) ** 2 * 0.6, c - 0.4)
    # ticks under count-ups
    tk = tt(0.03)
    tick = np.sin(2 * np.pi * 2400 * tk) * np.exp(-tk * 160) * 0.12
    for t in ticks:
        add(tick, t)
    fade = int(0.3 * sr)
    mix[:fade] *= np.linspace(0, 1, fade)
    end = int(total * sr)
    mix[end - int(0.6 * sr):end] *= np.linspace(1, 0, int(0.6 * sr))
    mix = np.tanh(mix[:end] * 1.3)
    mix *= 0.8 / max(1e-9, np.max(np.abs(mix)))
    stx = np.stack([mix, mix], axis=1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((stx * 32767).astype(np.int16).tobytes())


# ---------------- main ----------------
def whip(a, b, p):
    """A slides out left as B slides in from the right, with horizontal motion blur."""
    e = ease_in_out(p)
    off = int(W * e)
    fr = Image.new("RGB", (W, H), BG)
    fr.paste(a, (-off, 0))
    fr.paste(b, (W - off, 0))
    if 0.08 < p < 0.92:
        arr = np.asarray(fr).astype(np.float32)
        acc = np.zeros_like(arr)
        k = 9
        for i in range(k):
            acc += np.roll(arr, (i - k // 2) * 14, axis=1)
        fr = Image.fromarray((acc / k).astype(np.uint8))
    return fr


def main(spec_path):
    spec = json.load(open(spec_path))
    outdir = os.path.dirname(os.path.abspath(spec_path))
    scenes = [Intro(spec)] + [Scene(spec, as_slide(s), i) for i, s in enumerate(spec["slides"])] + [EndCard()]
    starts, t = [], 0.0
    for sc in scenes:
        starts.append(t); t += sc.dur
    total = t
    cuts = starts[1:]
    ticks = []
    for sc, st in zip(scenes, starts):
        ticks += [st + x for x in sc.ticks]
    bg = background()
    ticker = make_ticker(spec)
    wav = os.path.join(outdir, "reel-audio.wav")
    soundtrack(scenes, cuts, ticks, total, wav)
    mp4 = os.path.join(outdir, "reel.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", mp4]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    WHIP = 0.3
    cover_t = starts[1] + min(scenes[1].dur - 0.4, 2.8)
    for f in range(int(total * FPS)):
        t = f / FPS
        i = max(k for k, s in enumerate(starts) if s <= t)
        sc, lt = scenes[i], t - starts[i]
        # whip window around each cut (except into the intro)
        nxt = i + 1 < len(scenes) and (starts[i + 1] - t) < WHIP / 2
        prv = i > 0 and lt < WHIP / 2 and scenes[i - 1].kind != "intro" or (i == 1 and lt < WHIP / 2)
        if nxt:
            a = sc.frame(lt, bg)
            b = scenes[i + 1].frame(0.0, bg)
            p = 0.5 - (starts[i + 1] - t) / WHIP
            fr = whip(a.convert("RGB"), b.convert("RGB"), p)
            fr = fr.convert("RGBA")
        elif prv:
            a = scenes[i - 1].frame(scenes[i - 1].dur, bg)
            b = sc.frame(lt, bg)
            p = 0.5 + lt / WHIP
            fr = whip(a.convert("RGB"), b.convert("RGB"), p).convert("RGBA")
        else:
            fr = sc.frame(lt, bg)
        overlays(fr, t, total, ticker, sc.kind == "slide")
        rgb = fr.convert("RGB")
        ff.stdin.write(rgb.tobytes())
        if f == int(cover_t * FPS):
            rgb.save(os.path.join(outdir, "reel-cover.jpg"), quality=90)
    ff.stdin.close(); ff.wait()
    os.remove(wav)
    if ff.returncode:
        sys.exit("ffmpeg failed")
    print(f"{mp4}  ({total:.1f} s: intro + {len(scenes)-2} scenes + end card)")


if __name__ == "__main__":
    main(sys.argv[1])
