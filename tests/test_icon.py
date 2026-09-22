"""The small icon has to survive being small.

NOTE ON THIS FILE'S NAME: it sorts after test_glass.py on purpose. See the note
at the top of tests/test_tag_suggestions.py for the landmine that requires.

The icon shipped for a long time with the camera lifted straight out of the logo
artwork, which is a good drawing carrying eight separate elements: body, top
plate, viewfinder hump, four lens rings, a red dot. At 16 px it rendered into
nine pixels by seven and every one of those elements landed on a fraction of a
pixel, so the antialiaser split them all. The result was an orange smudge.

What replaced it is two shapes and a heavy stroke: 54 pixels at full strength
against 22 half-lit ones at 16 px.

A NOTE ON THE MEASUREMENT, because it is easy to read more into it than it can
carry. "Full strength" here means luminance >= 210, and that favours a white
mark by construction -- the old camera is peach and yellow and scores 0 at this
threshold at 16 px, which says it is not white, not that it is illegible. What
made it illegible is visible in the pixel grid instead: one-pixel walls, a lens
drawn as a one-pixel ring around a one-pixel hole, and a bottom rail that landed
on a fraction of a pixel and came out dim along its whole length.

So these floors are a regression guard for THIS mark, calibrated to what it
actually scores, and not a general law about icons. A future camera in another
colour would need its own numbers.
"""
import os

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("PIL")

from PIL import Image

ICO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "assets", "VRGallery.ico")

pytestmark = pytest.mark.skipif(not os.path.exists(ICO),
                                reason="built assets are not in the checkout")


def entry(size):
    ico = Image.open(ICO)
    ico.size = (size, size)
    return ico.convert("RGBA")


def ink(img, floor=210):
    """Pixels at or above `floor` luminance -- the ones that actually read."""
    return sum(1 for y in range(img.height) for x in range(img.width)
               if sum(img.getpixel((x, y))[:3]) / 3 >= floor)


def half_lit(img, lo=160, hi=210):
    return sum(1 for y in range(img.height) for x in range(img.width)
               if lo < sum(img.getpixel((x, y))[:3]) / 3 < hi)


# ------------------------------------------------------------- the container

def test_the_icon_carries_every_size_windows_asks_for(_=None):
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

# measured on the shipped icon: 54 / 81 / 179. The floors sit about a third
# below, so ordinary drift passes and a mark that stops resolving does not.
@pytest.mark.parametrize("size, floor", [(16, 35), (24, 55), (32, 120)])
def test_the_mark_still_resolves_at_small_sizes(size, floor):
    """Enough of the camera lands at full strength to hold an edge.

    Thinning the stroke or shrinking the mark inside the tile both show up here,
    because both move ink out of whole pixels and into fractions of them.
    """
    got = ink(entry(size))
    assert got >= floor, (
        f"only {got} pixels of the {size} px icon are at full strength; below "
        f"{floor} the mark stops reading as anything")


def test_it_is_not_mostly_half_lit_pixels():
    """The failure mode has a signature: not too little ink, but ink spread
    across pixels that are each half-on. That is what soft looks like.

    Only at 16 px. At 24 the mark legitimately has more half-lit pixels than
    solid ones (81 against 89) because a rounded body at that size has a lot of
    curve to antialias, and the same assertion there would be asking the
    engine not to do its job.
    """
    img = entry(16)
    solid, soft = ink(img), half_lit(img)
    assert solid > soft, (
        f"at 16 px the icon has {solid} solid pixels against {soft} half-lit "
        f"ones: the mark is being drawn on fractions of a pixel")


def test_the_mark_is_not_crowded_into_a_corner_of_the_tile():
    """It should use the tile. The old camera occupied 62% of the square and at
    16 px that is nine pixels by seven with a wide empty border."""
    img = entry(16)
    rows = [y for y in range(16)
            if any(sum(img.getpixel((x, y))[:3]) / 3 > 160 for x in range(16))]
    assert len(rows) >= 9, f"the mark only uses {len(rows)} of 16 rows"


# ------------------------------------------------------- the two stay one mark

def test_the_in_app_logo_draws_the_same_camera_as_the_icon(tmp_path):
    """logo_pixmap prefers the shipped PNG and falls back to a drawn tile when
    the assets are missing -- running from a source checkout, say. The two used
    to be different marks entirely: the fallback drew a chat balloon."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from vrgallery import icons

    assert "circle" in icons.APP_TILE_SVG and "stroke-width" in icons.APP_TILE_SVG
    pm = icons._drawn_logo(64, 1.0)
    assert not pm.isNull()
    img = pm.toImage()
    white = sum(1 for y in range(64) for x in range(64)
                if img.pixelColor(x, y).alpha() > 200
                and img.pixelColor(x, y).lightness() > 200)
    assert white > 150, (
        f"the drawn fallback has {white} light pixels: it is not the camera")


def test_the_generator_can_draw_the_camera_without_a_screen():
    """make_icon.py runs on a build box. It needs Qt to rasterise the mark, and
    Qt refuses to start without a platform plugin."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_mk", os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "tools", "make_icon.py"))
    mk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mk)
    img = mk._camera(64)
    assert img.size == (64, 64)
    assert any(px[3] > 0 for px in img.getdata()), "the camera rendered empty"
