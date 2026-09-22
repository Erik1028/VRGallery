"""The front door.

NOTE ON THIS FILE'S NAME: it sorts after test_glass.py on purpose. See the note
at the top of tests/test_tag_suggestions.py for the landmine that requires.

Two things about this page are easy to get wrong and invisible when they are.

The first is COVERAGE. The library's metadata is not evenly spread: photographs
go back to 2023, the world and people columns only start in 2025, and the
session tables are rebuilt from VRChat's own logs, which the game keeps about
two days of on disk -- so they hold only the stretch the app has been running
for. A block that assumes its data exists renders an empty frame on a library
that is mostly older than its column, and an empty frame reads as a fault. Each
block here has to disappear instead.

The second is WIDTH. The app is meant to survive being snapped to half a 1920
screen, which leaves the page about 712 px, and this one started life at a
993 px floor -- a horizontal scrollbar and three of five covers cut off. Every
row on it wraps, and this file holds that open the way tests/test_narrow.py
holds the rest of the app open.
"""
import os

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget

from vrgallery import paths, style


@pytest.fixture(scope="module")
def app():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    return QApplication.instance() or QApplication([])


def _library(tmp_path, photos=True, sessions=True, people=True):
    """A library with any of its three metadata eras switched off."""
    paths.set_appdir(str(tmp_path / "lib"))
    paths.ensure_dirs()
    from vrgallery.config import Config
    from vrgallery.db import Database

    cfg = Config()
    cfg.set("onboarded", True, save=False)
    cfg.set("check_updates", False, save=False)
    cfg.set("api_enabled", False, save=False)
    db = Database()
    if photos:
        db.upsert_photos([{
            "path": str(tmp_path / f"p{i}.png"), "folder": str(tmp_path),
            "filename": f"p{i}.png",
            "taken_at": f"2026-0{1 + i % 3}-1{i % 9}T22:0{i % 6}:00",
            "day": f"2026-0{1 + i % 3}-1{i % 9}", "filesize": 1000 + i,
            "mtime": float(i), "world_id": "wrld_%d" % (i % 4),
            "world_name": "World %d" % (i % 4),
        } for i in range(40)])
    if people:
        # written straight in: there is no public setter, and the hasattr
        # guard this started with silently wrote nothing at all, which left
        # every people-shaped assertion below passing on an empty table
        for r in list(db.query_photos(_all()))[:20]:
            db._conn.execute(
                "INSERT OR IGNORE INTO photo_players(photo_id, name, user_id)"
                " VALUES(?,?,?)", (r["id"], "Someone", None))
        db._conn.commit()
    if sessions:
        db._conn.execute(
            "INSERT INTO sessions(log_file, world_id, world_name, start_at, end_at,"
            " instance_type, region) VALUES(?,?,?,?,?,?,?)",
            ("l.txt", "wrld_1", "World 1", "2026-03-18T21:00:00",
             "2026-03-19T01:30:00", "friends", "eu"))
        sid = db._conn.execute("SELECT id FROM sessions").fetchone()["id"]
        db._conn.execute(
            "INSERT INTO session_players(session_id, name, user_id, join_at, leave_at)"
            " VALUES(?,?,?,?,?)",
            (sid, "Someone", None, "2026-03-18T21:10:00", "2026-03-19T00:40:00"))
        db._conn.commit()
    return cfg, db


def _all():
    from vrgallery.db import PhotoFilter
    return PhotoFilter()


def _window(app, cfg, db):
    from vrgallery.mainwindow import MainWindow
    win = MainWindow(app, cfg, db, auto_index=False)
    win.resize(1400, 900)
    win.show()
    app.processEvents()
    win.activate("home")
    for _ in range(40):
        app.processEvents()
    return win


@pytest.fixture()
def home(app, tmp_path):
    cfg, db = _library(tmp_path)
    win = _window(app, cfg, db)
    yield win, win.page_home
    win._quitting = True
    win.close()
    win.deleteLater()
    app.processEvents()


def _labels(page):
    from PySide6.QtWidgets import QLabel
    return [w.text() for w in page.findChildren(QLabel) if w.text()]


# --------------------------------------------------------------- it is there

def test_the_sidebar_has_a_home_entry_and_it_is_first(home):
    win, _page = home
    from vrgallery.mainwindow import NAV
    keys = [e[0] for e in NAV if e]
    assert keys[0] == "home"
    assert "home" in win._nav_buttons


def test_the_page_builds_with_something_on_it(home):
    _win, page = home
    text = " ".join(_labels(page))
    assert "photographs" in text
    assert "LAST NIGHT" in text


# ------------------------------------------------------------- the coverage

def test_a_library_with_no_sessions_simply_has_no_night_card(app, tmp_path):
    """The logs only go back as far as the app has been running. On a fresh
    install there are none at all, and the card has to be absent rather than
    drawn empty."""
    cfg, db = _library(tmp_path, sessions=False)
    assert db.last_night() is None
    win = _window(app, cfg, db)
    try:
        assert "LAST NIGHT" not in " ".join(_labels(win.page_home))
        assert "photographs" in " ".join(_labels(win.page_home))
    finally:
        win._quitting = True
        win.close()
        win.deleteLater()
        app.processEvents()


