"""The timeline rail at the Years and Months levels.

There the grid holds year and month cards, not photos, and a card's payload is
a dict. GridModel.month_marks() only knew the photo-shaped rows, so any rail
refresh that ran while the cards were up -- the one the Days view queues for
after its own layout, a window resize, a thumbnail-size change -- raised
AttributeError: 'dict' object has no attribute 'day'. `run.py --shot x.png
--page years` hit it every time.
"""
import os

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from vrgallery import paths
from vrgallery.gridmodel import GridModel

_KEEP = []


@pytest.fixture(scope="module")
def app():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    return QApplication.instance() or QApplication([])


def _periods(level):
    keys = ["2026", "2025", "2024"] if level == "year" else ["2025-07", "2025-03"]
    return [{"k": k, "c": 4, "b": 40, "cover_id": None} for k in keys]


@pytest.mark.parametrize("level", ["year", "month"])
def test_period_cards_have_no_month_marks(app, level):
    m = GridModel()
    _KEEP.append(m)
    m.set_periods(_periods(level), level, {}, top_gap=90)
    assert m.month_marks() == []
    assert all(m.day_of_row(r) is None for r in range(m.rowCount()))


@pytest.fixture()
def window(app, tmp_path):
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
    rows = []
    for year in (2024, 2025, 2026):
        for month in range(1, 13):
            for n in range(4):
                day = f"{year}-{month:02d}-{n + 3:02d}"
                rows.append({"path": f"/r/{year}{month:02d}{n}.png", "folder": "/r",
                             "filename": f"VRChat_{day}_10-00-0{n}.000.png",
                             "taken_at": f"{day}T10:00:0{n}", "day": day,
                             "filesize": 10, "mtime": 1.0})
    db.upsert_photos(rows)
    win = MainWindow(app, cfg, db, auto_index=False)
    win.resize(1200, 820)
    win.show()
    app.processEvents()
    yield win
    win._quitting = True
    win.close()
    win.deleteLater()
    app.processEvents()


def _settle(app, n=20):
    for _ in range(n):
        app.processEvents()


def _rail_and_scrollbar_agree(page):
    """One scale in the gutter: the rail, or the plain scrollbar, never both."""
    off = page.view.verticalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    return page.rail.isVisible() == off


@pytest.mark.parametrize("level", ["year", "month"])
def test_a_rail_refresh_at_a_period_level_is_harmless(window, app, level):
    page = window.page_grid
    window.activate("all")
    page.set_level(level)        # as --shot --page years does: the Days view's
    _settle(app)                 # queued rail refresh fires after the switch
    page._refresh_rail()         # and a resize or a zoom asks again, directly
    assert page.rail_marks()[0] == []
    assert not page.rail.isVisible(), "the cards are the scale at this level"
    assert _rail_and_scrollbar_agree(page)


def test_days_after_years_shows_photos_and_the_rail_again(window, app):
    """Days -> Years -> Days through the level control, the filter unchanged.

    refresh() skips the rebuild when the photo query's answer is the one it
    is already showing -- and set_periods() did not tell it the model had been
    swapped for cards, so Days came back as the year cards under a Days
    button. Found while fixing the rail; 2.16.1 does it too.
    """
    page = window.page_grid
    window.activate("all")
    page._level_clicked("day")
    _settle(app)
    assert page.rail.isVisible()
    page._level_clicked("year")
    _settle(app)
    page._refresh_rail()
    page._level_clicked("day")
    _settle(app)
    assert len(page.model.photos()) == 3 * 12 * 4, "Days must show the photos"
    assert page.model.month_marks(), "not the year cards"
    assert page.rail.isVisible(), "three years of months deserve the rail"
    assert _rail_and_scrollbar_agree(page)
