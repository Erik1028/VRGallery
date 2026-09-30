"""The Windows 95 look.

Settings > Appearance > Look: Modern | Windows 95 -- the switch Mixtape, Erik's
music app, has, asked for here too (2026-09-30). Like Mixtape's it is applied
once, at start-up, before a single widget is built, and a change takes effect
after a restart: it reaches past the stylesheet into the style engine, the
font and a few painting primitives, none of which can be swapped under a
window that is already standing.

What makes the look:

  * Qt's own "Windows" style draws the controls: raised and sunken 3D edges,
    scroll bars with arrow buttons on a dithered track, blocky progress bars,
    the dotted tree. The stylesheet stays off them -- qss() gives no button,
    field or scroll bar a background or a border -- because one such rule and
    Qt draws that control itself instead of asking the style.
  * One palette of its own, the 1995 one: face grey, white fields, navy
    selection. The Modern look's theme and accent stay saved for its return.
  * Microsoft Sans Serif 8 pt, unsmoothed: what Windows 95's MS Sans Serif is
    on a modern system, and what Mixtape draws with.
  * Square corners. The app asks for rounded shapes in three ways --
    QPainterPath.addRoundedRect, QPainter.drawRoundedRect and border-radius in
    a stylesheet -- and in this look all three give a plain rectangle. That is
    done at the three entry points (see _square_everything) rather than at the
    sixty call sites, which would have to be kept square one by one forever.
  * The window of 1995: a navy caption with the small icon, a bold white title
    and three bevelled 16 x 14 buttons; a 3D frame round the window; a white
    sunken tree for the navigation; a status bar with sunken panels along the
    bottom.
  * 16 x 16 pixel icons in the sixteen VGA colours. Home, Photos, Folder, the
    film strip, the person, the chart, the computer and the sliders are
    Mixtape's own (ClassicIcons.cs); the heart, clock, star, album, globe,
    people and recycle bin are drawn to match.
"""
import re

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPixmap, QPen
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QSizeGrip,
                               QStyledItemDelegate, QTreeWidget, QTreeWidgetItem, QWidget)

FACE = "#c0c0c0"      # COLOR_3DFACE
LIGHT = "#dfdfdf"     # COLOR_3DLIGHT
HI = "#ffffff"        # COLOR_3DHILIGHT
SHADOW = "#808080"    # COLOR_3DSHADOW
DARK = "#000000"      # COLOR_3DDKSHADOW
NAVY = "#000080"      # COLOR_HIGHLIGHT and the active caption
INFO = "#ffffe1"      # COLOR_INFOBK, the tooltip yellow

FONT_FAMILY = "Microsoft Sans Serif"
FONT_PT = 8

# style.PAL while this look is on. Hover is the face itself: nothing in 1995
# lit up under the pointer.
PAL = {
    "bg": FACE, "sidebar": FACE, "surface": FACE, "surface2": FACE, "hover": FACE,
    "border": SHADOW, "border2": SHADOW, "text": DARK, "dim": "#000000",
    "faint": "#404040", "star": "#808000", "danger": "#800000", "ok": "#008000",
}
ACCENT = {"a": NAVY, "b": NAVY, "label": "Navy"}

CAPTION_H = 18
# a heading: 12 pt was 16 px in 1995, but Microsoft Sans Serif carries embedded
# bitmaps at 15 and 16 px that have no bold, and unsmoothed there a bold heading
# comes out regular. 17 px is the nearest size that is really bold.
HEADING_PX = 17
STATUS_H = 22


# ------------------------------------------------------------ switching it on

def apply(app):
    """Style, palette, font and the square corners, before anything is built."""
    app.setStyle("Windows")
    pal = QPalette()
    for grp in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
        for role, colour in ((QPalette.Window, FACE), (QPalette.Button, FACE),
                             (QPalette.Base, HI), (QPalette.AlternateBase, FACE),
                             (QPalette.Light, HI), (QPalette.Midlight, LIGHT),
                             (QPalette.Dark, SHADOW), (QPalette.Mid, SHADOW),
                             (QPalette.Shadow, DARK), (QPalette.Highlight, NAVY),
                             (QPalette.HighlightedText, HI), (QPalette.ToolTipBase, INFO),
                             (QPalette.ToolTipText, DARK), (QPalette.Link, "#0000ff"),
                             (QPalette.PlaceholderText, SHADOW)):
            pal.setColor(grp, role, QColor(colour))
        ink = SHADOW if grp == QPalette.Disabled else DARK
        for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
            pal.setColor(grp, role, QColor(ink))
    app.setPalette(pal)
    app.setFont(font())
    _square_everything()
    global _CAPTIONS
    _CAPTIONS = _Captions(app)
    app.installEventFilter(_CAPTIONS)


