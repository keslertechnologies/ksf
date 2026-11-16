#!/usr/bin/env python3
"""
Build KSF — Keslers Sans Font.

A heavy geometric, caps-only display face derived from the Keslers logo
lettering (keslers-k-logo, KTU, KUI): flat horizontal terminals, heavy
strokes, a detached chevron K, round-bottomed U -- with a double-struck
(blackboard bold) treatment: main stems are hollow, rounds carry a crescent
inline, and E is drawn as a stemless, Xi-like stack of three bars.

Every glyph is constructed from geometric primitives (rectangles,
parallelograms, ellipses) combined with boolean path ops, so the font is
fully reproducible. Tweak the constants below and re-run.

Requires (see requirements.txt):
    pip install -r requirements.txt
Usage (from the repo root):
    python3 sources/build_ksf.py

Writes fonts/otf/KSF.otf, fonts/ttf/KSF.ttf, fonts/webfonts/KSF.woff2,
documentation/specimen.png and ksf.png. The font version is read from
package.json so npm and the font files never disagree.

Licensed under the SIL Open Font License 1.1 (see OFL.txt).
"""
import json
import math
import os

import pathops
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.transformPen import TransformPen
from fontTools.misc.timeTools import timestampNow
from fontTools.ttLib import TTFont

# ---------------------------------------------------------------- metrics
UPM = 1000
CAP = 700          # cap height
V = 165            # vertical stem weight          (logo: ~0.235 x cap)
H = 148            # horizontal stroke weight      (logo: ~0.21 x cap)
D = 180            # diagonal weight, measured horizontally (logo K chevron)
OS = 12            # overshoot for round shapes
K_SLOPE = 0.63     # dx/dy of K chevron arms (measured from the logo)
K_GAP = 40         # gap between K stem and chevron (logo K has a gap)
MID = CAP / 2
SW = 55            # width of the double-struck slit
T = (V - SW) / 2   # line weight either side of the slit
ASC, DESC = 900, -250

BIG = 5000


# ------------------------------------------------------------- primitives
def P(*pts):
    p = pathops.Path()
    p.moveTo(*pts[0])
    for pt in pts[1:]:
        p.lineTo(*pt)
    p.close()
    return p


