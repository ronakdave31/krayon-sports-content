#!/usr/bin/env python3
"""Krayon Sports reel renderer: turns the same spec.json used for the feed post into a 9:16 Reel.

Usage:  python3 render_reel.py posts/<slug>/spec.json
Writes  posts/<slug>/reel.mp4      1080x1920, 30 fps, H.264 + AAC, ~10-30 s
        posts/<slug>/reel-cover.jpg first full frame of the reel (cover image)

Each slide becomes a scene. Its pieces (kicker, headline, numbers, bullets, rows...) slide up and fade in
one after another, hold long enough to read, then move off before the next scene. The reel ends on a
Krayon Sports end card. The soundtrack is an original beat synthesised here (no licensed or trending
music), so it is safe to publish.
Photo slides are shown in the text layout (no photo) because the photo is added by hand.
Needs: python3, numpy, pillow, fonttools, rsvg-convert, ffmpeg.
"""
import io, json, math, os, re, subprocess, sys, wave
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as R

W, H = 1080, 1920
TOP = 285                 # the 1080x1350 post layout sits at this y inside the reel
FPS = 30
BPM = 112
BEAT = 60 / BPM

DEFS = """<defs>
 <radialGradient id="dot" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#2e5bff"/><stop offset=".5" stop-color="#ff5436"/><stop offset="1" stop-color="#7c3aed"/></radialGradient>
 <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#ff5436" stop-opacity=".22"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>
 <linearGradient id="trail" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#7c3aed" stop-opacity="0"/><stop offset="1" stop-color="#ff5436"/></linearGradient>
 <linearGradient id="barg" x1="0" x2="1"><stop offset="0" stop-color="#7c3aed" stop-opacity=".15"/><stop offset="1" stop-color="#ff5436"/></linearGradient>
</defs>"""


# ---------------- rasterising ----------------
def svg_png(body, w=W, h=H):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">{DEFS}{body}</svg>'
    out = subprocess.run(["rsvg-convert"], input=svg.encode(), capture_output=True, check=True).stdout
    return Image.open(io.BytesIO(out)).convert("RGBA")


def sprite(body):
    """Render a layer at full reel size, then crop to its content so per-frame compositing stays fast."""
    im = svg_png(f'<g transform="translate(0 {TOP})">{body}</g>')
    box = im.getbbox()
    if not box:
        return None
    return {"img": im.crop(box), "x": box[0], "y": box[1]}


def background(gx, gy):
    return svg_png(f'<rect width="{W}" height="{H}" fill="#0e0e0e"/>'
                   f'<circle cx="{gx}" cy="{gy + TOP}" r="620" fill="url(#glow)"/>').convert("RGB")


# ---------------- building scenes from the spec ----------------
def as_reel_slide(s):
    if s["type"] == "photo":           # photo goes in by hand; reels use the text layout
        s = {k: v for k, v in s.items() if k not in ("image", "credit")}
        s["type"] = "hero"
    return s


def words_in(s):
    txt = " ".join(str(v) for k, v in s.items() if k not in ("type", "image", "rows", "facts", "bracket", "highlight_first", "dot"))
    for r in s.get("rows", []):
        txt += " " + " ".join(str(x) for x in r[:2])
    for f in s.get("facts", []) or []:
        txt += " " + " ".join(f)
    return len(txt.split())


def scene_layers(spec, s):
    c = R.Canvas()
    c.sport = spec.get("sport", "other")
    R.TYPES[s["type"]](c, s)
    marks = c.marks or [(0, "content")]
    layers = []
    for k, (start, name) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(c.parts)
        body = "".join(c.parts[start:end])
        if body.strip():
            sp = sprite(body)
            if sp:
                sp["name"] = name
                layers.append(sp)
    return layers


def header_layer(spec):
    c = R.Canvas()
    tagcol = R.COLOURS.get(spec.get("sport", "other"), R.GREY)
    c.text("KRAYON SPORTS", R.BOLD, 26, R.X0, 128, R.OFF, ls=6)
    tag = spec.get("tag", "").upper()
    tw = R.measure(tag, R.REG, 22, 5)
    c.add(f'<circle cx="{R.XMAX-tw-24:.0f}" cy="105" r="7" fill="{tagcol}"/>')
    c.text(tag, R.REG, 22, R.XMAX, 112, R.MUTED, ls=5, anchor="end")
    c.text(spec.get("series", "").upper(), R.REG, 22, R.XMAX, 140, R.MUTED, ls=5, anchor="end")
    c.add(f'<rect x="{R.X0}" y="170" width="{R.XMAX-R.X0}" height="2" fill="{R.LINE}"/>')
    return sprite("".join(c.parts))


