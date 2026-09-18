"""The header is a floating overlay, and a second row does not fit itself.

NOTE ON THIS FILE'S NAME: it sorts after test_glass.py on purpose. See the note
at the top of tests/test_tag_suggestions.py for the landmine that requires.

Clicking the filter button made the filter bar visible and stopped there. The
header is a floating panel that sizes itself to the rows it holds, and showing
a child does not re-place it -- so it stayed at its one-row height with two
rows to fit, and Qt did the only thing it can: it halved both.

What that looked like is the part worth keeping a test for. Every control in
BOTH rows came out 14 px tall, and 5 px when the header was in its collapsed
state further down the page. A glyph does not fit in 14 px, let alone 5, so the
title landed on top of its own subtitle and the level pills, the sort box, all
three filter combos and the Apply button came up as blank rounded boxes. It
read as data failing to load rather than as a layout with no room, and it put
itself right on the next window resize, which is most of why it survived.
"""
import os

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QComboBox, QDateEdit, QPushButton

from vrgallery import paths


@pytest.fixture(scope="module")
def app():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def grid(app, tmp_path):
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
        "filename": f"p{i}.png",
        "taken_at": f"2026-02-{1 + i // 9:02d}T10:{i % 60:02d}:00",
        "day": f"2026-02-{1 + i // 9:02d}", "filesize": 10, "mtime": float(i),
    } for i in range(120)])
    win = MainWindow(app, cfg, db, auto_index=False)
    win.resize(1500, 800)
    win.show()
    app.processEvents()
    win.activate("all")
    for _ in range(40):
        app.processEvents()
    yield win.page_grid
    win._quitting = True
    win.close()
    win.deleteLater()
    app.processEvents()


def settle(n=25):
    for _ in range(n):
        QApplication.instance().processEvents()


def settle_head(grid, tries=60):
    """Pump events until the header has stopped moving.

    The collapse is animated, so processEvents() in a tight loop returns with
    it part-way there -- 62 px between an open 72 and a collapsed 55. Measuring
    a BEFORE against that and an AFTER against the settled height makes the
    difference come out short by however far the animation got in between, and
    the test fails on a build that is perfectly correct.
    """
    from PySide6.QtCore import QEventLoop, QTimer

    last, same = None, 0
    for _ in range(tries):
        loop = QEventLoop()
        QTimer.singleShot(16, loop.quit)
        loop.exec()
        h = grid.headwrap.height()
        same = same + 1 if h == last else 0
        last = h
        if same >= 4:
            return h
    return last


def controls(bar):
    """The things in the filter bar that have to be tall enough to read."""
    out = []
    for cls in (QPushButton, QComboBox, QDateEdit):
        out.extend(bar.findChildren(cls))
    return out


def shortest(bar):
    """(height it got, height it asked for) for the worst-off control."""
    return min(((c.height(), c.sizeHint().height()) for c in controls(bar)),
               key=lambda t: t[0] - t[1])


# --------------------------------------------------------------- the height

def test_opening_the_filter_bar_does_not_squash_what_is_already_there(grid):
    """THE one. The header has to get taller by the row it just grew, not
    redistribute the height it already had between two rows."""
    before = settle_head(grid)
    bar_h = grid.filter_bar.sizeHint().height()
    grid.btn_filter.setChecked(True)
    after = settle_head(grid)
    assert after - before == bar_h, (
        f"the header went {before} -> {after} for a "
        f"{bar_h} px row: it is dividing its old height between two rows")


def test_every_filter_control_is_tall_enough_for_its_own_text(grid):
    """What the squash actually did. 14 px is shorter than a line of text, so
    the combos and the buttons rendered as empty boxes."""
    grid.btn_filter.setChecked(True)
    settle()
    got, want = shortest(grid.filter_bar)
    assert got >= want - 1, (
        f"the shortest control in the filter bar is {got} px tall and wants "
        f"{want}: its label will not be drawn at all")