def R(x0, y0, x1, y1):
    return P((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def E(cx, cy, rx, ry, k=0.5523):
    """Ellipse from four cubic arcs."""
    p = pathops.Path()
    kx, ky = rx * k, ry * k
    p.moveTo(cx + rx, cy)
    p.cubicTo(cx + rx, cy + ky, cx + kx, cy + ry, cx, cy + ry)
    p.cubicTo(cx - kx, cy + ry, cx - rx, cy + ky, cx - rx, cy)
    p.cubicTo(cx - rx, cy - ky, cx - kx, cy - ry, cx, cy - ry)
    p.cubicTo(cx + kx, cy - ry, cx + rx, cy - ky, cx + rx, cy)
    p.close()
    return p


def stroke(p0, p1, w):
    """Rectangle of perpendicular width w along segment p0->p1."""
    (x0, y0), (x1, y1) = p0, p1
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy)
    nx, ny = -dy / L * w / 2, dx / L * w / 2
    return P((x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny))


def U(*paths):
    out = paths[0]
    for p in paths[1:]:
        out = pathops.op(out, p, pathops.PathOp.UNION)
    return out


def SUB(a, *bs):
    for b in bs:
        a = pathops.op(a, b, pathops.PathOp.DIFFERENCE)
    return a


def X(a, b):
    return pathops.op(a, b, pathops.PathOp.INTERSECTION)


def clipcap(p, lo=0, hi=CAP):
    return X(p, R(-BIG, lo, BIG, hi))


def ring(cx, cy, rx, ry, v=V, h=H):
    return SUB(E(cx, cy, rx, ry), E(cx, cy, rx - v, ry - h))


def bowl(x0, y0, x1, y1, rx=None):
    """Flat on the left, semi-elliptical on the right."""
    ry = (y1 - y0) / 2
    if rx is None:
        rx = min(ry, x1 - x0)
    cx = x1 - rx
    return U(R(x0, y0, cx, y1), E(cx, y0 + ry, rx, ry))


def bowl_glyph(x0, y0, x1, y1, rx=None, v=V, h=H, hb=None):
    """Outer bowl minus its counter (stadium-ended counter)."""
    hb = h if hb is None else hb
    return SUB(bowl(x0, y0, x1, y1, rx), bowl(x0 + v, y0 + hb, x1 - v, y1 - h))


# ---------------------------------------------------- double-struck slits
def vslit(x0, y0=0, y1=CAP, w=V):
    """Hollow out a vertical stem occupying x0..x0+w, y0..y1."""
    return R(x0 + T, y0 + T, x0 + w - T, y1 - T)


def dslit(xb, yb, xt, yt, w, lo=None, hi=None):
    """Hollow out a diagonal band whose left edge runs (xb,yb)->(xt,yt) and
    whose horizontal width is w."""
    dx, dy = xt - xb, yt - yb
    th = T * math.hypot(dx, dy) / dy
    lo = yb + T if lo is None else lo
    hi = yt - T if hi is None else hi
    L = lambda y: xb + dx * (y - yb) / dy
    return P((L(lo) + th, lo), (L(lo) + w - th, lo), (L(hi) + w - th, hi), (L(hi) + th, hi))


def crescent(cx, cy, rx, ry, side=-1):
    """Crescent inline on the left (side=-1) or right (side=+1) of a round."""
    a = E(cx, cy, rx - T, ry - T)
    b = E(cx - side * SW, cy, rx - T, ry - T)
    return SUB(a, b)


def mirror_x(p, w):
    return transform(p, (-1, 0, 0, 1, w, 0))


def rot180(p, w):
    return transform(p, (-1, 0, 0, -1, w, CAP))


def transform(p, m):
    out = pathops.Path()
    p.draw(TransformPen(out.getPen(), m))
    return out


# ----------------------------------------------------------------- glyphs
G = {}  # name -> (unicode list, path, shape_width, lsb, rsb)


def glyph(name, uni, w, lsb=55, rsb=55):
    def deco(fn):
        G[name] = (uni, fn(), w, lsb, rsb)
        return fn
    return deco


# -- A
@glyph("A", [0x41], 690, 15, 15)
def _():
    hull = P((0, 0), (270, CAP), (420, CAP), (690, 0))
    l = P((0, 0), (D, 0), (270 + D, CAP), (270, CAP))
    r = P((690 - D, 0), (690, 0), (420, CAP), (420 - D, CAP))
    bar = X(R(0, 150, 690, 150 + H * 0.9), hull)
    return SUB(X(clipcap(U(l, r, bar)), hull), dslit(690 - D, 0, 420 - D, CAP, D, hi=CAP - 150))


# -- B
@glyph("B", [0x42], 590, 55, 40)
def _():
    top_y0, bot_y1 = 290, 430
    outer = U(R(0, 0, V, CAP), bowl(0, top_y0, 550, CAP), bowl(0, 0, 590, bot_y1))
    return SUB(outer,
               bowl(V, bot_y1 - 4, 550 - V, CAP - H),
               bowl(V, H, 590 - V, top_y0 + 4), vslit(0))


# -- C
@glyph("C", [0x43], 690, 40, 25)
def _():
    cx = 345
    r = ring(cx, MID, 345, MID + OS)
    return SUB(r, R(cx + 40, MID - 135, BIG, MID + 135), crescent(cx, MID, 345, MID + OS))


# -- D
@glyph("D", [0x44], 650, 55, 40)
def _():
    return SUB(U(R(0, 0, V, CAP), bowl_glyph(0, 0, 650, CAP, rx=330)), vslit(0))


# -- E
@glyph("E", [0x45], 540, 35, 35)
def _():
    # Xi-style E: no stem, three bars, shorter middle bar lined up on the left
    hm = H * 0.92
    return U(R(0, CAP - H, 540, CAP), R(0, MID - hm / 2, 440, MID + hm / 2), R(0, 0, 540, H))


# -- F
@glyph("F", [0x46], 480, 55, 25)
def _():
    hm = H * 0.92
    return U(R(0, 0, V, CAP), R(0, CAP - H, 480, CAP),
             R(0, MID - hm / 2 - 20, 440, MID + hm / 2 - 20)) if False else SUB(
        U(R(0, 0, V, CAP), R(0, CAP - H, 480, CAP), R(0, MID - hm / 2 - 20, 440, MID + hm / 2 - 20)),
        vslit(0))


# -- G
@glyph("G", [0x47], 720, 40, 45)
def _():
    cx = 360
    r = ring(cx, MID, 360, MID + OS)
    r = SUB(r, R(cx + 30, MID, BIG, MID + 150))
    bar = X(R(cx - 10, MID - H * 0.95, BIG, MID), E(cx, MID, 360, MID + OS))
    return SUB(U(r, bar), crescent(cx, MID, 360, MID + OS))


# -- H
@glyph("H", [0x48], 610)
def _():
    hm = H * 0.92
    return SUB(U(R(0, 0, V, CAP), R(610 - V, 0, 610, CAP), R(0, MID - hm / 2, 610, MID + hm / 2)),
               vslit(0), vslit(610 - V))


# -- I
@glyph("I", [0x49], 400, 30, 30)
def _():
    # serifed I: centred hollow stem capped top and bottom like T's crossbar
    w = 400
    sx = w / 2 - V / 2
    return SUB(U(R(0, CAP - H, w, CAP), R(0, 0, w, H), R(sx, 0, sx + V, CAP)), vslit(sx))


# -- J
@glyph("J", [0x4A], 520, 25, 55)
def _():
    w = 520
    rx = w / 2
    outer = U(R(0, rx, w, CAP), E(rx, rx, rx, rx + OS))
    inner = U(R(V, rx, w - V, BIG), E(rx, rx, rx - V, rx + OS - H))
    j = SUB(outer, inner)
    return SUB(j, R(-BIG, 200, rx, BIG), vslit(w - V, rx - 40))


# -- K  (detached chevron, straight from the logo)
@glyph("K", [0x4B], V + K_GAP + D + K_SLOPE * MID, 55, 15)
def _():
    vx = V + K_GAP
    dx = K_SLOPE * MID
    up = P((vx, MID), (vx + D, MID), (vx + D + dx, CAP), (vx + dx, CAP))
    dn = P((vx, MID), (vx + D, MID), (vx + D + dx, 0), (vx + dx, 0))
    return SUB(U(R(0, 0, V, CAP), up, dn), vslit(0))


# -- L
@glyph("L", [0x4C], 470, 55, 20)
def _():
    return SUB(U(R(0, 0, V, CAP), R(0, 0, 470, H)), vslit(0))


# -- M
@glyph("M", [0x4D], 800)
def _():
    w, c = 800, 400
    l = P((0, CAP), (D, CAP), (c + D / 2, 0), (c - D / 2, 0))
    r = P((w - D, CAP), (w, CAP), (c + D / 2, 0), (c - D / 2, 0))
    return SUB(clipcap(U(R(0, 0, V, CAP), R(w - V, 0, w, CAP), l, r)), vslit(0), vslit(w - V))


# -- N
@glyph("N", [0x4E], 640)
def _():
    w = 640
    d = P((0, CAP), (D + 15, CAP), (w, 0), (w - D - 15, 0))
    return SUB(clipcap(U(R(0, 0, V, CAP), R(w - V, 0, w, CAP), d)), vslit(0), vslit(w - V))


# -- O
@glyph("O", [0x4F], 760, 40, 40)
def _():
    return SUB(ring(380, MID, 380, MID + OS), crescent(380, MID, 380, MID + OS))


# -- P
@glyph("P", [0x50], 580, 55, 30)
def _():
    return SUB(U(R(0, 0, V, CAP), bowl_glyph(0, 260, 580, CAP, hb=H * 0.92)), vslit(0))


# -- Q
@glyph("Q", [0x51], 760, 40, 30)
def _():
    o = ring(380, MID, 380, MID + OS)
    tail = P((430, 250), (610, 250), (790, -70), (610, -70))
    return SUB(U(o, tail), crescent(380, MID, 380, MID + OS))


# -- R
@glyph("R", [0x52], 610, 55, 20)
def _():
    leg = P((250, 300), (250 + D, 300), (610, 0), (610 - D, 0))
    return SUB(clipcap(U(R(0, 0, V, CAP), bowl_glyph(0, 260, 580, CAP, hb=H * 0.92), leg)), vslit(0))


# -- S
def s_shape(w=560, top_w=530, m=MID + 10, h=H, cut=45):
    cx = w / 2
    yt0, yb1 = m - h / 2, m + h / 2          # spine band
    cu = (yt0 + CAP + OS) / 2                # upper ring centre
    ru = (CAP + OS - yt0) / 2
    cl = (yb1 - OS) / 2                      # lower ring centre
    rl = (yb1 + OS) / 2
    up = ring(cx, cu, top_w / 2, ru, h=h)
    up = SUB(up, R(cx, -BIG, BIG, cu - cut))     # open lower-right
    lo = ring(cx, cl, w / 2, rl, h=h)
    lo = SUB(lo, R(-BIG, cl + cut, cx, BIG))     # open upper-left
    return SUB(U(up, lo), crescent(cx, cu, top_w / 2, ru, -1))


@glyph("S", [0x53], 560, 35, 35)
def _():
    return s_shape()


# -- T
@glyph("T", [0x54], 570, 15, 15)
def _():
    return SUB(U(R(0, CAP - H, 570, CAP), R(285 - V / 2, 0, 285 + V / 2, CAP)), vslit(285 - V / 2))


# -- U
@glyph("U", [0x55], 570)
def _():
    w = 570
    rx = w / 2
    outer = U(R(0, rx, w, CAP), E(rx, rx, rx, rx + OS))
    inner = U(R(V, rx, w - V, BIG), E(rx, rx, rx - V, rx + OS - H))
    return SUB(outer, inner, vslit(0, rx - 40))


# -- V
@glyph("V", [0x56], 690, 15, 15)
def _():
    l = P((0, CAP), (D, CAP), (270 + D, 0), (270, 0))
    r = P((690 - D, CAP), (690, CAP), (420, 0), (420 - D, 0))
    hull = P((0, CAP), (690, CAP), (420, 0), (270, 0))
    return SUB(X(clipcap(U(l, r)), hull), dslit(270, 0, 0, CAP, D, lo=150))


# -- W
@glyph("W", [0x57], 980, 15, 15)
def _():
    d = 172
    s1 = P((0, CAP), (d, CAP), (205 + d, 0), (205, 0))
    s2 = P((205, 0), (205 + d, 0), (395 + d, CAP), (395, CAP))
    s3 = P((980 - 205, 0), (980 - 205 - d, 0), (980 - 395 - d, CAP), (980 - 395, CAP))
    s4 = P((980, CAP), (980 - d, CAP), (980 - 205 - d, 0), (980 - 205, 0))
    return SUB(clipcap(U(s1, s2, s3, s4)), dslit(205, 0, 0, CAP, d), dslit(980 - 205 - d, 0, 980 - 395 - d, CAP, d))


# -- X
@glyph("X", [0x58], 660, 15, 15)
def _():
    a = P((0, CAP), (D + 10, CAP), (660, 0), (660 - D - 10, 0))
    b = P((660 - D - 10, CAP), (660, CAP), (D + 10, 0), (0, 0))
    return SUB(clipcap(U(a, b)), dslit(660 - D - 10, 0, 0, CAP, D + 10))


# -- Y
@glyph("Y", [0x59], 670, 15, 15)
def _():
    c, j = 335, 300
    l = P((0, CAP), (D, CAP), (c + V / 2, j), (c - V / 2, j))
    r = P((670 - D, CAP), (670, CAP), (c + V / 2, j), (c - V / 2, j))
    return SUB(clipcap(U(l, r, R(c - V / 2, 0, c + V / 2, j + 40))), vslit(c - V / 2, 0, j + 20))


# -- Z
@glyph("Z", [0x5A], 570, 30, 30)
def _():
    dw = 235
    d = P((550 - dw, CAP - H), (550, CAP - H), (dw, H), (0, H))
    return SUB(U(R(15, CAP - H, 550, CAP), R(0, 0, 570, H), d), dslit(0, H, 550 - dw, CAP - H, dw, H, CAP - H))


# ---------------------------------------------------------------- figures
@glyph("zero", [0x30], 590, 40, 40)
def _():
    return SUB(ring(295, MID, 295, MID + OS), crescent(295, MID, 295, MID + OS))


@glyph("one", [0x31], 390, 25, 55)
def _():
    flag = P((0, 430), (0, 580), (240, CAP), (240, 550))
    return SUB(U(R(390 - V, 0, 390, CAP), flag), vslit(390 - V))


@glyph("two", [0x32], 570, 35, 35)
def _():
    cx, ry = 285, 215
    cu = CAP + OS - ry
    r = ring(cx, cu, 275, ry)
    jy = cu - 40
    r = SUB(r, R(-BIG, -BIG, cx, cu), R(-BIG, -BIG, BIG, jy))
    diag = P((373, jy), (cx + 275 - 4, jy), (250, H), (0, H))
    return U(r, diag, R(0, 0, 570, H))


@glyph("three", [0x33], 560, 30, 35)
def _():
    m, h = MID + 10, H
    yt0, yb1 = m - h / 2, m + h / 2
    cu, ru = (yt0 + CAP + OS) / 2, (CAP + OS - yt0) / 2
    cl, rl = (yb1 - OS) / 2, (yb1 + OS) / 2
    up = SUB(ring(270, cu, 255, ru), R(-BIG, -BIG, 270, cu - 20))
    lo = SUB(ring(285, cl, 275, rl), R(-BIG, cl + 20, 285, BIG))
    tongue = R(150, yt0, 290, yb1)
    return U(up, lo, tongue)


@glyph("four", [0x34], 590, 20, 30)
def _():
    sx = 590 - 30 - V
    stem = R(sx, 0, sx + V, CAP)
    bar = R(0, 150, 590, 150 + H * 0.95)
    diag = P((0, 150), (195, 150), (sx + V, CAP), (sx + V - 195, CAP))
    # trim the bar's left end flush with the diagonal's outer edge
    k = (sx + V - 195) / (CAP - 150)
    right_of_diag = P((-150 * k, 0), (sx + V - 195, CAP), (BIG, CAP), (BIG, 0))
    bar = X(bar, right_of_diag)
    return SUB(U(stem, bar, X(diag, R(0, 0, sx + V, CAP))), vslit(sx))


@glyph("five", [0x35], 560, 35, 35)
def _():
    cx, ry = 280, 250
    cl = ry - OS
    r = SUB(ring(cx, cl, 280, ry), R(-BIG, 160, cx, BIG))
    top_r = cl + ry
    stem = R(35, top_r - H, 35 + V, CAP)
    link = R(35, top_r - H, cx, top_r)
    top = R(35, CAP - H, 545, CAP)
    return SUB(U(r, stem, link, top), vslit(35, cl + ry - H, CAP))


@glyph("six", [0x36], 580, 40, 40)
def _():
    cl, ry = 247 - OS, 247
    r = ring(290, cl, 290, ry)
    diag = P((3, cl), (3 + D + 10, cl), (440, CAP), (440 - D - 10, CAP))
    return SUB(U(r, clipcap(diag)), E(290, cl, 290 - V, ry - H), crescent(290, cl, 290, ry))


@glyph("seven", [0x37], 550, 25, 15)
def _():
    diag = P((550 - 205, CAP - H), (550, CAP - H), (275, 0), (70, 0))
    return SUB(U(R(0, CAP - H, 550, CAP), diag), dslit(70, 0, 345, CAP - H, 205, T, CAP - H))


@glyph("eight", [0x38], 580, 40, 40)
def _():
    m, h = MID + 15, H * 0.95
    yt0, yb1 = m - h / 2, m + h / 2
    cu, ru = (yt0 + CAP + OS) / 2, (CAP + OS - yt0) / 2
    cl, rl = (yb1 - OS) / 2, (yb1 + OS) / 2
    return U(ring(290, cu, 255, ru, h=h), ring(290, cl, 290, rl, h=h))


@glyph("nine", [0x39], 580, 40, 40)
def _():
    return rot180(G["six"][1], 580)


# ------------------------------------------------------------ punctuation
@glyph("space", [0x20], 0, 130, 130)
def _():
    return pathops.Path()


@glyph("period", [0x2E], V, 50, 50)
def _():
    return R(0, 0, V, V)


def comma_shape():
    return U(R(0, 0, V, V), P((0, 0), (V, 0), (90, -150), (-20, -150)))


@glyph("comma", [0x2C], V, 50, 50)
def _():
    return comma_shape()


@glyph("colon", [0x3A], V, 55, 55)
def _():
    return U(R(0, 0, V, V), R(0, 400, V, 400 + V))


@glyph("semicolon", [0x3B], V, 55, 55)
def _():
    return U(comma_shape(), R(0, 400, V, 400 + V))


@glyph("exclam", [0x21], V, 55, 55)
def _():
    return U(R(0, 255, V, CAP), R(0, 0, V, V))


@glyph("question", [0x3F], 520, 30, 35)
def _():
    cx, ry = 260, 210
    cu = CAP + OS - ry
    r = SUB(ring(cx, cu, 260, ry), R(-BIG, -BIG, cx - 1, cu))
    stem = R(cx - V / 2, 250, cx + V / 2, cu - ry + H)
    return U(r, stem, R(cx - V / 2, 0, cx + V / 2, V))


@glyph("quotesingle", [0x27], 140, 55, 55)
def _():
    return R(0, 450, 140, CAP)


@glyph("quotedbl", [0x22], 380, 55, 55)
def _():
    return U(R(0, 450, 140, CAP), R(240, 450, 380, CAP))


@glyph("quoteright", [0x2019], V, 50, 50)
def _():
    return transform(comma_shape(), (1, 0, 0, 1, 0, CAP - V))


@glyph("quoteleft", [0x2018], V, 50, 50)
def _():
    return transform(comma_shape(), (-1, 0, 0, -1, V, CAP - 150))


@glyph("hyphen", [0x2D], 320, 40, 40)
def _():
    return R(0, 270, 320, 270 + H * 0.92)


@glyph("endash", [0x2013], 520, 30, 30)
def _():
    return R(0, 270, 520, 270 + H * 0.92)


@glyph("emdash", [0x2014], 940, 30, 30)
def _():
    return R(0, 270, 940, 270 + H * 0.92)


@glyph("underscore", [0x5F], 560, 20, 20)
def _():
    return R(0, -170, 560, -170 + H * 0.9)


@glyph("slash", [0x2F], 470, 10, 10)
def _():
    return clipcap(P((0, -80), (D, -80), (470, 780), (470 - D, 780)), -80, 780)


@glyph("backslash", [0x5C], 470, 10, 10)
def _():
    return mirror_x(G["slash"][1], 470)


@glyph("parenleft", [0x28], 270, 50, 15)
def _():
    r = ring(330, MID, 330, 470, h=150)
    return X(r, R(-BIG, -BIG, 270, BIG))


@glyph("parenright", [0x29], 270, 15, 50)
def _():
    return mirror_x(G["parenleft"][1], 270)


@glyph("bracketleft", [0x5B], 300, 55, 15)
def _():
    return U(R(0, -120, V, 820), R(0, 820 - 130, 300, 820), R(0, -120, 300, 10))


@glyph("bracketright", [0x5D], 300, 15, 55)
def _():
    return mirror_x(G["bracketleft"][1], 300)


@glyph("plus", [0x2B], 520, 40, 40)
def _():
    t = 145
    return U(R(0, MID - t / 2, 520, MID + t / 2), R(260 - t / 2, MID - 260, 260 + t / 2, MID + 260))


@glyph("equal", [0x3D], 520, 40, 40)
def _():
    t = 135
    return U(R(0, MID - 45 - t, 520, MID - 45), R(0, MID + 45, 520, MID + 45 + t))


@glyph("less", [0x3C], 450, 40, 40)
def _():
    dx = 270
    a, b = MID - 260, MID + 260
    up = P((0, MID), (D, MID), (D + dx, b), (dx, b))
    dn = P((0, MID), (D, MID), (D + dx, a), (dx, a))
    return U(up, dn)


@glyph("greater", [0x3E], 450, 40, 40)
def _():
    return mirror_x(G["less"][1], 450)


@glyph("numbersign", [0x23], 640, 30, 30)
def _():
    t = 130
    return U(R(140, 0, 140 + t, CAP), R(370, 0, 370 + t, CAP),
             R(0, 175, 640, 175 + t), R(0, CAP - 175 - t, 640, CAP - 175))


@glyph("percent", [0x25], 780, 30, 30)
def _():
    a = ring(150, CAP - 175, 150, 175 + OS / 2, v=100, h=95)
    b = ring(630, 175, 150, 175 + OS / 2, v=100, h=95)
    s = clipcap(P((80, -10), (220, -10), (700, 710), (560, 710)), -10, 710)
    return U(a, b, s)


@glyph("dollar", [0x24], 560, 35, 35)
def _():
    return U(s_shape(), R(280 - 55, -110, 280 + 55, CAP + 110))


@glyph("asterisk", [0x2A], 440, 40, 40)
def _():
    c, r, t = (220, 520), 200, 120
    arms = [stroke((c[0] + r * math.cos(a), c[1] + r * math.sin(a)),
                   (c[0] - r * math.cos(a), c[1] - r * math.sin(a)), t)
            for a in (math.pi / 2, math.pi / 2 + 2 * math.pi / 3, math.pi / 2 - 2 * math.pi / 3)]
    return U(*arms)


@glyph("ampersand", [0x26], 700, 30, 20)
def _():
    loop = ring(245, 540, 175, 160 + OS, v=135, h=125)
    cl = 225
    lo = SUB(ring(270, cl, 270, cl + OS, v=V, h=H), R(270, cl - 10, BIG, BIG), R(-BIG, 380, BIG, BIG))
    leg = P((110, 470), (320, 470), (700, 0), (490, 0))
    arm = R(380, 300, 700, 300 + H * 0.9)
    return clipcap(U(loop, lo, leg, arm), -OS, CAP + OS)


@glyph("at", [0x40], 860, 35, 35)
def _():
    cx, cy, rx, ry = 430, 300, 430, 440
    outer = SUB(ring(cx, cy, rx, ry, v=110, h=105), R(cx, 140, BIG, cy))
    inner = ring(cx - 20, cy, 175, 190, v=120, h=115)
    sx = cx - 20 + 175 - 120
    stem = R(sx, 140, sx + 120, cy + 190)
    foot = X(R(sx, 140, BIG, 250), E(cx, cy, rx, ry))
    return U(outer, inner, stem, foot)


# ------------------------------------------------------------------ build
def glyph_order():
    return [".notdef"] + list(G.keys())


def placed(name):
    uni, path, w, lsb, rsb = G[name]
    p = transform(path, (1, 0, 0, 1, lsb, 0))
    return p, int(round(w + lsb + rsb))


def notdef():
    p = SUB(R(50, 0, 550, CAP), R(130, 80, 470, CAP - 80))
    return p, 600


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(ROOT, "package.json")) as _f:
    PKG_VERSION = json.load(_f)["version"]
