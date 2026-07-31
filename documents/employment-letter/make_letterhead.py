"""
WOVEN SIGNAL — loomi.ai identity + letterhead
Subtle reference: "loomi" contains LOOM. Plain weave, warp and weft.
One accent thread runs through the ink weave — the signal in the fabric.
"""
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONTS = '/root/.claude/skills/canvas-design/canvas-fonts'
pdfmetrics.registerFont(TTFont('Outfit', f'{FONTS}/Outfit-Regular.ttf'))
pdfmetrics.registerFont(TTFont('Outfit-Bold', f'{FONTS}/Outfit-Bold.ttf'))
pdfmetrics.registerFont(TTFont('Mono', f'{FONTS}/IBMPlexMono-Regular.ttf'))

# ---- Palette: an ink, a light, and the paper between them ----------
INK    = HexColor('#11132B')
ACCENT = HexColor('#6D5AE6')
PAPER  = HexColor('#FBFAF8')
MUTED  = HexColor('#8A8FA3')
HAIR   = HexColor('#DCDEE6')

N = 4              # warp count == weft count
F = 0.44           # thread width as a fraction of pitch — thread, not block
G = 0.21           # knockout gap, as a fraction of thread width
OH = 0.58          # thread tail beyond the last crossing, as a fraction of pitch
SIGNAL = 2         # the accent weft, off dead centre


# =====================================================================
# THE MARK — a plain weave, drawn as real interlace
# =====================================================================
def _threads(size, n=N, f=F, oh=OH):
    """
    Thread width and crossing-centre offsets, laid out so that every crossing
    is a true interior crossing — each thread runs on past the last one it
    meets, and the mark's VISUAL bounds (round terminals included) measure
    exactly `size` on both axes.
    """
    q = size / (n - 1 + 2 * oh + f)  # pitch
    tw = f * q                       # thread width
    first = oh * q + tw / 2.0        # edge -> first crossing centre
    return tw, [first + i * q for i in range(n)]


def draw_mark(c, x, y, size, n=N, signal=SIGNAL, ink=INK, accent=ACCENT,
              bg=PAPER, g=G):
    """
    Plain weave. Warp = vertical, weft = horizontal.
    Cell (i,j): the weft passes OVER the warp when (i+j) is even.

    Ink crossing ink shows nothing, so the pass-under is cut with a hairline
    of ground — the thread visibly goes behind and comes back. Three passes:
      1. weft, full span    2. warp, full span (now entirely on top)
      3. at every OVER crossing: knock a gap in the warp, lay the weft across
    """
    tw, cs = _threads(size, n)
    a, b = x + tw / 2.0, x + size - tw / 2.0     # thread span, x
    p, q = y + tw / 2.0, y + size - tw / 2.0     # thread span, y
    gap = g * tw
    reach = tw / 2.0 + gap                       # half-length of the crossing

    c.saveState()
    c.setLineCap(1)                  # round — the soft cut end of a thread
    c.setLineWidth(tw)

    def weft_col(j):
        return accent if j == signal else ink

    for j in range(n):               # 1 — weft
        c.setStrokeColor(weft_col(j))
        c.line(a, y + cs[j], b, y + cs[j])

    c.setStrokeColor(ink)            # 2 — warp
    for i in range(n):
        c.line(x + cs[i], p, x + cs[i], q)

    c.setLineCap(0)                  # butt — crossings are exact rectangles
    for j in range(n):               # 3 — the weft rides over
        for i in range(n):
            if (i + j) % 2:
                continue
            xx, yy = x + cs[i], y + cs[j]
            c.setStrokeColor(bg)     # cut the warp
            c.setLineWidth(tw + 2 * gap)
            c.line(xx - reach, yy, xx + reach, yy)
            c.setStrokeColor(weft_col(j))   # lay the weft across the cut
            c.setLineWidth(tw)
            c.line(xx - reach - 0.02, yy, xx + reach + 0.02, yy)
    c.restoreState()


# =====================================================================
# THE WORDMARK
# =====================================================================
def draw_wordmark(c, x, y, pt, ink=INK, accent=ACCENT, track=-0.012):
    """'loomi' in ink, '.ai' in light. Returns the total advance."""
    def run(txt, size, xx, col):
        c.setFont('Outfit-Bold', size)
        c.setFillColor(col)
        adv = 0.0
        for ch in txt:
            c.drawString(xx + adv, y, ch)
            adv += pdfmetrics.stringWidth(ch, 'Outfit-Bold', size) + track * size
        return adv

    w1 = run('loomi', pt, x, ink)
    w2 = run('.ai', pt, x + w1, accent)
    return w1 + w2