def test_the_row_that_was_already_there_keeps_its_height(grid):
    """The search box, the sort box and the level pills live in the first row,
    and they were halved along with everything else."""
    row = grid.headwrap.bar
    settle_head(grid)
    before = row.height()
    grid.btn_filter.setChecked(True)
    settle_head(grid)
    assert row.height() == before, (
        f"the main header row went {before} -> {row.height()} px when a "
        f"SECOND row was opened below it")


def test_it_is_still_right_when_the_header_is_collapsed(grid):
    """Scrolled down the header shrinks to a slim bar, and the squash was worse
    there: the controls came out 5 px tall."""
    sb = grid.view.verticalScrollBar()
    sb.setValue(sb.maximum() // 2)
    before = settle_head(grid)
    bar_h = grid.filter_bar.sizeHint().height()
    grid.btn_filter.setChecked(True)
    after = settle_head(grid)
    assert after - before == bar_h, f"collapsed: {before} -> {after}, bar {bar_h}"
    got, want = shortest(grid.filter_bar)
    assert got >= want - 1, f"collapsed, the shortest control is {got} of {want}"


def test_closing_it_gives_the_room_back(grid):
    """A header that kept the taller size would leave a band of empty glass
    over the photographs for the rest of the session."""
    before = settle_head(grid)
    gap = grid.model._shape[1]
    grid.btn_filter.setChecked(True)
    settle_head(grid)
    grid.btn_filter.setChecked(False)
    assert settle_head(grid) == before
    assert grid.model._shape[1] == gap


# ----------------------------------------------------- and what sits under it

def test_the_grid_leaves_room_for_the_new_row(grid):
    """The photographs scroll UNDER the header, so the blank row at the top of
    the model is the only thing keeping the first of them out from behind it."""
    gap = grid.model._shape[1]
    bar_h = grid.filter_bar.sizeHint().height()
    grid.btn_filter.setChecked(True)
    settle()
    assert grid.model._shape[1] - gap == bar_h, (
        f"the grid's top gap stayed at {grid.model._shape[1]}: the first row "
        f"of photographs is behind the filter bar")


def test_making_room_does_not_throw_you_back_to_the_top(grid):
    """Going through set_photos() to change one row's height would
    beginResetModel() the whole library, and that drops the scroll position --
    the same fault that used to move the grid under you every fifteen seconds."""
    sb = grid.view.verticalScrollBar()
    sb.setValue(sb.maximum() // 2)
    settle()
    was = sb.value()
    assert was > 0, "the grid did not scroll; this test proves nothing"
    grid.btn_filter.setChecked(True)
    settle()
    assert abs(sb.value() - was) <= 2, (
        f"opening the filter bar moved the grid from {was} to {sb.value()}")


def test_it_does_not_lose_the_selection_either(grid):
    """Same reason: a model reset clears the selection, and the filter bar is
    something you open while holding a selection you are about to act on."""
    from PySide6.QtCore import QItemSelectionModel

    from vrgallery.gridmodel import KIND_PHOTO
    row = next(r for r in range(grid.model.rowCount())
               if grid.model.row_at(r)[0] == KIND_PHOTO)
    grid.view.selectionModel().select(grid.model.index(row, 0),
                                      QItemSelectionModel.Select)
    settle()
    assert grid.view.selected_photo_items()
    grid.btn_filter.setChecked(True)
    settle()
    assert grid.view.selected_photo_items(), (
        "opening the filter bar cleared the selection")


# ------------------------------------------------------------- the model part

def test_setting_the_same_gap_twice_is_not_a_change(grid):
    """place() runs on every step of a window resize, and a rebuild per frame
    would be the most expensive thing in the drag."""
    gap = grid.model._shape[1]
    assert grid.model.set_top_gap(gap) is False
    assert grid.model.set_top_gap(gap + 10) is True


def test_a_gap_change_does_not_rebuild_the_rows(grid):
    """It edits the one spacer row in place. If that ever goes back to a full
    rebuild, the two tests above start passing for the wrong reason."""
    resets = []
    grid.model.modelAboutToBeReset.connect(lambda: resets.append(1))
    grid.model.set_top_gap(grid.model._shape[1] + 17)
    assert not resets, "changing the top gap reset the whole model"
