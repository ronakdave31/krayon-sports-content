#!/usr/bin/env python3
"""YouTube thumbnail (1280x720) for a post, built from its spec.json.

Usage:  python3 render_thumbs.py posts/<slug>/spec.json
Writes  posts/<slug>/yt-thumbnail.jpg

Layout: sport tag + kicker, the hero's main line very large, the grey line above it, the Krayon motion
dot, the logo bottom right, faint sport lines behind, and (if the post has a stat slide) that number
ghosted huge on the right as the visual hook.
Optional spec field "thumb": {"title": "...", "sub": "...", "ghost": "..."} overrides the defaults.
"""
import io, json, os, re, subprocess, sys
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R

W, H = 1280, 720
DEFS = """<defs>
 <radialGradient id="dot" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#2e5bff"/><stop offset=".5" stop-color="#ff5436"/><stop offset="1" stop-color="#7c3aed"/></radialGradient>
 <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#ff5436" stop-opacity=".28"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>
 <linearGradient id="trail" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#7c3aed" stop-opacity="0"/><stop offset="1" stop-color="#ff5436"/></linearGradient>
</defs>"""


def lines_for(sport):
    o = 'stroke="#ffffff" stroke-opacity="0.08" stroke-width="3" fill="none"'
    if sport == "football":
        return (f'<rect x="40" y="40" width="1200" height="640" {o}/><line x1="640" y1="40" x2="640" y2="680" {o}/>'
                f'<circle cx="640" cy="360" r="110" {o}/><rect x="40" y="194" width="190" height="332" {o}/>'
                f'<rect x="1050" y="194" width="190" height="332" {o}/>')
    if sport == "cricket":
        return (f'<ellipse cx="640" cy="360" rx="700" ry="420" {o}/><ellipse cx="640" cy="360" rx="380" ry="230" {o}/>'
                f'<rect x="420" y="320" width="440" height="80" {o}/>')
    if sport in ("f1", "motorsport"):
        return (f'<path d="M-20,560 C260,380 420,700 700,470 S1100,180 1320,300" {o}/>'
                f'<path d="M-20,640 C260,460 420,780 700,550 S1100,260 1320,380" {o}/>')
    return f'<circle cx="980" cy="360" r="220" {o}/><circle cx="980" cy="360" r="340" {o}/>'


def mdot(x, y, r):
    s = r / 21
    return (f'<rect x="{x-r-6*s-46*s:.1f}" y="{y-11*s:.1f}" width="{46*s:.1f}" height="{7*s:.1f}" rx="{3.5*s:.1f}" fill="url(#trail)"/>'
            f'<rect x="{x-r-6*s-34*s:.1f}" y="{y+5*s:.1f}" width="{34*s:.1f}" height="{7*s:.1f}" rx="{3.5*s:.1f}" fill="url(#trail)"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="url(#dot)"/>')


def main(spec_path):
    spec = json.load(open(spec_path))
    outdir = os.path.dirname(os.path.abspath(spec_path))
    hero = spec["slides"][0]
    th = spec.get("thumb", {})
    title = th.get("title") or hero.get("white") or hero.get("title") or hero.get("big", "")
    sub = th.get("sub", hero.get("grey", ""))
    ghost = th.get("ghost")
    if ghost is None:
        ghost = next((s["big"] for s in spec["slides"] if s["type"] == "stat" and len(str(s["big"])) <= 6), "")
    sport = spec.get("sport", "other")
    tagcol = R.COLOURS.get(sport, R.GREY)
    kick = (hero.get("kicker") or spec.get("tag", "")).upper()

    parts = [f'<rect width="{W}" height="{H}" fill="#0e0e0e"/>', lines_for(sport),
             f'<circle cx="980" cy="380" r="520" fill="url(#glow)"/>']
    if ghost:
        p, _ = R.text_path(str(ghost), R.BOLD, 420, 1250, 600, "#ffffff", -16, "end")
        parts.append(p.replace('fill="#ffffff"', 'fill="#ffffff" fill-opacity="0.06"'))
    parts.append(f'<circle cx="77" cy="78" r="8" fill="{tagcol}"/>')
    ks = 30
    while R.measure(kick, R.BOLD, ks, 5) > 1080 and ks > 18:
        ks -= 2
    parts.append(R.text_path(kick, R.BOLD, ks, 98, 89, "#ff5436", 5)[0])

    # title: as big as fits in 3 lines over ~1000 px
    maxw, size = 1060, 132
    while size > 64 and len(R.wrap(title, R.BOLD, size, maxw, -0.035 * size)) > 3:
        size -= 4
    tl = R.wrap(title, R.BOLD, size, maxw, -0.035 * size)
    lh = size * 1.02
    sub_size = 54
    sl = R.wrap(sub, R.BOLD, sub_size, maxw, -1) if sub else []
    sl = sl[:2]
    block = len(sl) * sub_size * 1.1 + (16 if sl else 0) + len(tl) * lh
    y = 130 + (520 - block) / 2 + (sub_size * 0.85 if sl else size * 0.82)
    for ln in sl:
        parts.append(R.text_path(ln, R.BOLD, sub_size, 62, y, "#8f8d86", -1)[0])
        y += sub_size * 1.1
    if sl:
        y += 16 - sub_size * 1.1 + size * 0.85 + sub_size * 0.25
    end = 62
    for i, ln in enumerate(tl):
        p, end = R.text_path(ln, R.BOLD, size, 58, y + i * lh, "#ffffff", -0.035 * size)
        parts.append(p)
    last = y + (len(tl) - 1) * lh
    r = max(16, size * 0.16)
    cx = min(end + 14 + 52 * r / 21 + r, 1240 - r)
    parts.append(mdot(cx, last - r, r))

    logo = open(os.path.join(R.HERE, "brand/krayon-sports-motion-white.svg")).read()
    inner = re.search(r"<svg[^>]*>(.*)</svg>", logo, re.S).group(1)
    inner = (inner.replace('id="kgrad"', 'id="lgrad"').replace("url(#kgrad)", "url(#lgrad)")
                  .replace('id="streak"', 'id="lstreak"').replace("url(#streak)", "url(#lstreak)"))
    sc = 0.55
    parts.append(f'<g transform="translate({1240 - 380 * sc:.1f} {680 - 245 * sc:.1f}) scale({sc})">{inner}</g>')

    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">{DEFS}{"".join(parts)}</svg>'
    png = subprocess.run(["rsvg-convert"], input=svg.encode(), capture_output=True, check=True).stdout
    out = os.path.join(outdir, "yt-thumbnail.jpg")
    Image.open(io.BytesIO(png)).convert("RGB").save(out, quality=93)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1])