_CAPTIONS = None


def font(bold=False, pt=FONT_PT):
    f = QFont(FONT_FAMILY)
    f.setPointSize(pt)
    f.setBold(bold)
    # a smoothed MS Sans Serif is neither one decade nor the other
    f.setStyleStrategy(QFont.NoAntialias)
    return f


_PATCHED = False


def _square_everything():
    """Rounded rects become rects; stylesheets lose their radii, and their
    type sizes fold onto the two sizes of 1995 (8 pt, and 12 pt for a heading),
    the way Mixtape's classic font does it."""
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    def add_rounded(self, *a, **_kw):
        if len(a) >= 6 and not isinstance(a[0], (QRect, QRectF)):
            return QPainterPath.addRect(self, QRectF(a[0], a[1], a[2], a[3]))
        return QPainterPath.addRect(self, QRectF(a[0]))

    def draw_rounded(self, *a, **_kw):
        if len(a) >= 6 and not isinstance(a[0], (QRect, QRectF)):
            return QPainter.drawRect(self, QRectF(a[0], a[1], a[2], a[3]))
        return QPainter.drawRect(self, QRectF(a[0]))

    QPainterPath.addRoundedRect = add_rounded
    QPainter.drawRoundedRect = draw_rounded

    real_set = QWidget.setStyleSheet

    def set_style_sheet(self, css):
        return real_set(self, classic_css(css))

    QWidget.setStyleSheet = set_style_sheet

    # the pointing hand is Windows 98's web page; 1995 pointed at everything
    # with the arrow
    real_cursor = QWidget.setCursor

    def set_cursor(self, c):
        if c == Qt.PointingHandCursor:
            c = Qt.ArrowCursor
        return real_cursor(self, c)

    QWidget.setCursor = set_cursor


_RADIUS = re.compile(r"border(-top|-bottom)?(-left|-right)?-radius\s*:\s*[^;}]+;?")
_SPACING = re.compile(r"letter-spacing\s*:\s*[^;}]+;?")
_SIZE = re.compile(r"font-size\s*:\s*(\d+(?:\.\d+)?)px")


def classic_css(css):
    """A stylesheet written for the Modern look, in the Windows 95 one."""
    if not css:
        return css
    css = _RADIUS.sub("", css)
    css = _SPACING.sub("", css)
    return _SIZE.sub(lambda m: "font-size: %dpx" % (HEADING_PX if float(m.group(1)) >= 17 else 11),
                     css)


def sentence(text):
    """ "ON THIS DAY" -> "On this day", "TIME OF DAY — when..." -> "Time of day —
    when...": 1995 did not shout its captions. The words in capitals at the
    head of the caption are lowered; names that are capitals by right keep them."""
    if not text:
        return text
    words = text.split(" ")
    n = 0
    while n < len(words) and not any(ch.islower() for ch in words[n]):
        n += 1
    if n == 0 or not any(ch.isalpha() for ch in " ".join(words[:n])):
        return text
    s = " ".join(w.lower() for w in words[:n])
    s = s[:1].upper() + s[1:]
    for word, right in (("vrchat", "VRChat"), ("api", "API"), ("osc", "OSC"),
                        ("discord", "Discord"), ("quest", "Quest"), ("vr", "VR"),
                        ("gb", "GB"), ("mb", "MB")):
        s = re.sub(r"\b%s\b" % word, right, s, flags=re.IGNORECASE)
    return " ".join([s] + words[n:])


class _Captions(QObject):
    """Every caption labelled SectionLabel, in sentence case as it is first
    shown -- the lightbox's WORLD / RATING / TAGS and the rest, which are set
    once and never passed through style.caps."""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Polish and isinstance(obj, QLabel) \
                and obj.objectName() == "SectionLabel":
            t = obj.text()
            s = sentence(t)
            if s != t:
                obj.setText(s)
        return False


# ------------------------------------------------------------------ the stylesheet