def footer_layer():
    c = R.Canvas()
    c.add(f'<rect x="{R.X0}" y="1170" width="{R.XMAX-R.X0}" height="2" fill="{R.LINE}"/>')
    c.add(R.logo_group())
    return sprite("".join(c.parts))


def end_card():
    svg = open(os.path.join(R.HERE, "brand/krayon-sports-motion-white.svg")).read()
    inner = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1)
    inner = (inner.replace('id="kgrad"', 'id="egrad"').replace("url(#kgrad)", "url(#egrad)")
                  .replace('id="streak"', 'id="estreak"').replace("url(#streak)", "url(#estreak)"))
    # wordmark spans x 58..378, y 165..246 in its own 412-unit box; scale to ~760 px wide, centred
    sc = 760 / (378 - 58)
    tx, ty = (W - 760) / 2 - 58 * sc, 820 - 205 * sc
    logo = sprite(f'<g transform="translate({tx:.1f} {ty - TOP:.1f}) scale({sc:.3f})">{inner}</g>')
    c = R.Canvas()
    c.text("FOLLOW @KRAYON_SPORTS", R.BOLD, 40, W / 2, 1090 - TOP, R.OFF, ls=6, anchor="middle")
    c.text("Scores tell you who won. We tell you why.", R.REG, 34, W / 2, 1150 - TOP, R.GREY, anchor="middle")
    line = sprite("".join(c.parts))
    return [l for l in (logo, line) if l]


# ---------------- animation ----------------
def ease_out(p):
    p = min(max(p, 0.0), 1.0)
    return 1 - (1 - p) ** 3


def ease_in(p):
    p = min(max(p, 0.0), 1.0)
    return p ** 3


def paste(frame, sp, dx, dy, alpha):
    if alpha <= 0.01:
        return
    img = sp["img"]
    if alpha < 0.99:
        a = np.asarray(img).copy()
        a[..., 3] = (a[..., 3] * alpha).astype(np.uint8)
        img = Image.fromarray(a, "RGBA")
    frame.alpha_composite(img, (int(sp["x"] + dx), int(sp["y"] + dy)))


def build_timeline(spec):
    slides = [as_reel_slide(s) for s in spec["slides"]]
    glows = R.GLOWS
    scenes, t = [], 0.0
    for i, s in enumerate(slides):
        layers = scene_layers(spec, s)
        appear_end = 0.3 + 0.28 * max(len(layers) - 1, 0) + 0.5
        hold = max(1.8, words_in(s) / 4.2)
        # land each scene change on the beat
        dur = min(max(appear_end + hold, 3.2), 7.0)
        dur = math.ceil(dur / BEAT) * BEAT
        gx, gy = glows[i % len(glows)]
        scenes.append({"start": t, "dur": dur, "layers": layers, "bg": background(gx, gy), "kind": "slide"})
        t += dur
    end_dur = 4 * BEAT
    scenes.append({"start": t, "dur": end_dur, "layers": end_card(), "bg": background(540, 640), "kind": "end"})
    return scenes, t + end_dur


