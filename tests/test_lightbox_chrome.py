"""With a photo open, the window still has a title bar you can take hold of.

NOTE ON THIS FILE'S NAME: it sorts after test_glass.py on purpose. See the note
at the top of tests/test_tag_suggestions.py for the landmine that requires.

The main window is frameless and supplies its own chrome, widgets.TitleBar. The
lightbox is a child widget that covers the WHOLE window, that bar included, and
its own top row was a bare QHBoxLayout -- a layout has no widget to receive a
mouse press. So while a photo was open the window could not be dragged, could
not be double-clicked to maximise, and could not be thrown at a screen edge to
snap. Nothing looked broken; the title bar simply stopped answering.

The row is a _TitleStrip now. The two things that can quietly undo that are the
row going back to a bare layout, and the strip swallowing presses that belong to
the buttons sitting in it -- so both are pinned down here.
"""
import os

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QPushButton

from vrgallery import paths


@pytest.fixture(scope="module")
def app():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def box(app, tmp_path):
    """A main window with the lightbox open on one photo."""
    paths.set_appdir(str(tmp_path / "lib"))
    paths.ensure_dirs()
    from vrgallery.config import Config
    from vrgallery.db import Database
    from vrgallery.mainwindow import MainWindow

    cfg = Config()
    cfg.set("onboarded", True, save=False)
    cfg.set("check_updates", False, save=False)
    cfg.set("api_enabled", False, save=False)
    db = Database()
    db.upsert_photos([{
        "path": str(tmp_path / f"p{i}.png"), "folder": str(tmp_path),
        "filename": f"p{i}.png", "taken_at": f"2026-02-01T10:0{i}:00",
        "day": "2026-02-01", "filesize": 10, "mtime": float(i),
    } for i in range(3)])
    win = MainWindow(app, cfg, db, auto_index=False)
    win.resize(1200, 800)
    win.show()
    app.processEvents()
    win.activate("all")
    for _ in range(40):
        app.processEvents()
    win.lightbox.open(win.page_grid.model.photos(), 0, win.page_grid)
    for _ in range(40):
        app.processEvents()
    yield win, win.lightbox
    win._quitting = True
    win.close()
    win.deleteLater()
    app.processEvents()


def press(widget, pos=None, button=Qt.LeftButton, dbl=False):
    """Hand one mouse event straight to a widget and report whether it took it.

    Through the handler rather than through QTest.mouseClick: the whole point is
    which widget ACCEPTS the press, and a synthesised click that Qt routes for
    us would hide exactly that.
    """
    pt = QPointF(pos if pos is not None else widget.rect().center())
    kind = QEvent.MouseButtonDblClick if dbl else QEvent.MouseButtonPress
    ev = QMouseEvent(kind, pt, widget.mapToGlobal(pt.toPoint()),
                     button, button, Qt.NoModifier)
    ev.ignore()
    (widget.mouseDoubleClickEvent if dbl else widget.mousePressEvent)(ev)
    return ev.isAccepted()


# ------------------------------------------------------------ the drag handle

def test_the_header_is_a_widget_and_not_a_bare_layout(box):
    """A QHBoxLayout cannot receive a mouse press. This is the whole fix in one
    assertion: if the row goes back to a layout, everything below is moot."""
    _win, lb = box
    from PySide6.QtWidgets import QWidget
    assert isinstance(lb.topbar, QWidget)
    assert lb.topbar.height() > 0 and lb.topbar.width() > 0


def test_pressing_the_header_starts_a_window_drag(box):
    """THE one. An accepted press means the strip took it and handed the move
    to the compositor."""
    _win, lb = box
    assert press(lb.topbar), (
        "a left press on the lightbox header was not accepted: there is "
        "nothing to drag the window by while a photo is open")


def test_the_filename_is_part_of_the_handle(box):
    """It fills most of the strip. A QLabel ignores presses, so they reach the
    strip -- but only while nothing sets a mouse handler on the label."""
    _win, lb = box
    lab = lb.lab_name
    at = lb.topbar.childAt(lab.geometry().center())
    assert at is None or not isinstance(at, QPushButton), (
        "the filename area is covered by something that eats presses")


def test_the_buttons_in_the_strip_still_get_their_clicks(box):
    """Tag, info and close live inside the drag handle. Qt offers a press to
    the child under the cursor first, so they must still be the child there --
    a strip that covered them would make the close button undraggable AND
    unclickable."""
    _win, lb = box
    for name, btn in (("tag", lb.btn_tag), ("info", lb.btn_info),
                      ("close", lb.btn_close)):
        at = lb.topbar.childAt(btn.geometry().center())
        assert isinstance(at, QPushButton), (
            f"the {name} button is not what sits at its own centre; the strip "
            f"is on top of it")


def test_a_right_press_is_left_alone(box):
    """Only the left button drags. Swallowing the right one would kill any
    context menu the strip ever grows."""
    _win, lb = box
    assert not press(lb.topbar, button=Qt.RightButton)


# --------------------------------------------------------------- double click

def test_double_clicking_the_header_maximises_the_window(box):
    """What a title bar does. The lightbox covers the real one, so it has to
    answer for it."""
    win, lb = box
    was = win.isMaximized()
    assert press(lb.topbar, dbl=True)
    for _ in range(20):
        QApplication.instance().processEvents()
    assert win.isMaximized() != was


def test_it_goes_through_the_real_title_bar_so_the_button_icon_follows(box):
    """The maximise button swaps its icon between maximise and restore. Calling
    showMaximized() directly would leave it showing the wrong one."""
    win, lb = box
    assert hasattr(win, "titlebar"), "the window has no title bar to keep in sync"
    seen = []
    real = win.titlebar.toggle_max
    win.titlebar.toggle_max = lambda: (seen.append(1), real())[1]
    try:
        press(lb.topbar, dbl=True)
        for _ in range(20):
            QApplication.instance().processEvents()
    finally:
        win.titlebar.toggle_max = real
    assert seen, "the double click bypassed the window's own title bar"


def test_a_right_double_click_does_nothing(box):
    _win, lb = box
    assert not press(lb.topbar, button=Qt.RightButton, dbl=True)


# ------------------------------------------------------- and nothing else moved

def test_the_header_still_holds_what_it_held(box):
    """The strip is new furniture around the same controls; if the change had
    reparented one away, it would simply vanish from the lightbox."""
    _win, lb = box
    for name in ("lab_name", "lab_count", "btn_tag", "btn_info", "btn_close"):
        w = getattr(lb, name)
        assert w.parent() is lb.topbar, f"{name} is no longer in the header"


def test_the_header_sits_at_the_top_of_the_lightbox(box):
    """It replaced a layout in the same slot, so it has to land in the same
    place -- not float over the photograph or push it down."""
    _win, lb = box
    assert lb.topbar.y() == 0
    assert lb.topbar.width() > lb.width() // 2, "the strip does not span the column"
    assert lb.viewer.y() >= lb.topbar.height(), "the photo is under the header"
