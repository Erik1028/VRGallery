"""The small icon has to survive being small.

NOTE ON THIS FILE'S NAME: it sorts after test_glass.py on purpose. See the note
at the top of tests/test_tag_suggestions.py for the landmine that requires.

The small .ico entries have carried three cameras. First the one lifted out of
the logo artwork: a good drawing with eight separate elements -- body, top plate,
viewfinder hump, four lens rings, a red dot -- which at 16 px rendered into nine
pixels by seven and read as an orange smudge. Then a white stroke camera, which
read cleanly and looked like a toolbar glyph. Now a compact camera drawn in the
manner of Mixtape's cassette icon, so the two apps sit together: a black body, a
blue-to-purple band, a white-ringed lens, on a gradient tile.

These tests are about what survives at the size Windows draws, and they are
calibrated to THIS mark. It is a dark shape on a bright tile, so what carries it
at 16 px is the dark silhouette, not white ink -- the white-stroke camera's tests
counted white pixels, and this mark has almost none at 16 px by design: its
white ring is one pixel there and blends to grey. It becomes a clean white ring
from 32 px up, and that is tested where it holds. A future mark in another
scheme needs its own numbers.
"""
import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("PIL")

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICO = os.path.join(ROOT, "assets", "VRGallery.ico")

pytestmark = pytest.mark.skipif(not os.path.exists(ICO),
                                reason="built assets are not in the checkout")


def entry(size):
    ico = Image.open(ICO)
    ico.size = (size, size)
    return ico.convert("RGBA")


def lum(img):
    """Luminance of every opaque pixel."""
    return [sum(p[:3]) / 3 for p in img.getdata() if p[3] > 200]


def dark(img, ceil=45):
    """The camera body: nothing on the tile is anywhere near this dark."""
    return sum(1 for v in lum(img) if v < ceil)


def transitional(img, lo=45, hi=90):
    """Pixels between the body and the tile -- the ones that make an edge soft."""
    return sum(1 for v in lum(img) if lo <= v < hi)


def white(img, floor=210):
    return sum(1 for v in lum(img) if v >= floor)


# ------------------------------------------------------------- the container

def test_the_icon_carries_every_size_windows_asks_for():
    ico = Image.open(ICO)
    assert set(ico.info["sizes"]) >= {(256, 256), (128, 128), (64, 64),
                                      (48, 48), (32, 32), (24, 24), (16, 16)}


def test_the_big_entries_are_a_different_drawing_from_the_small_ones():
    """A .ico may hold a different picture per size and this one does: the
    wordmark is unreadable mush below 128, so the small entries drop it and
    carry the mark alone. One rescaled drawing would lose that."""
    big = entry(256).resize((64, 64), Image.LANCZOS)
    small = entry(64)
    diff = sum(1 for y in range(64) for x in range(64)
               if big.getpixel((x, y)) != small.getpixel((x, y)))
    assert diff > 64 * 64 * 0.3, (
        "the 64 px entry looks like a scaled-down 256: the sizes are no longer "
        "drawn separately")


# --------------------------------------------------------------- the legibility

# measured on the shipped icon: 56 / 134 / 257 dark pixels. The floors sit about
# a quarter below, so ordinary drift passes and a mark that stops resolving,
# shrinks inside its tile or goes grey does not.
@pytest.mark.parametrize("size, floor", [(16, 40), (24, 100), (32, 190)])
def test_the_silhouette_holds_at_small_sizes(size, floor):
    got = dark(entry(size))
    assert got >= floor, (
        f"only {got} pixels of the {size} px icon are dark enough to be the "
        f"camera body; below {floor} it stops reading as a shape")


def test_the_body_has_an_edge_not_a_blur():
    """The signature of a mark drawn on fractions of a pixel is not too little
    ink but a wide band of in-between pixels. At 16 px the body must outweigh
    the soft edge around it (56 against 35 when measured)."""
    img = entry(16)
    assert dark(img) > transitional(img), (
        f"at 16 px: {dark(img)} dark pixels against {transitional(img)} in-between")


def test_the_mark_fills_its_tile():
    """The first camera occupied 62% of the square: at 16 px, nine pixels by
    seven inside a wide empty border."""
    img = entry(16)
    rows = [y for y in range(16)
            if any(img.getpixel((x, y))[3] > 200 and sum(img.getpixel((x, y))[:3]) / 3 < 45
                   for x in range(16))]
    assert len(rows) >= 8, f"the body only spans {len(rows)} of 16 rows"


@pytest.mark.parametrize("size, floor", [(32, 8), (48, 30)])
def test_the_lens_ring_is_white_where_it_can_be(size, floor):
    """The white ring is the cassette's white hubs, and the one bright thing on
    the body. From 32 px it has room to stay white (15 and 62 measured); below
    that it is one pixel and blends, which is why it is not asked for there."""
    got = white(entry(size))
    assert got >= floor, f"{got} white pixels at {size} px: the lens ring has gone grey"


# ------------------------------------------------------- the two stay one mark

def test_the_in_app_logo_is_the_icon(app_offscreen):
    """logo_pixmap prefers the shipped PNG and falls back to drawing the mark
    when the assets are missing. They used to be different marks entirely -- the
    fallback drew a chat balloon. Both now come from icons.app_mark_svg, and
    rendered side by side they agree to within a rounding error (1.0 / 255
    measured; the icon before this one differs by 78)."""
    from vrgallery import icons
    q = icons._drawn_logo(64, 1.0).toImage()
    q = q.convertToFormat(q.Format.Format_RGBA8888)
    drawn = Image.frombytes("RGBA", (64, 64), q.constBits().tobytes())
    a, b = drawn.resize((32, 32)), entry(64).resize((32, 32))
    mad = sum(abs(x - y) for pa, pb in zip(a.getdata(), b.getdata())
              for x, y in zip(pa[:3], pb[:3])) / (32 * 32 * 3)
    assert mad < 8, f"the in-app logo and the shipped icon differ by {mad:.1f}/255"


def test_the_generator_draws_the_mark_without_a_screen():
    """make_icon.py runs on a build box. It needs Qt to rasterise the mark, and
    Qt refuses to start without a platform plugin."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_mk", os.path.join(ROOT, "tools", "make_icon.py"))
    mk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mk)
    img = mk._mark(64)
    assert img.size == (64, 64)
    assert any(px[3] > 0 for px in img.getdata()), "the mark rendered empty"


@pytest.fixture()
def app_offscreen():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])