_maj, _min, _pat = (int(n) for n in PKG_VERSION.split("."))
FONT_REVISION = float(f"{_maj}.{_min:02d}{_pat}")           # 1.0.0 -> 1.000
VERSION_STRING = f"Version {_maj}.{_min:02d}{_pat}"

COPYRIGHT = "Copyright 2026 The KSF Project Authors (https://gitlab.com/keslers/ksf)"
LICENSE = ("This Font Software is licensed under the SIL Open Font License, Version 1.1. "
           "This license is available with a FAQ at: https://openfontlicense.org")


def build(path_out, cff):
    fb = FontBuilder(UPM, isTTF=not cff)
    order = glyph_order()
    fb.setupGlyphOrder(order)

    cmap = {}
    for name, (uni, *_rest) in G.items():
        for u in uni:
            cmap[u] = name
    # caps-only: lowercase a–z map onto the capitals
    for c in range(ord("a"), ord("z") + 1):
        cmap[c] = chr(c).upper()
    fb.setupCharacterMap(cmap)

    shapes = {".notdef": notdef()}
    for n in G:
        shapes[n] = placed(n)

    metrics = {}
    if cff:
        charstrings = {}
        for n in order:
            p, adv = shapes[n]
            p = pathops.Path(p)
            p.simplify(fix_winding=True, clockwise=False)
            pen = T2CharStringPen(adv, None)
            p.draw(pen)
            charstrings[n] = pen.getCharString()
            b = p.bounds if len(p) else (0, 0, 0, 0)
            metrics[n] = (adv, int(math.floor(b[0])))
        fb.setupCFF("KSF-Regular", {"FullName": "KSF"}, charstrings, {})
    else:
        glyphs = {}
        for n in order:
            p, adv = shapes[n]
            p = pathops.Path(p)
            p.simplify(fix_winding=True, clockwise=True)
            tt = TTGlyphPen(None)
            p.draw(Cu2QuPen(tt, max_err=0.5, reverse_direction=False))
            g = tt.glyph()
            glyphs[n] = g
            b = p.bounds if len(p) else (0, 0, 0, 0)
            metrics[n] = (adv, int(math.floor(b[0])))
        fb.setupGlyf(glyphs)

    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASC, descent=DESC)
    fb.setupNameTable({
        "copyright": COPYRIGHT,
        "familyName": "KSF",
        "styleName": "Regular",
        "uniqueFontIdentifier": f"{PKG_VERSION};KSLR;KSF-Regular",
        "fullName": "KSF Regular",
        "version": VERSION_STRING,
        "psName": "KSF-Regular",
        "manufacturer": "Kesler Technologies",
        "designer": "Christian 'CJ' Kesler",
        "description": "Keslers Sans Font: heavy geometric double-struck capitals "
                       "from the Keslers logo lettering.",
        "vendorURL": "https://gitlab.com/keslers",
        "designerURL": "https://gitlab.com/keslers",
        "licenseDescription": LICENSE,
        "licenseInfoURL": "https://openfontlicense.org",
    })
    fb.setupOS2(
        version=4,
        sTypoAscender=ASC, sTypoDescender=DESC, sTypoLineGap=0,
        usWinAscent=ASC, usWinDescent=-DESC,
        sCapHeight=CAP, sxHeight=CAP, usWeightClass=400,
        achVendID="KSLR", fsSelection=0x40 | 0x80,  # REGULAR | USE_TYPO_METRICS
        fsType=0,                                    # installable embedding (OFL)
    )
    fb.setupPost()
    now = timestampNow()
    fb.setupHead(unitsPerEm=UPM, fontRevision=FONT_REVISION, created=now, modified=now)
    fb.addOpenTypeFeatures(KERN_FEA)
    fb.save(path_out)