def qss():
    """The app stylesheet in this look: fonts and colours only on what the
    Windows style draws, so that the style keeps drawing it."""
    return f"""
* {{ outline: none; }}
QWidget {{ color: {DARK}; font-family: '{FONT_FAMILY}'; font-size: 11px; }}
QMainWindow, #Root {{ background: {FACE}; }}
#TitleBar {{ background: {NAVY}; }}
#TitleBarText {{ color: {HI}; font-weight: bold; }}
#PageHeaderTitle {{ font-size: {HEADING_PX}px; font-weight: bold; }}
#PageHeaderSub {{ color: {DARK}; }}
#SectionLabel {{ color: {DARK}; font-weight: bold; }}
#CardTitle {{ color: {DARK}; }}
#GridStatus, #SidebarStatus {{ color: {DARK}; }}
QPushButton#PrimaryBtn {{ font-weight: bold; }}
QPushButton#DangerBtn {{ color: #800000; }}
QPushButton#LinkBtn {{
    background: transparent; border: none; color: #0000ff; text-decoration: underline;
}}
QListView, QScrollArea {{ background: transparent; border: none; }}
QLineEdit#SearchBox {{ padding-left: 20px; }}
QToolTip {{
    background: {INFO}; color: {DARK}; border: 1px solid {DARK}; padding: 1px 2px;
}}
#LightboxPanel {{ background: {FACE}; border-left: 1px solid {SHADOW}; }}
#LbTitle {{ font-weight: bold; }}
#LbDim, #LbKey, #ToastText {{ color: {DARK}; }}
"""


# -------------------------------------------------------------------- 3D edges

def bevel(p, r, kind="raised"):
    """The four-colour 3D edge of 1995 round rect `r` (a QRect).

    raised  -- a button or a window: light outside, then highlight, shadow
               and dark inside out on the far sides
    sunken  -- a field or a list: the reverse
    thin    -- a status-bar panel: one sunken pixel
    etched  -- a group box: a groove, shadow then highlight
    """
    x0, y0, x1, y1 = r.left(), r.top(), r.right(), r.bottom()

    def frame(inset, tl, br):
        a, b, c, d = x0 + inset, y0 + inset, x1 - inset, y1 - inset
        p.setPen(QPen(QColor(tl), 1))
        p.drawLine(a, b, c - 1, b)
        p.drawLine(a, b, a, d - 1)
        p.setPen(QPen(QColor(br), 1))
        p.drawLine(a, d, c, d)
        p.drawLine(c, b, c, d)

    if kind == "raised":
        frame(0, LIGHT, DARK)
        frame(1, HI, SHADOW)
    elif kind == "window":
        frame(0, LIGHT, DARK)
        frame(1, HI, SHADOW)
    elif kind == "sunken":
        frame(0, SHADOW, HI)
        frame(1, DARK, LIGHT)
    elif kind == "thin":
        frame(0, SHADOW, HI)
    elif kind == "etched":
        p.setPen(QPen(QColor(SHADOW), 1))
        p.drawRect(QRect(x0, y0, r.width() - 2, r.height() - 2))
        p.setPen(QPen(QColor(HI), 1))
        p.drawLine(x0 + 1, y0 + 1, x1 - 2, y0 + 1)
        p.drawLine(x0 + 1, y0 + 1, x0 + 1, y1 - 2)
        p.drawLine(x0, y1, x1, y1)
        p.drawLine(x1, y0, x1, y1)


def panel(p, widget, kind="raised"):
    """Fill a widget with the face and edge it: the glass of the Modern look,
    in this one (toasts, the selection bar) and the flat bars it becomes."""
    r = widget.rect()
    p.fillRect(r, QColor(FACE))
    if kind:
        bevel(p, r, kind)


class WindowFrame(QWidget):
    """The window's root: the face, and the 3D frame round the edge while the
    window is not maximised (a maximised window of 1995 had its frame off the
    screen)."""

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self.setObjectName("Root")
        self.setAttribute(Qt.WA_StyledBackground, True)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(FACE))
        if not self.win.isMaximized():
            bevel(p, self.rect(), "window")
        p.end()


class Sunken(QFrame):
    """A white well with a sunken edge -- the tree sits in one."""

    def __init__(self, kind="sunken", fill=HI, parent=None):
        super().__init__(parent)
        self._kind, self._fill = kind, fill

    def paintEvent(self, ev):
        p = QPainter(self)
        if self._fill:
            p.fillRect(self.rect(), QColor(self._fill))
        bevel(p, self.rect(), self._kind)
        p.end()
        super().paintEvent(ev)


