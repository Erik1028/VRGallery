"""Build the app icon from the logo artwork.

A .ico holds several sizes, and they do not have to be the same drawing. The
logo has "VR GALLERY" set into it, which is unreadable mush at 16 px and turns
the whole tile to noise, so the small entries get the app mark instead -- the
compact camera from vrgallery/icons.py -- while the large ones keep the full logo.
That is what an icon this shape needs to stay recognisable in the tray.

    .venv\\Scripts\\python.exe tools\\make_icon.py [source.png]
"""
import io
import os
import struct
import sys

from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# the artwork has lived in both places; the first that exists is used
DEFAULT_SRCS = [os.path.join(os.path.expanduser("~"), "Desktop", *p) for p in
                (("VRGallery.png",), ("Images", "VRGallery.png"))]
OUT_ICO = os.path.join(HERE, "assets", "VRGallery.ico")
OUT_PNG = os.path.join(HERE, "assets", "VRGallery.png")

FULL_AT = (256, 128)                    # sizes that keep the wordmark
MARK_AT = (64, 48, 32, 24, 16)          # below 128 the words are mush


def _trimmed(src):
    box = src.getchannel("A").getbbox()
    return src.crop(box) if box else src


def full_tile(src, size):
    """The whole logo, fitted into a square with a little air around it."""
    art = _trimmed(src)
    inner = int(size * 0.94)
    art = art.copy()
    art.thumbnail((inner, inner), Image.LANCZOS)
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    tile.paste(art, ((size - art.width) // 2, (size - art.height) // 2), art)
    return tile


# The small entries carry the app mark from vrgallery/icons.py -- the one copy of
# the drawing, so this .ico and the logo inside the app are the same picture.
# It went through two versions before this: the camera lifted out of the logo
# artwork, which at 16 px was nine pixels by seven with eight elements in it and
# read as an orange smudge, then a white stroke camera that read cleanly but
# looked like a toolbar glyph. Erik picked this one from three drawn in the
# manner of Mixtape's cassette, so the two apps sit together as a family.
sys.path.insert(0, HERE)


def _mark(px, detail=True):
    """vrgallery.icons.app_mark_svg rendered to a transparent RGBA image."""
    from PySide6.QtCore import QByteArray, QRectF
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication

    if QApplication.instance() is None:
        # A build box has no display, and QApplication refuses to start without
        # a platform plugin. Nothing here is ever shown, so ask for the one that
        # needs no screen -- but only when we are the ones creating it, or this
        # would override the platform of a live app that imported the tool.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        QApplication([])
    from vrgallery.icons import app_mark_svg

    r = QSvgRenderer(QByteArray(app_mark_svg(detail).encode()))
    img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    r.render(p, QRectF(0, 0, px, px))
    p.end()
    img = img.convertToFormat(QImage.Format_RGBA8888)
    return Image.frombytes("RGBA", (img.width(), img.height()),
                           img.constBits().tobytes())


def mark_tile(_src, size):
    """The app mark at one .ico size: the detailed drawing from 64 up, the small
    one below, each rendered at 8x and brought down, so the edges come out of a
    real downsample rather than the renderer's own coverage at 16 px."""
    return _mark(max(256, size * 8), detail=size >= 64).resize((size, size),
                                                              Image.LANCZOS)


def write_ico(path, tiles):
    """ICO with a PNG payload per entry, so each size keeps its own drawing.

    Pillow's own ICO writer takes one image and rescales it, which is exactly
    what we are avoiding here.
    """
    blobs = []
    for tile in tiles:
        buf = io.BytesIO()
        tile.save(buf, format="PNG")
        blobs.append(buf.getvalue())
    header = struct.pack("<HHH", 0, 1, len(tiles))
    offset = len(header) + 16 * len(tiles)
    entries, body = b"", b""
    for tile, blob in zip(tiles, blobs):
        w = 0 if tile.width >= 256 else tile.width
        h = 0 if tile.height >= 256 else tile.height
        entries += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
        body += blob
    with open(path, "wb") as f:
        f.write(header + entries + body)


def main(argv):
    src_path = argv[1] if len(argv) > 1 else next(
        (p for p in DEFAULT_SRCS if os.path.exists(p)), DEFAULT_SRCS[0])
    if not os.path.exists(src_path):
        print(f"no artwork at {src_path}")
        return 1
    src = Image.open(src_path).convert("RGBA")
    os.makedirs(os.path.dirname(OUT_ICO), exist_ok=True)

    tiles = [full_tile(src, s) for s in FULL_AT] + [mark_tile(src, s) for s in MARK_AT]
    write_ico(OUT_ICO, tiles)
    full_tile(src, 512).save(OUT_PNG)             # for the About box and the README
    mark_tile(src, 256).save(os.path.join(HERE, "assets", "VRGallery-mark.png"))

    got = Image.open(OUT_ICO)
    print(f"{OUT_ICO}  {os.path.getsize(OUT_ICO):,} bytes")
    print("  sizes:", sorted(got.info.get("sizes", []), reverse=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