KERN_FEA = """
@DIAG_L = [A];
@DIAG_R = [V W Y];
@ROUND  = [C G O Q];
feature kern {
    pos A [T] -60;  pos [T] A -60;
    pos A @DIAG_R -55;  pos @DIAG_R A -55;
    pos L [T V W Y] -70;
    pos [P] A -45;
    pos [F] A -35;
    pos [T] @ROUND -20; pos @ROUND [T] -20;
    pos A @ROUND -15; pos @ROUND A -15;
    pos [V W Y] @ROUND -20; pos @ROUND [V W Y] -20;
    pos [T V W Y P F] [period comma] -70;
    pos [period comma] [T V W Y] -70;
    pos L quoteright -60;
} kern;
"""


LOGO_COLOR = "#14B8A6"   # Keslers palette: Ocean Mist


def render_images(ttf):
    """Specimen sheet + repo/avatar logo (white K, colored SF), rendered with
    the font itself. Skipped if Pillow isn't installed."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Pillow not installed: skipping specimen.png and ksf.png")
        return []

    lines = [("KESLER TECHNOLOGIES", 104), ("ABCDEFGHIJKLM", 110), ("NOPQRSTUVWXYZ", 110),
             ("0123456789", 110), (".,:;!?'\"-\u2013\u2014_/\\()[]+=<>#%$*&@", 90),
             ("THE QUICK BROWN FOX JUMPS OVER", 80), ("THE LAZY DOG 2026", 80)]
    img = Image.new("RGB", (1700, 1150), "black")
    d = ImageDraw.Draw(img)
    y = 30
    for text, size in lines:
        d.text((40, y), text, font=ImageFont.truetype(ttf, size), fill="white")
        y += int(size * 1.4)
    specimen = os.path.join(ROOT, "documentation", "specimen.png")
    os.makedirs(os.path.dirname(specimen), exist_ok=True)
    img.save(specimen)

    # Logo: same canvas and proportions as the KTU / KUI logos (1024px,
    # letters ~280px tall, centred).
    size = 1024
    f = ImageFont.truetype(ttf, int(280 / CAP * UPM))
    img = Image.new("RGB", (size, size), "black")
    d = ImageDraw.Draw(img)
    wk = d.textlength("K", font=f)
    w = d.textlength("KSF", font=f)
    x = (size - w) / 2
    cap_px = 280
    y = (size - cap_px) / 2 - f.getmetrics()[0] + cap_px
    d.text((x, y), "K", font=f, fill="white")
    d.text((x + wk, y), "SF", font=f, fill=LOGO_COLOR)
    logo = os.path.join(ROOT, "ksf.png")
    img.save(logo)
    return [specimen, logo]


def main():
    outs = {
        "otf": os.path.join(ROOT, "fonts", "otf", "KSF.otf"),
        "ttf": os.path.join(ROOT, "fonts", "ttf", "KSF.ttf"),
        "woff2": os.path.join(ROOT, "fonts", "webfonts", "KSF.woff2"),
    }
    for path in outs.values():
        os.makedirs(os.path.dirname(path), exist_ok=True)
    build(outs["otf"], cff=True)
    build(outs["ttf"], cff=False)
    f = TTFont(outs["ttf"])
    f.flavor = "woff2"
    f.save(outs["woff2"])
    written = list(outs.values()) + render_images(outs["ttf"])
    for path in written:
        print("wrote", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    main()