# ---------------------------------------------------------------- pixel icons

# k black  w white  s silver  g grey  n navy  b blue  t teal  c cyan  r red
# m maroon  y yellow  o olive  e green  l lime  p purple  f fuchsia  . clear
VGA = {
    "k": (0, 0, 0), "w": (255, 255, 255), "s": (192, 192, 192), "g": (128, 128, 128),
    "n": (0, 0, 128), "b": (0, 0, 255), "t": (0, 128, 128), "c": (0, 255, 255),
    "r": (255, 0, 0), "m": (128, 0, 0), "y": (255, 255, 0), "o": (128, 128, 0),
    "e": (0, 128, 0), "l": (0, 255, 0), "p": (128, 0, 128), "f": (255, 0, 255),
}

ICONS = {
    "home": (
        "................",
        ".......kk.......",
        "......kmmk......",
        ".....kmrrmk.....",
        "....kmrrrrmk....",
        "...kmrrrrrrmk...",
        "..kmrrrrrrrrmk..",
        ".kkkkkkkkkkkkkk.",
        "..kwwwwwwwwwwk..",
        "..kwbbwwkkkkwk..",
        "..kwbbwwkmmkwk..",
        "..kwwwwwkmmkwk..",
        "..kwwwwwkmykwk..",
        "..kwwwwwkmmkwk..",
        "..kkkkkkkkkkkk..",
        "................",
    ),
    "photos": (
        "................",
        "kkkkkkkkkkkkkkkk",
        "kssssssssssssssk",
        "kskkkkkkkkkkkksk",
        "kskccccccccyycsk",
        "kskccccccccyycsk",
        "kskcccccccccccsk",
        "kskcccccecccccsk",
        "kskccceeeeccccsk",
        "kskceeeeeeeeccsk",
        "kskeeeeeeeeeeesk",
        "kskeeeeeeeeeeesk",
        "kskkkkkkkkkkkksk",
        "kssssssssssssssk",
        "kkkkkkkkkkkkkkkk",
        "................",
    ),
    "folder": (
        "................",
        "................",
        "..kkkkk.........",
        ".kwyyyyk........",
        ".kyyyyyykkkkkkk.",
        ".kwwwwwwwwwwwwok",
        ".kwyyyyyyyyyyyok",
        ".kwyyyyyyyyyyyok",
        ".kwyyyyyyyyyyyok",
        ".kwyyyyyyyyyyyok",
        ".kwyyyyyyyyyyyok",
        ".kwyyyyyyyyyyyok",
        ".koooooooooooooo",
        ".kkkkkkkkkkkkkkk",
        "................",
        "................",
    ),
    "film": (
        "................",
        "................",
        "kkkkkkkkkkkkkkkk",
        "kwkkwkkwkkwkkwkk",
        "kkkkkkkkkkkkkkkk",
        "kkcccckkcccckkkk",
        "kkcbbckkcbbckkkk",
        "kkcbbckkcbbckkkk",
        "kkcccckkcccckkkk",
        "kkkkkkkkkkkkkkkk",
        "kwkkwkkwkkwkkwkk",
        "kkkkkkkkkkkkkkkk",
        "................",
        "................",
        "................",
        "................",
    ),
    "person": (
        "................",
        "......kkkk......",
        ".....kkkkkk.....",
        ".....kwwwwk.....",
        ".....kwwwwk.....",
        ".....kwwwwk.....",
        "......kwwk......",
        ".....kkwwkk.....",
        "....knnwwnnk....",
        "...knnnnnnnnk...",
        "..knnnnnnnnnnk..",
        "..knnnnnnnnnnk..",
        "..knnnnnnnnnnk..",
        "..kkkkkkkkkkkk..",
        "................",
        "................",
    ),
    "chart": (
        "................",
        ".kkkkkkkkkkkkkk.",
        ".kwwwwwwwwwwwwk.",
        ".kwwwwwwwwrrwwk.",
        ".kwwwwwwwwrrwwk.",
        ".kwwwwwwwwrrwwk.",
        ".kwwwwwbbwrrwwk.",
        ".kwwwwwbbwrrwwk.",
        ".kwwwwwbbwrrwwk.",
        ".kwwllwbbwrrwwk.",
        ".kwwllwbbwrrwwk.",
        ".kwwllwbbwrrwwk.",
        ".kwkkkkkkkkkkwk.",
        ".kwwwwwwwwwwwwk.",
        ".kkkkkkkkkkkkkk.",
        "................",
    ),
    "computer": (
        "................",
        "..kkkkkkkkkkkk..",
        "..kssssssssssk..",
        "..kskkkkkkkksk..",
        "..ksktttttcksk..",
        "..kskttttttksk..",
        "..kskttttttksk..",
        "..kskttttttksk..",
        "..kskkkkkkkksk..",
        "..kssssssssesk..",
        "..kkkkkkkkkkkk..",
        ".....kssssk.....",
        "...kkkkkkkkkk...",
        "...kssssssssk...",
        "...kkkkkkkkkk...",
        "................",
    ),
    "sliders": (
        "................",
        "..k....k....k...",
        "..k....k....k...",
        "..k..kkkkk..k...",
        "..k..kwwwk..k...",
        "kkkkkkkkkk..k...",
        "kwwwk..k....k...",
        "kkkkk..k..kkkkk.",
        "..k....k..kwwwk.",
        "..k....k..kkkkk.",
        "..k....k....k...",
        "..k....k....k...",
        "..k....k....k...",
        "..k....k....k...",
        "................",
        "................",
    ),
    "heart": (
        "................",
        "..kkkk....kkkk..",
        ".krrrrk..krrrrk.",
        "krwwrrrkkrrrrrmk",
        "krwrrrrrrrrrrrmk",
        "krrrrrrrrrrrrrmk",
        "krrrrrrrrrrrrrmk",
        ".krrrrrrrrrrrmk.",
        "..krrrrrrrrrmk..",
        "...krrrrrrrmk...",
        "....krrrrrmk....",
        ".....krrrmk.....",
        "......krmk......",
        ".......kk.......",
        "................",
        "................",
    ),
    "clock": (
        "................",
        ".....kkkkkk.....",
        "...kkwwkkwwkk...",
        "..k.wwwwwwww.k..",
        "..kwwwwkwwwwwk..",
        ".kwwwwwkwwwwwwk.",
        ".kwwwwwkwwwwwwk.",
        ".kkwwwwkwwwwwkk.",
        ".kkwwwwknnnnwkk.",
        ".kwwwwwwwwwwwwk.",
        ".kwwwwwwwwwwwwk.",
        "..kwwwwwwwwwwk..",
        "..kkwwwwwwwwkk..",
        "...kkwwkkwwkk...",
        ".....kkkkkk.....",
        "................",
    ),
    "star": (
        ".......kk.......",
        ".......kk.......",
        "......kyyk......",
        "......kyyk......",
        ".....kyyyyk.....",
        "kkkkkkywyyykkkkk",
        "kyyyyywyyyyyyyok",
        ".kyyyyyyyyyyyok.",
        "..kyyyyyyyyyok..",
        "...kyyyyyyyok...",
        "...kyyyyyyyyk...",
        "..kyyyykkyyyok..",
        "..kyyykk.kkyyk..",
        ".kyyk......kyok.",
        ".kkk........kkk.",
        "................",
    ),
    "album": (
        "................",
        ".kkkkkkkkkkkkkk.",
        ".kpmmmmmmmmmmmk.",
        ".kpmkkkkkkkkkmk.",
        ".kpmkcccccyykmk.",
        ".kpmkcccccyykmk.",
        ".kpmkccccccckmk.",
        ".kpmkceeeecckmk.",
        ".kpmkeeeeeeekmk.",
        ".kpmkkkkkkkkkmk.",
        ".kpmmmmmmmmmmmk.",
        ".kpmmmwwwwwmmmk.",
        ".kpmmmwwwwwmmmk.",
        ".kpmmmmmmmmmmmk.",
        ".kkkkkkkkkkkkkk.",
        "................",
    ),
    "globe": (
        "................",
        ".....kkkkkk.....",
        "...kkbbbbcbkk...",
        "..kkbeeebbcbkk..",
        "..kbeeeeebbebk..",
        ".kbeeeebbbbbebk.",
        ".kbeeebbbbbbbbk.",
        ".kbbeebbbbbbbbk.",
        ".kbbbbbbbeeeebk.",
        ".kbbbbbbeeeeebk.",
        ".kbbbbbbeeeebbk.",
        "..kbbbbbbeebbk..",
        "..kkbbbbbbbbkk..",
        "...kkbbbbbbkk...",
        ".....kkkkkk.....",
        "................",
    ),
    "people": (
        "................",
        "..kkkk..........",
        ".kkkkkk..kkkk...",
        ".kwwwwk.kkkkkk..",
        ".kwwwwk.kwwwwk..",
        "..kwwk..kwwwwk..",
        ".kkwwkk.kwwwwk..",
        "kttwwttkkkwwkk..",
        "kttttttkknwwnnk.",
        "ktttttkknnnnnnnk",
        "kttttknnnnnnnnnk",
        "kttttknnnnnnnnnk",
        "kkkkkknnnnnnnnnk",
        ".....kkkkkkkkkkk",
        "................",
        "................",
    ),
    "recycle": (
        "................",
        "...kkkkkkkkkk...",
        "..kwwwwwwwwwwk..",
        "..kkkkkkkkkkkk..",
        "..kswgswgswgsk..",
        "..kswgswgswgsk..",
        "...kwgswgswgk...",
        "...kwgseeswgk...",
        "...kwgeeeewgk...",
        "...kwgseeswgk...",
        "...kwgswgswgk...",
        "...kwgswgswgk...",
        "....kgswgswk....",
        "....kgswgswk....",
        "....kkkkkkkk....",
        "................",
    ),
}