def wordmark_width(pt, track=-0.012):
    """Advance of the wordmark. No trailing track — it would clip the final i."""
    return sum(pdfmetrics.stringWidth(ch, 'Outfit-Bold', pt)
               for ch in 'loomi.ai') + track * pt * (len('loomi.ai') - 1)


def lockup(c, x, y, mark_size, pt=None, gap=None):
    """
    Mark + wordmark, optically centred on each other. `y` is the foot of the
    mark. The wordmark's optical centre sits ~0.33em above its baseline —
    the round lowercase carries the mass, the ascenders pull it up.
    Returns the total advance width.
    """
    pt = pt or mark_size * 0.75
    gap = gap if gap is not None else mark_size * 0.44
    draw_mark(c, x, y, mark_size)
    base = y + mark_size / 2.0 - 0.33 * pt
    w = draw_wordmark(c, x + mark_size + gap, base, pt)
    return mark_size + gap + w


def label(c, x, y, txt, size=5.2, col=MUTED, track=0.9):
    c.saveState()
    c.setFont('Mono', size)
    c.setFillColor(col)
    adv = 0.0
    for ch in txt:
        c.drawString(x + adv, y, ch)
        adv += pdfmetrics.stringWidth(ch, 'Mono', size) + track
    c.restoreState()
    return adv


def mono_w(txt, size, track=0.9):
    return sum(pdfmetrics.stringWidth(ch, 'Mono', size) + track for ch in txt) - track


# =====================================================================
# PAGE 1 — the letterhead, as it is actually used. The body stays silent.
# =====================================================================
W, H = 612.0, 792.0
ML, MR = 62.0, 62.0


def head(c, top=None):
    """The head of the sheet. Returns the y of the baseline rule."""
    top = top if top is not None else H - 56.0
    mark = 32.0
    lockup(c, ML, top - mark, mark, pt=24.0, gap=14.0)

    # clinical annotation, answering the mark across the measure
    for k, (txt, col) in enumerate([('PLAIN WEAVE', MUTED),
                                    (f'WARP {N:02d} / WEFT {N:02d}', MUTED),
                                    (f'SIGNAL AT WEFT {SIGNAL+1:02d}', ACCENT)]):
        c.saveState()
        label(c, W - MR - mono_w(txt, 5.0), top - 10.0 - k * 9.5, txt, 5.0, col)
        c.restoreState()

    # the rule — a single weft laid across the full measure,
    # interrupted where the signal crosses it
    ry = top - mark - 19.0
    c.setLineCap(0)
    c.setStrokeColor(HAIR)
    c.setLineWidth(0.8)
    c.line(ML, ry, W - MR, ry)
    c.setStrokeColor(INK)
    c.setLineWidth(0.8)
    c.line(ML, ry, ML + 132.0, ry)
    c.setStrokeColor(ACCENT)
    c.setLineWidth(2.4)
    c.line(ML, ry, ML + 40.0, ry)

    label(c, ML, ry - 13.5, '[STREET ADDRESS]   [CITY, STATE ZIP]   [PHONE]', 5.4, MUTED)
    label(c, W - MR - mono_w('LOOMI.AI', 5.4), ry - 13.5, 'LOOMI.AI', 5.4, INK)
    return ry


def foot(c, fig):
    fy = 60.0
    c.setStrokeColor(HAIR)
    c.setLineWidth(0.4)
    c.line(ML, fy + 15.0, W - MR, fy + 15.0)
    label(c, ML, fy, 'LOOMI, INC.', 4.8, MUTED)
    label(c, W - MR - mono_w(fig, 4.8), fy, fig, 4.8, MUTED)


def page_letterhead(c):
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    head(c)
    # The measure is left empty. This is where the letter falls,
    # and the silence is the point.
    foot(c, 'FIG. 01')