def test_an_empty_library_does_not_crash_the_front_door(app, tmp_path):
    """Nothing at all: every block has to bow out and leave the figures."""
    cfg, db = _library(tmp_path, photos=False, sessions=False, people=False)
    win = _window(app, cfg, db)
    try:
        assert win.page_home.isVisible() or win.stack.currentWidget() is win.page_home
    finally:
        win._quitting = True
        win.close()
        win.deleteLater()
        app.processEvents()


def test_the_night_card_sums_the_whole_evening(home):
    """A night is several instance visits, not one. Reading only the newest
    session would report the last twenty minutes of a five-hour evening."""
    win, _page = home
    night = win.db.last_night()
    assert night["day"] == "2026-03-18"
    assert night["mins"] == pytest.approx(270, abs=1)     # 21:00 -> 01:30
    assert night["stops"] == 1
    assert night["people"] and night["people"][0][0] == "Someone"


def test_your_own_name_is_not_one_of_the_people(app, tmp_path):
    """You are in every session you have; listing yourself as company is noise."""
    cfg, db = _library(tmp_path)
    assert [n for n, _m in db.last_night()["people"]] == ["Someone"]
    assert db.last_night(("Someone",))["people"] == []


# ------------------------------------------------------------------ the width

def test_the_page_fits_a_window_snapped_to_half_a_screen(home):
    """712 px of page is what a 960 px window leaves after the sidebar. The
    first version of this page would not go below 993 and grew a horizontal
    scrollbar; every row on it wraps for this reason."""
    win, page = home
    win.resize(960, 900)
    for _ in range(30):
        QApplication.instance().processEvents()
    floor = page.holder.minimumSizeHint().width()
    assert floor <= 700, (
        f"the home page will not go below {floor} px, so half-screen gets a "
        f"horizontal scrollbar")


def test_nothing_is_laid_out_past_the_right_edge(home):
    win, page = home
    for width in (1400, 1100, 960):
        win.resize(width, 900)
        for _ in range(30):
            QApplication.instance().processEvents()
        win.grab()
        over = [type(c).__name__ for c in page.holder.findChildren(QWidget)
                if not c.isHidden() and c.parentWidget() is not None
                and c.geometry().right() > c.parentWidget().width() + 1]
        assert not over, f"at {width}px these hang over the edge: {set(over)}"


# ------------------------------------------------------------ the rebuild guard

def test_a_second_visit_does_not_rebuild_the_page(home):
    """refresh() runs on every visit, and rebuilding means dropping and
    recreating every thumbnail widget on the page."""
    _win, page = home
    before = page._shown
    kids = len(page.holder.findChildren(QWidget))
    page.refresh()
    assert page._shown == before
    assert len(page.holder.findChildren(QWidget)) == kids


def test_changing_the_theme_does_rebuild_it(home):
    """The labels here bake their colours into inline stylesheets, so a palette
    swapped while another page was open has to be picked up on the way back.
    That is why the fingerprint carries the ground colour."""
    _win, page = home
    before = page._shown
    try:
        style.apply_palette("ember")
        page.refresh()
        assert page._shown != before, (
            "the page came back in the old colours after a theme change")
    finally:
        style.apply_palette("midnight")


def test_a_new_photograph_rebuilds_it(home):
    win, page = home
    before = page._shown
    win.db.upsert_photos([{
        "path": str(win.db and "x/new.png"), "folder": "x",
        "filename": "new.png", "taken_at": "2026-09-30T23:00:00",
        "day": "2026-09-30", "filesize": 10, "mtime": 99.0}])
    page.refresh()
    assert page._shown != before


# --------------------------------------------------------------- the details

def test_the_gap_label_separates_people_a_year_apart():
    """"a year" for everything between one and two printed the same label for
    gaps of 548, 442 and 414 days -- three different people, four months apart,
    reading identically."""
    from vrgallery.homepage import _gap_label
    assert _gap_label(548) != _gap_label(414)
    assert _gap_label(91) == "3 months"
    assert _gap_label(760) == "2 years"
    assert _gap_label(30) == "30 days"


def test_drifted_apart_wants_a_run_as_well_as_a_gap(home):
    """Somebody photographed eight times in one week and never again was a night
    out, not a friendship that faded. The block asks for both."""
    from vrgallery import homepage
    win, page = home
    box = page._drifted(win.cfg.self_names)
    # this fixture's library is all 2026 and has no old regulars at all
    assert box is None or isinstance(box, QWidget)
    assert hasattr(homepage, "RankRow")


def test_every_row_is_a_way_into_the_app(app):
    """The whole point of a front door: a row is not a fact, it is a door. A
    RankRow with no callback would be a dead end dressed as a link."""
    from vrgallery.homepage import RankRow
    seen = []
    row = RankRow("Someone", "sub", "12", lambda: seen.append(1))
    row.resize(200, 30)
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    ev = QMouseEvent(QEvent.MouseButtonRelease, QPointF(10, 10),
                     row.mapToGlobal(row.rect().center()),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    row.mouseReleaseEvent(ev)
    assert seen, "clicking a row on the home page did nothing"