# the navigation's keys, onto the pictures
NAV_ICONS = {
    "home": "home", "all": "photos", "favs": "heart", "memories": "clock",
    "moments": "star", "albums": "album", "sessions": "film", "worlds": "globe",
    "people": "people", "avatars": "person", "stats": "chart", "cleanup": "recycle",
    "settings": "sliders",
}

# the Modern look's line icons that have a 1995 picture
FEATHER = {
    "image": "photos", "film": "film", "hard-drive": "computer", "database": "computer",
    "calendar": "clock", "clock": "clock", "globe": "globe", "users": "people",
    "user": "person", "user-check": "person", "heart": "heart", "award": "star",
    "star": "star", "layers": "album", "chart": "chart", "zap": "recycle", "home": "home",
    "folder": "folder", "settings": "sliders",
}

_ICON_CACHE = {}


def icon(name, scale=1, dpr=1.0):
    """One of the pixel icons, `scale` screen pixels to a pixel, never smoothed:
    a smoothed pixel icon is neither one thing nor the other."""
    n = max(1, int(round(scale * dpr)))
    key = (name, n, dpr)
    pm = _ICON_CACHE.get(key)
    if pm is None:
        rows = ICONS.get(name) or ICONS["folder"]
        pm = QPixmap(16 * n, 16 * n)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                rgb = VGA.get(ch)
                if rgb:
                    p.fillRect(x * n, y * n, n, n, QColor(*rgb))
        p.end()
        pm.setDevicePixelRatio(n / float(scale))
        _ICON_CACHE[key] = pm
    return pm


