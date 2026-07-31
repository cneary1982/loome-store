"""
LOOME letterhead, built from the real brand assets in src/App.jsx.

Logo, transcribed from the <Logo/> component:
  "L" + two ring-dots + "ME"   -- the OO of LOOME are the marks
  ring    circle r=7.5/18, stroke wheat, width 2
  centre  circle r=3.5/18, fill sage
  glint   circle r=1.2/18 at (12, 6.5), white @ 85%
Palette, transcribed from C:
  iron #232F3E   ironL #37475A   wheat #C8B896
  sage #3DAA6A   amber #E8973A   teal  #1B8FA8
"""
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.colors import HexColor, Color
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONTS = '/root/.claude/skills/canvas-design/canvas-fonts'
pdfmetrics.registerFont(TTFont('Outfit-Bold', f'{FONTS}/Outfit-Bold.ttf'))
pdfmetrics.registerFont(TTFont('Mono', f'{FONTS}/IBMPlexMono-Regular.ttf'))

IRON  = HexColor('#232F3E')
IRONL = HexColor('#37475A')
WHEAT = HexColor('#C8B896')
SAGE  = HexColor('#3DAA6A')
AMBER = HexColor('#E8973A')
TEAL  = HexColor('#1B8FA8')
MUTED = HexColor('#767676')
HAIR  = HexColor('#DDDDDD')
WHITE = HexColor('#FFFFFF')

TRACK = -0.014          # the component sets letterSpacing -.3px at 22px


def _txt(c, s, x, y, pt, col):
    c.setFont('Outfit-Bold', pt)
    c.setFillColor(col)
    adv = 0.0
    for ch in s:
        c.drawString(x + adv, y, ch)
        adv += pdfmetrics.stringWidth(ch, 'Outfit-Bold', pt) + TRACK * pt
    return adv


def _txt_w(s, pt):
    return sum(pdfmetrics.stringWidth(ch, 'Outfit-Bold', pt) for ch in s) \
        + TRACK * pt * len(s)


def ring_dot(c, x, y, d):
    """One O of LOOME. `d` is the box size; geometry scaled from the 18px SVG."""
    s = d / 18.0
    cx, cy = x + 9 * s, y + 9 * s
    c.setStrokeColor(WHEAT)
    c.setLineWidth(2 * s)
    c.circle(cx, cy, 7.5 * s, stroke=1, fill=0)
    c.setFillColor(SAGE)
    c.circle(cx, cy, 3.5 * s, stroke=0, fill=1)
    # the glint sits upper-right; SVG y is top-down, so flip it
    c.setFillColor(Color(1, 1, 1, alpha=0.85))
    c.circle(x + 12 * s, y + (18 - 6.5) * s, 1.2 * s, stroke=0, fill=1)


def logo_width(pt):
    d = pt * 18.0 / 22.0
    g = pt * 2.0 / 22.0
    return _txt_w('L', pt) + g + d + g + d + g + _txt_w('ME', pt)


def draw_logo(c, x, y, pt, col=IRON):
    """`y` is the text baseline. Returns the advance width."""
    d = pt * 18.0 / 22.0
    g = pt * 2.0 / 22.0
    # the component centres the dots on the text and nudges them down 1px
    box_y = y + 0.36 * pt - d / 2.0 - pt * (1.0 / 22.0)

    adv = _txt(c, 'L', x, y, pt, col) + g
    ring_dot(c, x + adv, box_y, d); adv += d + g
    ring_dot(c, x + adv, box_y, d); adv += d + g
    adv += _txt(c, 'ME', x + adv, y, pt, col)
    return adv


def label(c, x, y, s, size=5.4, col=MUTED, track=0.9):
    c.saveState()
    c.setFont('Mono', size)
    c.setFillColor(col)
    adv = 0.0
    for ch in s:
        c.drawString(x + adv, y, ch)
        adv += pdfmetrics.stringWidth(ch, 'Mono', size) + track
    c.restoreState()
    return adv


def mono_w(s, size, track=0.9):
    return sum(pdfmetrics.stringWidth(ch, 'Mono', size) + track for ch in s) - track