# =====================================================================
# PAGE 2 — the mark, studied
# =====================================================================
def page_study(c):
    c.setFillColor(PAPER)
    c.rect(0, 0, W, H, stroke=0, fill=1)

    s = 226.0
    x, y = ML + 24.0, H - 296.0
    tw, cs = _threads(s)
    draw_mark(c, x, y, s)

    label(c, x, y + s + 30.0, 'THE MARK', 7.2, INK, track=2.8)
    label(c, x, y + s + 18.0, 'PLAIN WEAVE — WEFT OVER WARP WHERE (i+j) IS EVEN', 5.0, MUTED)

    # coordinate ticks — systematic observation of an ordinary thing
    c.setStrokeColor(HAIR)
    c.setLineWidth(0.4)
    for i in range(N):
        c.line(x + cs[i], y - 11.0, x + cs[i], y - 6.0)
        c.line(x - 11.0, y + cs[i], x - 6.0, y + cs[i])
        label(c, x + cs[i] - mono_w(f'{i+1:02d}', 4.6) / 2.0, y - 20.0,
              f'{i+1:02d}', 4.6, MUTED, track=0.4)

    # the accent weft, called out
    ay = y + cs[SIGNAL]
    c.setStrokeColor(ACCENT)
    c.setLineWidth(0.4)
    c.line(x + s + 9.0, ay, x + s + 38.0, ay)
    label(c, x + s + 43.0, ay - 2.0, 'SIGNAL', 5.0, ACCENT)

    # the wordmark, given its own silence
    draw_wordmark(c, x, 238.0, 44.0)
    label(c, x, 218.0, 'OUTFIT BOLD — TRACKED −12/1000', 5.0, MUTED)

    # palette, as evidence rather than decoration
    py = 146.0
    for i, (col, nm) in enumerate([(INK, 'INK  11132B'),
                                   (ACCENT, 'LIGHT  6D5AE6'),
                                   (PAPER, 'PAPER  FBFAF8')]):
        px = x + i * 138.0
        c.setFillColor(col)
        c.rect(px, py, 24.0, 24.0, stroke=0, fill=1)
        c.setStrokeColor(HAIR)
        c.setLineWidth(0.4)
        c.rect(px, py, 24.0, 24.0, stroke=1, fill=0)
        label(c, px + 32.0, py + 9.0, nm, 5.0, MUTED)

    foot(c, 'FIG. 02')


out = 'Loomi-Letterhead.pdf'
c = rl_canvas.Canvas(out, pagesize=(W, H))
page_letterhead(c)
c.showPage()
page_study(c)
c.showPage()
c.save()
print('wrote', out)

# ---- the lockup alone, trimmed to its own bounds, for the letter ----
# Drawn large and rasterised down, so it stays crisp at any print size.
MS, PT, GP = 132.0, 99.0, 58.0
LW = MS + GP + wordmark_width(PT)
lc = rl_canvas.Canvas('lockup.pdf', pagesize=(LW, MS))
# on white — this one sits on the letter, not on the letterhead's paper tone
lockup_bg = HexColor('#FFFFFF')
_orig = draw_mark
def draw_mark(c, x, y, size, **kw):            # noqa: F811 — bind the ground
    kw.setdefault('bg', lockup_bg)
    return _orig(c, x, y, size, **kw)
lockup(lc, 0, 0, MS, pt=PT, gap=GP)
lc.showPage()
lc.save()
print(f'wrote lockup.pdf  ({LW:.0f} x {MS:.0f} pt)')

# ---- the full head band: lockup + the two-tone rule, drawn as one
# image so the letter carries the real rule, not a border approximation.
# Content measure of the letter = 12240 - 1240 - 1240 DXA = 488 pt.
BW = 488.0
BM = 32.0                      # mark size on the letter
BPT = BM * 0.75
BGP = BM * 0.4375
RY = 12.0                      # rule sits this far below the mark's foot
BH = BM + RY + 2.0
S = 4.0                        # draw at 4x, rasterise down — crisper terminals

bc = rl_canvas.Canvas('band.pdf', pagesize=(BW * S, BH * S))
bc.scale(S, S)
lockup(bc, 0, RY + 2.0, BM, pt=BPT, gap=BGP)
ry = 2.0
bc.setLineCap(0)
bc.setStrokeColor(HAIR)
bc.setLineWidth(0.8)
bc.line(0, ry, BW, ry)
bc.setStrokeColor(INK)
bc.line(0, ry, 132.0, ry)
bc.setStrokeColor(ACCENT)
bc.setLineWidth(2.4)
bc.line(0, ry, 40.0, ry)
bc.showPage()
bc.save()
draw_mark = _orig
print(f'wrote band.pdf  ({BW:.0f} x {BH:.0f} pt)')