# the caption buttons' glyphs, black pixels
GLYPHS = {
    "min": ("......", "......", "......", "......", "......", "kkkkkk", "kkkkkk"),
    "max": ("kkkkkkkkk", "kkkkkkkkk", "k.......k", "k.......k", "k.......k",
            "k.......k", "k.......k", "k.......k", "kkkkkkkkk"),
    "restore": ("..kkkkkk", "..kkkkkk", "..k....k", "kkkkkk.k", "kkkkkk.k",
                "k....kkk", "k....k..", "k....k..", "kkkkkk.."),
    "close": ("kk....kk", ".kk..kk.", "..kkkk..", "...kk...", "..kkkk..",
              ".kk..kk.", "kk....kk"),
}


class CaptionButton(QAbstractButton):
    """A 16 x 14 caption button of 1995: raised, sunken while held, its glyph
    stepping a pixel down and right as it goes in."""

    def __init__(self, glyph, tip, parent=None):
        super().__init__(parent)
        self.glyph = glyph
        self.setFixedSize(16, 14)
        self.setToolTip(tip)
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, _ev):
        p = QPainter(self)
        down = self.isDown()
        p.fillRect(self.rect(), QColor(FACE))
        if down:
            bevel(p, self.rect(), "sunken")
        else:
            bevel(p, self.rect(), "raised")
        rows = GLYPHS[self.glyph]
        gw, gh = len(rows[0]), len(rows)
        x0 = (self.width() - gw) // 2 + (1 if down else 0)
        y0 = (self.height() - gh) // 2 + (1 if down else 0)
        for y, row in enumerate(rows):
            for x, ch in enumerate(row):
                if ch == "k":
                    p.fillRect(x0 + x, y0 + y, 1, 1, QColor(DARK))
        p.end()


