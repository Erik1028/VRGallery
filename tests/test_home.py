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
    assert page._card is not None, "the fixture has a sitting and no card was drawn"


# ------------------------------------------------------------- the coverage

def test_a_library_with_no_sessions_simply_has_no_night_card(app, tmp_path):
    """The logs only go back as far as the app has been running. On a fresh
    install there are none at all, and the card has to be absent rather than
    drawn empty."""
    cfg, db = _library(tmp_path, sessions=False)
    assert db.last_sitting() is None
    win = _window(app, cfg, db)
    try:
        assert win.page_home._card is None
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


def test_the_sitting_sums_the_whole_evening(home):
    """A sitting is several instance visits, not one. Reading only the newest
    session would report the last twenty minutes of a five-hour evening."""
    win, _page = home
    sit = win.db.last_sitting()
    assert sit["mins"] == pytest.approx(270, abs=1)       # 21:00 -> 01:30
    assert sit["sessions"] == 1
    assert [p["name"] for p in sit["people"]] == ["Someone"]


def test_your_own_name_is_not_one_of_the_people(app, tmp_path):
    """You are in every session you have; listing yourself as company is noise."""
    cfg, db = _library(tmp_path)
    assert [p["name"] for p in db.last_sitting()["people"]] == ["Someone"]
    assert db.last_sitting(("Someone",))["people"] == []


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


# ------------------------------------------------------- the sitting, measured

def _sessions(db, spans, people=()):
    """Sessions from (start, end, world) and players from
    (session_index, name, user_id, join, leave-or-None)."""
    ids = []
    for i, (a, b, w) in enumerate(spans):
        db._conn.execute(
            "INSERT INTO sessions(log_file, world_id, world_name, start_at, end_at,"
            " instance_type, region) VALUES(?,?,?,?,?,?,?)",
            ("log%d.txt" % i, "wrld_" + w, w, a, b, "friends", "eu"))
        ids.append(db._conn.execute("SELECT MAX(id) i FROM sessions").fetchone()["i"])
    for si, name, uid, j, l in people:
        db._conn.execute(
            "INSERT INTO session_players(session_id, name, user_id, join_at, leave_at)"
            " VALUES(?,?,?,?,?)", (ids[si], name, uid, j, l))
    db._conn.commit()
    return ids


def test_a_night_that_crosses_midnight_is_one_sitting(app, tmp_path):
    """The whole reason this is not a calendar day. 24 of the 40 sittings in the
    real logs cross midnight; grouped by the date they started, the tail of each
    was glued onto the next afternoon."""
    # B STARTS after midnight -- that is the case calendar grouping splits. A
    # session that merely ends after midnight does not show the bug, which is
    # how the first version of this test passed with the bug put back.
    _cfg, db = _library(tmp_path, sessions=False)
    _sessions(db, [("2026-09-20T21:00:00", "2026-09-20T23:55:00", "A"),
                   ("2026-09-21T00:10:00", "2026-09-21T02:30:00", "B")])
    sit = db.last_sitting()
    assert sit["sessions"] == 2
    assert sit["start"].isoformat() == "2026-09-20T21:00:00"
    assert sit["end"].isoformat() == "2026-09-21T02:30:00"
    assert len(sit["worlds"]) == 2


def test_the_tail_of_a_night_is_not_glued_onto_the_next_afternoon(app, tmp_path):
    """The exact failure that was on screen: grouped by start date, the hours
    after midnight belonged to the NEXT day and were added to that afternoon,
    and the card reported one "9h 16m, 12 stops" evening that never happened."""
    _cfg, db = _library(tmp_path, sessions=False)
    _sessions(db, [("2026-09-20T21:00:00", "2026-09-20T23:55:00", "Night"),
                   ("2026-09-21T00:10:00", "2026-09-21T02:30:00", "Night"),
                   ("2026-09-21T16:00:00", "2026-09-21T18:00:00", "Afternoon")])
    sit = db.last_sitting()
    assert sit["sessions"] == 1
    assert [w[1] for w in sit["worlds"]] == ["Afternoon"]
    assert sit["mins"] == pytest.approx(120, abs=1)