def draw(scenes, header, footer, t):
    sc = next(s for s in scenes if s["start"] <= t < s["start"] + s["dur"]) if t < scenes[-1]["start"] + scenes[-1]["dur"] else scenes[-1]
    lt = t - sc["start"]
    # slow push-in on the background
    z = 1 + 0.035 * (lt / sc["dur"])
    bg = sc["bg"]
    if z > 1.001:
        bw, bh = int(W * z), int(H * z)
        bg = bg.resize((bw, bh), Image.BILINEAR).crop(((bw - W) // 2, (bh - H) // 2, (bw - W) // 2 + W, (bh - H) // 2 + H))
    frame = bg.convert("RGBA")
    out = max(0.0, (lt - (sc["dur"] - 0.35)) / 0.35)          # exit progress
    if sc["kind"] == "slide":
        a_h = ease_out(t / 0.4)
        if header:
            paste(frame, header, 0, 0, a_h)
        if footer:
            paste(frame, footer, 0, 0, a_h)
        for k, sp in enumerate(sc["layers"]):
            p = ease_out((lt - 0.3 - 0.28 * k) / 0.5)
            dx = -60 * (1 - p) if sp.get("name") in ("big",) else 0
            dy = 54 * (1 - p) - 36 * ease_in(out)
            paste(frame, sp, dx, dy, p * (1 - ease_in(out)))
    else:
        for k, sp in enumerate(sc["layers"]):
            p = ease_out((lt - 0.15 - 0.35 * k) / 0.6)
            dx = -120 * (1 - p) if k == 0 else 0
            dy = 0 if k == 0 else 40 * (1 - p)
            paste(frame, sp, dx, dy, p)
    return frame.convert("RGB")


# ---------------- original soundtrack ----------------
def soundtrack(scenes, total, path, sr=44100):
    n = int(total * sr) + sr
    mix = np.zeros(n)
    rng = np.random.default_rng(7)

    def add(sig, at):
        i = int(at * sr)
        j = min(n, i + len(sig))
        if i < n:
            mix[i:j] += sig[: j - i]

    tt = lambda d: np.arange(int(d * sr)) / sr
    # kick
    kt = tt(0.32)
    kick = np.sin(2 * np.pi * (45 * kt + (120 - 45) * (1 - np.exp(-kt * 30)) / 30)) * np.exp(-kt * 9)
    # hat
    ht = tt(0.05)
    hat = np.diff(rng.standard_normal(len(ht) + 1)) * np.exp(-ht * 90) * 0.18
    # bass notes per bar (A minor-ish: A F C G)
    roots = [55.0, 43.65, 65.41, 49.0]
    beats = int(total / BEAT) + 1
    for b in range(beats):
        at = b * BEAT
        add(kick * (0.9 if b % 4 == 0 else 0.7), at)
        add(hat, at + BEAT / 2)
        if b % 4 == 0:
            f = roots[(b // 4) % 4]
            bt = tt(BEAT * 4)
            env = np.minimum(1, bt / 0.04) * np.exp(-bt * 0.6)
            bass = (np.sin(2 * np.pi * f * bt) + 0.3 * np.sin(2 * np.pi * 2 * f * bt)) * env * 0.35
            add(bass, at)
            # soft pad: fifth + octave, slow attack
            pad = sum(np.sin(2 * np.pi * f * m * bt + ph) for m, ph in ((4, 0), (6, 1.3), (8, 2.1)))
            pad *= np.minimum(1, bt / 0.8) * np.minimum(1, (BEAT * 4 - bt) / 0.5) * 0.035
            add(pad, at)
    # whoosh into each scene change
    for sc in scenes[1:]:
        wt = tt(0.45)
        noise = rng.standard_normal(len(wt))
        # crude low-pass by moving average, opening up as it rises
        k = 24
        noise = np.convolve(noise, np.ones(k) / k, mode="same")
        add(noise * (wt / 0.45) ** 2 * 0.5, sc["start"] - 0.45)
    # fade in/out, normalise
    fade = int(0.4 * sr)
    mix[:fade] *= np.linspace(0, 1, fade)
    end = int(total * sr)
    mix[end - int(1.2 * sr):end] *= np.linspace(1, 0, int(1.2 * sr))
    mix = mix[:end]
    mix = np.tanh(mix * 1.2)
    mix *= 0.8 / max(1e-9, np.max(np.abs(mix)))
    st = np.stack([mix, mix], axis=1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((st * 32767).astype(np.int16).tobytes())


# ---------------- main ----------------
def main(spec_path):
    spec = json.load(open(spec_path))
    outdir = os.path.dirname(os.path.abspath(spec_path))
    scenes, total = build_timeline(spec)
    header, footer = header_layer(spec), footer_layer()
    wav = os.path.join(outdir, "reel-audio.wav")
    soundtrack(scenes, total, wav)
    mp4 = os.path.join(outdir, "reel.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", mp4]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    nframes = int(total * FPS)
    cover_t = min(scenes[0]["dur"] - 0.5, 2.6)
    for f in range(nframes):
        t = f / FPS
        fr = draw(scenes, header, footer, t)
        ff.stdin.write(fr.tobytes())
        if f == int(cover_t * FPS):
            fr.save(os.path.join(outdir, "reel-cover.jpg"), quality=90)
    ff.stdin.close()
    ff.wait()
    os.remove(wav)
    if ff.returncode:
        sys.exit("ffmpeg failed")
    print(f"{mp4}  ({total:.1f} s, {len(scenes)-1} scenes + end card)")


if __name__ == "__main__":
    main(sys.argv[1])