# ------------------------------------------------------------------ navigation

class _NavDelegate(QStyledItemDelegate):
    """A tree row the 1995 way: the icon, then the name, and only the NAME
    in navy when it is picked, not the whole width of the tree."""

    def sizeHint(self, opt, idx):
        return QSize(super().sizeHint(opt, idx).width() + 8, 18)

    def paint(self, p, opt, idx):
        from PySide6.QtWidgets import QStyle
        r = opt.rect
        pm = idx.data(Qt.DecorationRole)
        if isinstance(pm, QPixmap):
            p.drawPixmap(QPoint(r.x() + 1, r.y() + (r.height() - 16) // 2), pm)
        text = idx.data(Qt.DisplayRole) or ""
        fm = opt.fontMetrics
        tr = QRect(r.x() + 20, r.y() + 1, fm.horizontalAdvance(text) + 5, r.height() - 2)
        picked = bool(opt.state & QStyle.State_Selected)
        if picked:
            p.fillRect(tr, QColor(NAVY))
        p.setPen(QColor(HI if picked else DARK))
        p.setFont(opt.font)
        p.drawText(tr.adjusted(2, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, text)
        if picked and opt.state & QStyle.State_HasFocus:
            pen = QPen(QColor(HI), 1, Qt.DotLine)
            p.setPen(pen)
            p.drawRect(tr.adjusted(0, 0, -1, -1))


class NavTree(QTreeWidget):
    """The navigation, as Explorer's folder tree: Home, then three folders of
    pages, then Settings."""

    picked = Signal(str)

    GROUPS = (("Library", ("all", "favs", "memories", "moments", "albums")),
              ("VRChat", ("sessions", "worlds", "people", "avatars")),
              ("Tools", ("stats", "cleanup")))

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setIndentation(16)
        self.setFrameShape(QFrame.NoFrame)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setItemDelegate(_NavDelegate(self))
        self.setVerticalScrollMode(QTreeWidget.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._items = {}

        def leaf(key, parent_item=None):
            it = QTreeWidgetItem([labels.get(key, key)])
            it.setData(0, Qt.DecorationRole, icon(NAV_ICONS.get(key, "folder")))
            it.setData(0, Qt.UserRole, key)
            if parent_item is None:
                self.addTopLevelItem(it)
            else:
                parent_item.addChild(it)
            self._items[key] = it

        leaf("home")
        for name, keys in self.GROUPS:
            g = QTreeWidgetItem([name])
            g.setData(0, Qt.DecorationRole, icon("folder"))
            g.setFlags(Qt.ItemIsEnabled)            # a folder is not a page
            self.addTopLevelItem(g)
            for k in keys:
                leaf(k, g)
            g.setExpanded(True)
        leaf("settings")
        self.itemClicked.connect(self._on_click)
        self.currentItemChanged.connect(self._on_current)

    def _on_click(self, item, _col):
        key = item.data(0, Qt.UserRole)
        if key is None:
            item.setExpanded(not item.isExpanded())

    def _on_current(self, cur, _prev):
        key = cur.data(0, Qt.UserRole) if cur is not None else None
        if key:
            self.picked.emit(key)

    def select(self, key):
        """Show `key` as the open page without asking to open it again."""
        it = self._items.get(key)
        self.blockSignals(True)
        try:
            if it is not None:
                self.setCurrentItem(it)
            else:
                self.clearSelection()
        finally:
            self.blockSignals(False)



# ------------------------------------------------------------------ status bar

class StatusPanel(QLabel):
    """One sunken panel of the status bar."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setContentsMargins(4, 0, 4, 0)
        self.setMinimumWidth(0)

    def paintEvent(self, ev):
        p = QPainter(self)
        bevel(p, self.rect(), "thin")
        p.end()
        super().paintEvent(ev)


class StatusBar(QWidget):
    """Along the bottom of the window: sunken panels, and the grip in the
    corner that resizes the window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(STATUS_H)
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 2, 0, 0)
        self.lay.setSpacing(2)

    def add(self, w, stretch=0):
        self.lay.addWidget(w, stretch)

    def add_grip(self, win):
        grip = QSizeGrip(win)
        grip.setFixedSize(14, 14)
        self.lay.addWidget(grip, 0, Qt.AlignBottom | Qt.AlignRight)
        return grip