# ---------------------------------------------------------------- the band
# 488 pt is the letter's content measure (12240 - 1240 - 1240 DXA).
BW = 488.0
LOGO_PT = 27.0
BH = 46.0
S = 4.0                                     # draw at 4x, rasterise down

def draw_band(c, bg=WHITE):
    c.setFillColor(bg)
    c.rect(0, 0, BW, BH, stroke=0, fill=1)
    base = 17.0
    draw_logo(c, 0, base, LOGO_PT)

    ry = 3.0
    c.setLineCap(0)
    c.setStrokeColor(HAIR)
    c.setLineWidth(0.8)
    c.line(0, ry, BW, ry)
    c.setStrokeColor(IRON)
    c.line(0, ry, 132.0, ry)
    # the site rules its trust banner in wheat; echo that as the accent
    c.setStrokeColor(WHEAT)
    c.setLineWidth(2.6)
    c.line(0, ry, 46.0, ry)
    c.setStrokeColor(SAGE)
    c.line(46.0, ry, 74.0, ry)


bc = rl_canvas.Canvas('loome-band.pdf', pagesize=(BW * S, BH * S))
bc.scale(S, S)
draw_band(bc)
bc.showPage()
bc.save()
print(f'wrote loome-band.pdf ({BW:.0f} x {BH:.0f} pt, aspect {BW/BH:.5f})')


# ------------------------------------------------------------ the sheet
W, H = 612.0, 792.0
ML = MR = 62.0

lc = rl_canvas.Canvas('LOOME-Letterhead.pdf', pagesize=(W, H))
lc.setFillColor(WHITE)
lc.rect(0, 0, W, H, stroke=0, fill=1)

top = H - 56.0
lc.saveState()
lc.translate(ML, top - 46.0)
draw_band(lc)
lc.restoreState()

label(lc, ML, top - 60.0, '[STREET ADDRESS]   [CITY, STATE ZIP]   [PHONE]', 5.4, MUTED)
label(lc, W - MR - mono_w('LOOME.COM', 5.4), top - 60.0, 'LOOME.COM', 5.4, IRON)

fy = 60.0
lc.setStrokeColor(HAIR)
lc.setLineWidth(0.4)
lc.line(ML, fy + 15.0, W - MR, fy + 15.0)
label(lc, ML, fy, 'LOOME INC.', 4.8, MUTED)
label(lc, W - MR - mono_w('FIG. 01', 4.8), fy, 'FIG. 01', 4.8, MUTED)

lc.showPage()

# --- the logo, large, with the palette it is drawn from
lc.setFillColor(WHITE)
lc.rect(0, 0, W, H, stroke=0, fill=1)
draw_logo(lc, ML + 24.0, H - 220.0, 76.0)
label(lc, ML + 24.0, H - 250.0, 'L + TWO RING-DOTS + ME  —  THE OO ARE THE MARKS', 5.4, MUTED)

py = H - 340.0
for i, (col, nm) in enumerate([(IRON, 'IRON   232F3E'), (WHEAT, 'WHEAT  C8B896'),
                               (SAGE, 'SAGE   3DAA6A'), (AMBER, 'AMBER  E8973A'),
                               (TEAL, 'TEAL   1B8FA8')]):
    px = ML + 24.0 + i * 96.0
    lc.setFillColor(col)
    lc.rect(px, py, 24.0, 24.0, stroke=0, fill=1)
    label(lc, px, py - 12.0, nm, 4.8, MUTED, track=0.5)

label(lc, ML + 24.0, py - 60.0, 'TRANSCRIBED FROM src/App.jsx — <Logo/> AND THE C PALETTE', 5.0, MUTED)

lc.setStrokeColor(HAIR)
lc.setLineWidth(0.4)
lc.line(ML, fy + 15.0, W - MR, fy + 15.0)
label(lc, ML, fy, 'LOOME INC.', 4.8, MUTED)
label(lc, W - MR - mono_w('FIG. 02', 4.8), fy, 'FIG. 02', 4.8, MUTED)
lc.showPage()
lc.save()
print('wrote LOOME-Letterhead.pdf')