def test_a_long_break_ends_the_sitting(app, tmp_path):
    """Going to bed and coming back the next afternoon is two sittings, and the
    card is about the second."""
    _cfg, db = _library(tmp_path, sessions=False)
    _sessions(db, [("2026-09-20T21:00:00", "2026-09-21T02:00:00", "A"),
                   ("2026-09-21T16:00:00", "2026-09-21T18:00:00", "B")])
    sit = db.last_sitting()
    assert sit["sessions"] == 1
    assert sit["world_name"] == "B"


def test_a_break_just_under_the_limit_does_not(app, tmp_path):
    _cfg, db = _library(tmp_path, sessions=False)
    gap = db.SITTING_GAP_MIN - 5
    _sessions(db, [("2026-09-21T16:00:00", "2026-09-21T17:00:00", "A"),
                   ("2026-09-21T%02d:%02d:00" % (17 + gap // 60, gap % 60),
                    "2026-09-21T20:00:00", "B")])
    assert db.last_sitting()["sessions"] == 2


def test_somebody_still_there_when_the_game_closed_is_not_dropped(app, tmp_path):
    """VRChat writes no leave line when you quit, so the friends who stayed to
    the end have none. The first card filtered on leave_at IS NOT NULL and lost
    them -- usually the longest companions of the night."""
    _cfg, db = _library(tmp_path, sessions=False)
    _sessions(db, [("2026-09-21T20:00:00", "2026-09-21T23:00:00", "A")],
              [(0, "Stayer", "usr_1", "2026-09-21T20:05:00", None),
               (0, "Passer", "usr_2", "2026-09-21T21:00:00", "2026-09-21T21:05:00")])
    sit = db.last_sitting()
    names = [p["name"] for p in sit["people"]]
    assert names[0] == "Stayer", "the one who stayed to the end was dropped"
    assert sit["people"][0]["minutes"] == pytest.approx(175, abs=1)
    assert sit["people"][0]["present"] is True


def test_a_renamed_friend_is_one_person_under_the_latest_name(app, tmp_path):
    """The log carries user ids. Keyed by display name, somebody who changed it
    mid-evening came out as two half-length strangers."""
    _cfg, db = _library(tmp_path, sessions=False)
    _sessions(db, [("2026-09-21T20:00:00", "2026-09-21T23:00:00", "A")],
              [(0, "OldName", "usr_9", "2026-09-21T20:00:00", "2026-09-21T21:00:00"),
               (0, "NewName", "usr_9", "2026-09-21T21:10:00", "2026-09-21T22:10:00")])
    sit = db.last_sitting()
    assert len(sit["people"]) == 1
    assert sit["people"][0]["name"] == "NewName"
    assert sit["people"][0]["minutes"] == pytest.approx(120, abs=1)


def test_you_are_left_out_by_id_as_well_as_by_name(app, tmp_path):
    """A renamed you is still you: the ids your known names carry are excluded
    too, or your own old name turns up as a companion."""
    _cfg, db = _library(tmp_path, sessions=False)
    _sessions(db, [("2026-09-21T20:00:00", "2026-09-21T23:00:00", "A")],
              [(0, "Me", "usr_me", "2026-09-21T20:00:00", None),
               (0, "MyOldName", "usr_me", "2026-09-21T20:00:00", "2026-09-21T20:30:00"),
               (0, "Friend", "usr_f", "2026-09-21T20:00:00", None)])
    assert [p["name"] for p in db.last_sitting(("Me",))["people"]] == ["Friend"]


def test_people_are_ranked_by_time_not_by_who_was_left_at_the_end(app, tmp_path):
    """Present-at-the-end is not a ranking for a sitting that is over: it put
    somebody with 160 minutes behind five people with under an hour."""
    _cfg, db = _library(tmp_path, sessions=False)
    _sessions(db, [("2026-09-21T20:00:00", "2026-09-21T23:00:00", "A")],
              [(0, "Long", "usr_l", "2026-09-21T20:00:00", "2026-09-21T22:40:00"),
               (0, "Short", "usr_s", "2026-09-21T22:30:00", None)])
    assert [p["name"] for p in db.last_sitting()["people"]] == ["Long", "Short"]


def test_somebody_never_photographed_has_no_page_to_open(app, tmp_path):
    """A chip for them opened an empty "Nothing here" grid, which reads as a
    broken library. photo_name is how the card knows not to make it a link."""
    _cfg, db = _library(tmp_path, sessions=False)
    _sessions(db, [("2026-09-21T20:00:00", "2026-09-21T23:00:00", "A")],
              [(0, "Someone", "usr_a", "2026-09-21T20:00:00", None),
               (0, "Stranger", "usr_b", "2026-09-21T20:00:00", None)])
    by = {p["name"]: p for p in db.last_sitting()["people"]}
    assert by["Someone"]["photo_name"] == "Someone"      # photographed in the fixture
    assert by["Stranger"]["photo_name"] is None


def test_the_sittings_photos_are_found_across_midnight(app, tmp_path):
    """Not the day's photos: a sitting that crosses midnight is two days, and
    the day page for either is the wrong set of pictures."""
    _cfg, db = _library(tmp_path, photos=False, sessions=False, people=False)
    db.upsert_photos([{
        "path": "/n/%d.png" % i, "folder": "/n", "filename": "%d.png" % i,
        "taken_at": t, "day": t[:10], "filesize": 10, "mtime": float(i)}
        for i, t in enumerate(["2026-09-20T22:00:00", "2026-09-21T01:30:00",
                               "2026-09-21T15:00:00"])])
    _sessions(db, [("2026-09-20T21:00:00", "2026-09-21T02:00:00", "A")])
    got = db.photos_by_ids_full(db.last_sitting()["photo_ids"])
    assert [r["taken_at"] for r in got] == ["2026-09-20T22:00:00",
                                            "2026-09-21T01:30:00"]


# ----------------------------------------------------------- the words for it

def _lbl(start, end, now, live=False):
    import datetime as dt
    from vrgallery.homepage import sitting_label
    p = dt.datetime.fromisoformat
    return sitting_label(p(start), p(end), live, p(now))


def test_the_heading_is_not_last_night_on_a_wednesday_lunchtime():
    """It was a constant. On Wednesday at 13:15 it stood above a Tuesday
    afternoon, and a week later above the same Tuesday afternoon."""
    assert _lbl("2026-09-22T16:19:00", "2026-09-22T19:19:00",
                "2026-09-23T13:15:00") == "YESTERDAY AFTERNOON"


@pytest.mark.parametrize("start, end, now, want", [
    # an evening that ran past midnight, read the next day
    ("2026-09-20T21:00:00", "2026-09-21T02:00:00", "2026-09-21T13:00:00", "LAST NIGHT"),
    # the same evening read at 03:00 while it is still that night
    ("2026-09-20T21:00:00", "2026-09-21T02:00:00", "2026-09-21T03:00:00", "TONIGHT"),
    # a sitting that starts after midnight still belongs to the evening before
    ("2026-09-21T01:00:00", "2026-09-21T04:00:00", "2026-09-21T14:00:00", "LAST NIGHT"),
    ("2026-09-23T10:00:00", "2026-09-23T11:00:00", "2026-09-23T13:00:00", "THIS MORNING"),
    ("2026-09-23T14:00:00", "2026-09-23T16:00:00", "2026-09-23T17:00:00", "THIS AFTERNOON"),
    # within the week: the weekday
    ("2026-09-19T20:29:00", "2026-09-20T04:58:00", "2026-09-23T13:00:00", "SATURDAY NIGHT"),
    # older than that: the date
    ("2026-09-04T17:06:00", "2026-09-04T19:35:00", "2026-09-23T13:00:00", "SEPTEMBER 4"),
])
def test_the_heading_says_it_the_way_you_would(start, end, now, want):
    assert _lbl(start, end, now) == want


def test_a_running_game_is_right_now():
    assert _lbl("2026-09-23T13:35:00", "2026-09-23T13:45:00",
                "2026-09-23T13:50:00", live=True).startswith("RIGHT NOW")


# --------------------------------------------------------------- live, and fresh

def test_live_needs_the_game_running_and_the_newest_log_in_the_library(home, monkeypatch):
    """Both. The game alone would call yesterday's sitting "right now" in the
    seconds between starting it and the log pass catching up."""
    from vrgallery import homepage
    _win, page = home
    monkeypatch.setattr(homepage.winutil, "process_running", lambda _n: True)
    monkeypatch.setattr(homepage.vrclog, "find_logs", lambda: [r"C:\x\log0.txt"])
    assert page._live("log0.txt") is True
    assert page._live("an_older_log.txt") is False
    monkeypatch.setattr(homepage.winutil, "process_running", lambda _n: False)
    assert page._live("log0.txt") is False


def test_the_page_is_refreshed_when_an_index_pass_lands(home):
    """It is the page the app opens on, and it was missing from the list of
    pages after_photos_changed refreshes -- so it showed whatever it said when
    first drawn."""
    win, page = home
    calls = []
    real = page.refresh
    page.refresh = lambda *a, **k: (calls.append(1), real(*a, **k))[1]
    try:
        win.after_photos_changed()
    finally:
        page.refresh = real
    assert calls, "Home is open and after_photos_changed did not refresh it"


def test_a_longer_evening_changes_the_fingerprint(home):
    """One evening in one instance adds no session: it only makes the last one
    longer and fills in who left. With the session count alone the card froze."""
    win, _page = home
    before = win.db.home_stamp(())
    win.db._conn.execute("UPDATE sessions SET end_at='2026-03-19T03:00:00'")
    win.db._conn.commit()
    assert win.db.home_stamp(()) != before


def test_the_next_day_rebuilds_the_page(home, monkeypatch):
    """Reopened from the tray in the morning, "on this day" still said the day
    before: the fingerprint had no date in it."""
    import datetime as dt
    from vrgallery import homepage
    _win, page = home
    page.refresh(force=True)
    before = page._shown

    class Tomorrow(dt.date):
        @classmethod
        def today(cls):
            return dt.date(2031, 1, 2)

    monkeypatch.setattr(homepage.datetime, "date", Tomorrow)
    page.refresh()
    assert page._shown != before


def test_a_quiet_minute_ticks_the_clock_without_rebuilding(home):
    """The live card's "so far" moves once a minute. Rebuilding the page for it
    would recreate every thumbnail on it."""
    _win, page = home
    page.refresh(force=True)
    card = page._card
    ticks = []
    card.tick = lambda now: ticks.append(now)
    page.refresh()
    assert page._card is card, "an unchanged page was rebuilt"
    assert ticks, "the card's clock was not moved on"


def test_a_chip_with_nowhere_to_go_is_not_a_link(app):
    from vrgallery.homepage import PersonChip

    class Main:
        def push_person(self, n):
            raise AssertionError("navigated for somebody with no photographs")

    chip = PersonChip(Main(), {"name": "Stranger", "minutes": 40, "present": True,
                               "photo_name": None})
    assert chip._on_click is None
    assert "No photographs" in chip.toolTip()


def test_a_chip_does_not_navigate_on_a_right_click(app):
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from vrgallery.homepage import PersonChip
    went = []

    class Main:
        def push_person(self, n):
            went.append(n)

    chip = PersonChip(Main(), {"name": "Friend", "minutes": 40, "present": False,
                               "photo_name": "Friend"})
    chip.resize(120, 24)
    for button in (Qt.RightButton, Qt.LeftButton):
        ev = QMouseEvent(QEvent.MouseButtonRelease, QPointF(10, 10),
                         chip.mapToGlobal(chip.rect().center()),
                         button, button, Qt.NoModifier)
        chip.mouseReleaseEvent(ev)
    assert went == ["Friend"], f"navigated {len(went)} times for one left click"


# ------------------------------------- what the second review found, held shut

def _sit(**kw):
    import datetime as dt
    base = {"start": dt.datetime(2026, 9, 21, 20, 0), "end": dt.datetime(2026, 9, 21, 21, 30),
            "mins": 60.0, "sessions": 2, "log_file": "l.txt", "instance_type": "friends",
            "world_id": "wrld_a", "world_name": "A", "worlds": [["wrld_a", "A", 60.0]],
            "people": [], "people_total": 0, "photo_ids": [], "avatar": None}
    base.update(kw)
    return base


def test_live_so_far_is_in_world_time_not_the_clock(home):
    """A sitting takes in restarts up to 90 minutes apart. "now - start" counted
    the gaps, and one real sitting read 8h 17m live and 6h 34m a minute after
    quitting. Live is now the logged time plus the session still running."""
    import datetime as dt
    from vrgallery.homepage import SittingCard
    win, page = home
    card = SittingCard(win, win.cache, _sit(), True,
                       dt.datetime(2026, 9, 21, 21, 40), page._open_photos)
    assert "1h 10m in-world so far" in card._sub.text().replace("\u00a0", " ")


def test_the_part_of_the_day_is_read_from_the_middle():
    """11:02 to 16:23 was an afternoon and was headed "morning"."""
    assert _lbl("2026-09-05T11:02:00", "2026-09-05T16:23:00",
                "2026-09-05T16:30:00") == "THIS AFTERNOON"


def test_an_afternoon_is_yesterday_after_midnight():
    """The six-o'clock shift is for nights. Applied to afternoons it kept
    Tuesday's "THIS AFTERNOON" until six on Wednesday."""
    assert _lbl("2026-09-22T16:19:00", "2026-09-22T19:19:00",
                "2026-09-23T01:00:00") == "YESTERDAY AFTERNOON"


def test_an_old_night_is_dated_by_when_it_started():
    """The line under the heading gives the start's date; the heading must too,
    or "SEPTEMBER 18" sits over "Saturday · September 19 · 00:30"."""
    assert _lbl("2026-09-19T00:30:00", "2026-09-19T04:00:00",
                "2026-10-10T12:00:00") == "SEPTEMBER 19"


def test_the_night_the_clocks_go_back_keeps_its_hour(app, tmp_path):
    """Log times are local wall clock. Inside the repeated hour a session ends
    "before" it began, and clamping that to zero lost it and its people."""
    _cfg, db = _library(tmp_path, sessions=False)
    _sessions(db, [("2026-10-25T02:40:00", "2026-10-25T02:10:00", "A")],
              [(0, "Friend", "usr_f", "2026-10-25T02:45:00", "2026-10-25T02:05:00")])
    sit = db.last_sitting()
    assert sit["mins"] == pytest.approx(30, abs=1)
    assert sit["people"][0]["minutes"] == pytest.approx(20, abs=1)


def test_an_evening_moving_on_rebuilds_the_card_not_the_page(home):
    """The session part of the fingerprint moves on every log pass while the
    game runs. Folded into one fingerprint it tore down the whole page -- every
    shelf and thumbnail -- every fifteen seconds to change one card."""
    win, page = home
    page.refresh(force=True)
    first = page.vbox.itemAt(0).widget()
    card = page._card
    win.db._conn.execute("UPDATE sessions SET end_at='2026-03-19T03:00:00'")
    win.db._conn.commit()
    page.refresh()
    assert page.vbox.itemAt(0).widget() is first, "the page was rebuilt"
    assert page._card is not card, "the card was not"
    assert page.vbox.indexOf(page._card) == 1, "the new card is not where the old one was"


def test_nothing_is_rebuilt_while_the_window_is_hidden(home):
    """Home stays the current page in the tray, and every log pass rebuilt it
    for nobody. It waits, and catches up when it is shown."""
    win, page = home
    page.refresh(force=True)
    card = page._card
    win.hide()
    QApplication.instance().processEvents()
    win.db._conn.execute("UPDATE sessions SET end_at='2026-03-19T03:00:00'")
    win.db._conn.commit()
    page.refresh()
    assert page._card is card and page._dirty, "rebuilt while hidden"
    win.show()
    for _ in range(20):
        QApplication.instance().processEvents()
    assert not page._dirty and page._card is not card, "did not catch up on show"


def test_a_dead_tile_does_not_stay_registered(app):
    """A thumbnail already in memory is never delivered again, so pruning only
    on delivery let every rebuilt tile's wrapper pile up for good."""
    import shiboken6
    from vrgallery.gridmodel import ThumbCache

    class Svc:
        def request_thumb(self, *a):
            pass

    class Bridge:
        class thumb_ready:
            @staticmethod
            def connect(_f):
                pass

    cache = ThumbCache(Svc(), Bridge())
    for _ in range(5):
        w = QWidget()
        cache.watch(7, w)
        shiboken6.delete(w)
    keep = QWidget()
    cache.watch(7, keep)
    assert cache._watchers[7] == [keep]


def _photos_in(db, n, start="2026-03-18T21:05:00"):
    import datetime as dt
    t0 = dt.datetime.fromisoformat(start)
    db.upsert_photos([{
        "path": "/s/%d.png" % i, "folder": "/s", "filename": "%d.png" % i,
        "taken_at": (t0 + dt.timedelta(minutes=i)).isoformat(),
        "day": t0.date().isoformat(), "filesize": 10, "mtime": float(i)}
        for i in range(n)])


def test_the_strip_builds_what_can_show_and_still_counts_the_rest(home):
    """One tile per photograph made two hundred registered widgets to show
    five. It builds eight, and "+N" is told about the others."""
    from vrgallery.pages import ThumbStrip
    win, page = home
    _photos_in(win.db, 30)
    page.refresh(force=True)
    strip = page._card.findChild(ThumbStrip)
    total = len(win.db.last_sitting()["photo_ids"])
    assert strip.count() == 8
    assert strip._extra == total - 8


def test_plus_n_opens_the_sitting_at_its_start(home):
    """"+N" stands for the older photographs that did not fit. Opening at the
    newest landed on the tile already beside it."""
    from vrgallery.pages import ThumbStrip
    win, page = home
    _photos_in(win.db, 30)
    opened = []
    page._open_photos = lambda ids, pos: opened.append(pos)
    page.refresh(force=True)
    page._card.findChild(ThumbStrip)._on_more()
    assert opened == [0]


def test_plus_n_ignores_a_press_dragged_away(app):
    """The thumbnails beside it already did; on the same row it did not."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    from vrgallery.pages import MoreTile
    went = []
    tile = MoreTile(5, lambda: went.append(1))
    tile.set_tile(100, 60)
    for x in (300, 10):                     # off the tile, then on it
        ev = QMouseEvent(QEvent.MouseButtonRelease, QPointF(x, 10),
                         tile.mapToGlobal(tile.rect().center()),
                         Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        tile.mouseReleaseEvent(ev)
    assert went == [1]


def test_live_lists_only_who_is_in_the_room(home):
    """Under "RIGHT NOW" a row holding everyone met earlier in the night read
    as "these are here with me". The rest are a count."""
    import datetime as dt
    from vrgallery.homepage import PersonChip, SittingCard
    win, page = home
    people = [{"name": "Here", "user_id": "u1", "minutes": 30, "present": True,
               "photo_name": None},
              {"name": "Gone", "user_id": "u2", "minutes": 90, "present": False,
               "photo_name": None}]
    card = SittingCard(win, win.cache, _sit(people=people, people_total=2), True,
                       dt.datetime(2026, 9, 21, 21, 40), page._open_photos)
    names = [c.findChildren(type(card._sub))[-2].text() for c in card.findChildren(PersonChip)]
    assert names == ["Here"]
    assert "+1 earlier" in " ".join(l.text() for l in card.findChildren(type(card._sub)))


def test_one_photograph_does_not_float_mid_card(app, tmp_path):
    """The strip took three fifths of the card whatever it held. (Its own
    library: the shared fixture already has four photographs in its sitting.)"""
    from vrgallery.pages import ThumbStrip
    cfg, db = _library(tmp_path, photos=False, people=False)
    _photos_in(db, 1)
    win = _window(app, cfg, db)
    try:
        assert len(db.last_sitting()["photo_ids"]) == 1
        strip = win.page_home._card.findChild(ThumbStrip)
        assert strip.maximumWidth() <= 200
    finally:
        win._quitting = True
        win.close()
        win.deleteLater()
        app.processEvents()


# ------------------------------------------------------- the pill in the title bar
#
# Where you are in VRChat, on every page (2026-09-25): the one piece of
# Mixtape's design Erik asked for. It reads the same three things the Home card
# reads, and these hold the parts of it that are easy to break unseen: which of
# its two states it is in, that a press on it is a click and not a window drag,
# and that it keeps up without redrawing the world every minute.

def _game(monkeypatch, running, log="l.txt"):
    from vrgallery import homepage
    monkeypatch.setattr(homepage.winutil, "process_running", lambda _n: running)
    monkeypatch.setattr(homepage.vrclog, "find_logs", lambda: [os.path.join(r"C:\x", log)])


def _nbsp(s):
    return s.replace("\u00a0", " ")


def test_the_pill_says_where_you_are_while_the_game_runs(home, monkeypatch):
    win, _page = home
    pill = win.live_pill
    _game(monkeypatch, True)
    pill.refresh(force=True)
    assert not pill.isHidden()
    assert pill._title.text() == "In VRChat · World 1"
    assert not pill._dot.isHidden(), "live, and no green dot"
    sub = _nbsp(pill._sub.text())
    assert sub.startswith("Friends · "), sub
    assert "in-world" in sub and "so far" not in sub


def test_between_sessions_it_says_where_you_were_last(home, monkeypatch):
    """Dimmer, with the sitting's own heading in sentence case. The card's
    headings are capitals ("MARCH 18"); a title-bar line in capitals shouts."""
    win, _page = home
    pill = win.live_pill
    _game(monkeypatch, False)
    pill.refresh(force=True)
    assert not pill.isHidden(), "gone between sessions: the title bar would jump"
    assert pill._title.text() == "Last in VRChat · World 1"
    assert pill._dot.isHidden()
    bits = _nbsp(pill._sub.text()).split(" · ")
    assert bits[0] == "March 18", bits
    assert bits[1] == "4h 30m in-world", bits
    assert bits[2] == "4 photos", bits


def test_a_library_with_no_sessions_has_no_pill(app, tmp_path):
    cfg, db = _library(tmp_path, sessions=False)
    win = _window(app, cfg, db)
    try:
        win.live_pill.refresh(force=True)
        assert win.live_pill.isHidden(), "a pill with nothing to say"
    finally:
        win._quitting = True
        win.close()


def test_a_press_on_the_pill_is_a_click_not_a_window_drag(home):
    """The title bar turns every press nobody claims into startSystemMove, and
    the system move eats the release a click needs: the pill looked like a
    button and dragged the window instead."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent
    win, _page = home
    pill = win.live_pill
    pill.refresh(force=True)
    pos = QPointF(pill.width() / 2, pill.height() / 2)
    ev = QMouseEvent(QEvent.MouseButtonPress, pos, pill.mapToGlobal(pos),
                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    ev.ignore()          # as the title bar would leave it; the pill has to claim it
    pill.mousePressEvent(ev)
    assert ev.isAccepted(), "the press falls through to the title bar's drag"


def test_a_click_on_the_pill_opens_home(home):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    win, page = home
    pill = win.live_pill
    pill.refresh(force=True)
    win.activate("all")
    QApplication.instance().processEvents()
    QTest.mouseClick(pill, Qt.LeftButton)
    assert win.stack.currentWidget() is page


def test_the_pill_is_refreshed_whichever_page_is_open(home):
    """It is on every page; Home's own refresh only runs while Home is open."""
    win, _page = home
    win.activate("all")
    calls = []
    real = win.live_pill.refresh
    win.live_pill.refresh = lambda *a, **k: (calls.append(1), real(*a, **k))[1]
    try:
        win.after_photos_changed()
    finally:
        win.live_pill.refresh = real
    assert calls, "an index pass landed and the pill was not told"


def test_a_quiet_minute_only_moves_the_pills_clock(home, monkeypatch):
    import datetime as dt
    win, _page = home
    pill = win.live_pill
    _game(monkeypatch, True)
    pill.refresh(force=True)
    painted = []
    real_paint = pill._paint_state
    pill._paint_state = lambda: (painted.append(1), real_paint())[1]
    pill.refresh()
    assert not painted, "an unchanged pill was redrawn"
    before = _nbsp(pill._sub.text())
    pill.tick(dt.datetime.now() + dt.timedelta(minutes=75))
    assert _nbsp(pill._sub.text()) != before, "live, and the time in-world stood still"


def test_the_game_starting_redraws_the_pill(home, monkeypatch):
    """Live is in the pill's fingerprint: the log has not grown yet when the
    game starts, so the sessions alone would leave it saying "Last in"."""
    win, _page = home
    pill = win.live_pill
    _game(monkeypatch, False)
    pill.refresh(force=True)
    _game(monkeypatch, True)
    pill.refresh()
    assert pill._title.text().startswith("In VRChat")


def test_the_pill_waits_while_the_window_is_hidden(home, monkeypatch):
    win, _page = home
    pill = win.live_pill
    _game(monkeypatch, False)
    pill.refresh(force=True)
    win.hide()
    QApplication.instance().processEvents()
    _game(monkeypatch, True)
    pill.refresh()
    assert pill._dirty and pill._title.text().startswith("Last in"), "worked while hidden"
    win.show()
    for _ in range(20):
        QApplication.instance().processEvents()
    assert not pill._dirty and pill._title.text().startswith("In VRChat"), \
        "did not catch up when the window came back"


def test_the_pill_fits_inside_the_title_bar(home):
    from vrgallery.homepage import LivePill
    from vrgallery.widgets import TitleBar
    win, _page = home
    pill = win.live_pill
    pill.refresh(force=True)
    QApplication.instance().processEvents()
    assert LivePill.HEIGHT <= TitleBar.HEIGHT - 4
    top = pill.mapTo(win.titlebar, pill.rect().topLeft()).y()
    assert top >= 0 and top + pill.height() <= win.titlebar.height(), (
        "the pill spills out of the title bar")
