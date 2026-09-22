"""The front door: what the library looks like today, in one screen.

Every block here is a query the app already ran somewhere else, shown early and
in a form you can act on. Nothing is a new view of the library -- each tile and
each row opens a page that already exists, which is the point: this is a way IN,
not another place to be.

WHY IT IS SHAPED LIKE THIS. The library does not have even metadata coverage,
and any single-spine front page breaks on that. Photographs go back to
2023-07-25; the world and people columns only start in 2025 (VRCX's screenshot
helper was not running before that); and the session tables are built from
VRChat's own logs, which the game keeps about two days of on disk, so they hold
only what the app was running to see -- 33 days at the time of writing, growing
by one a day and impossible to backfill.

So no block here is asked to span the whole library. The figures and "on this
day" are built from `taken_at`, which every photograph has. The world shelf is
2025-on and simply shows fewer rows before that. The night card reaches into the
33-day window and gets away with it because it only ever asks for the LAST
night, which is the one night that window always holds. A block with nothing to
say hides itself rather than rendering an empty frame.
"""
import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import fmt, icons, style, widgets
from .gridmodel import MiniItem
from .pages import ThumbStripLabel


def _lab(text, size=12, colour="dim", weight=None):
    w = QLabel(text)
    w.setStyleSheet("color:%s; font-size:%dpx;%s"
                    % (style.PAL[colour], size,
                       (" font-weight:%d;" % weight) if weight else ""))
    return w


def _section(title, note=""):
    """The small capitalised label every block on this page wears."""
    row = QHBoxLayout()
    row.setSpacing(8)
    lab = QLabel(title)
    lab.setObjectName("SectionLabel")
    row.addWidget(lab)
    row.addStretch(1)
    if note:
        row.addWidget(_lab(note, 11, "faint"))
    return row


class Clickable(QFrame):
    """A frame that lights up under the pointer and calls back when clicked."""

    def __init__(self, on_click=None, parent=None):
        super().__init__(parent)
        self._on_click = on_click
        self._hover = False
        if on_click is not None:
            self.setCursor(Qt.PointingHandCursor)
            self.setAttribute(Qt.WA_Hover, True)

    def enterEvent(self, ev):
        self._hover = True
        self._sync()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._hover = False
        self._sync()
        super().leaveEvent(ev)

    def _sync(self):
        if self._on_click is None:
            return
        self.setStyleSheet(
            "QFrame#HomeRow { background:%s; border-radius:8px; }"
            % (style.PAL["surface2"] if self._hover else "transparent"))

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self._on_click is not None \
                and self.rect().contains(ev.position().toPoint()):
            self._on_click()
        super().mouseReleaseEvent(ev)


class RankRow(Clickable):
    """name / subtitle / figure -- the shape of every short list on this page."""

    def __init__(self, name, sub, figure, on_click=None, accent=False, parent=None):
        super().__init__(on_click, parent)
        self.setObjectName("HomeRow")
        self._sync()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(_lab(name, 13, "text", 600))
        if sub:
            col.addWidget(_lab(sub, 11, "faint"))
        lay.addLayout(col, 1)
        chip = QLabel(figure)
        chip.setStyleSheet(
            "color:%s; background:%s; border-radius:9px; padding:2px 9px;"
            "font-size:11px; font-weight:700;"
            % (style.PAL["text"] if accent else style.PAL["dim"],
               style.PAL["surface2"]))
        lay.addWidget(chip, 0, Qt.AlignVCenter)


class CoverTile(QWidget):
    """A thumbnail with a title and a line under it.

    The picture itself is a ThumbStripLabel, so it comes off the same cache and
    the same per-photo watch registry the memories strips use -- a cover that
    arrives late wakes this tile and nothing else.
    """

    def __init__(self, main, cache, item, title, sub, on_click, w=150, h=94,
                 parent=None):
        super().__init__(parent)
        self.setFixedWidth(w)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(5)
        if item is not None:
            thumb = ThumbStripLabel(main, cache, item, on_click, w, h)
            v.addWidget(thumb)
        else:
            blank = QFrame()
            blank.setFixedSize(w, h)
            blank.setStyleSheet("background:%s; border-radius:6px;"
                                % style.PAL["surface2"])
            v.addWidget(blank)
        t = _lab(title, 12, "text", 600)
        t.setToolTip(title)
        v.addWidget(t)
        v.addWidget(_lab(sub, 11, "faint"))


class Shelf(QWidget):
    """A labelled row of cover tiles, left-aligned, that stops at what fits."""

    def __init__(self, title, note="", parent=None):
        super().__init__(parent)
        self._v = QVBoxLayout(self)
        self._v.setContentsMargins(0, 0, 0, 0)
        self._v.setSpacing(10)
        self._v.addLayout(_section(title, note))
        # A plain row laid the tiles out wider than the page and Qt cut the
        # overflowing one in half -- at 960 px, which is the half-screen width
        # the app is meant to survive, three of five ran off the edge and took a
        # horizontal scrollbar with them. A flow wraps instead.
        self._holder = QWidget(self)
        self._flow = widgets.FlowLayout(self._holder, 0, 12, 12)
        self._v.addWidget(self._holder)

    def add(self, tile):
        self._flow.addWidget(tile)


class LastNight(QFrame):
    """The one block built from the logs, and the only one that needs to be.

    It is this page's "carry on where you left off": the most recent evening,
    how long it ran, how many places it moved through and who was there for it,
    with the night's own photographs beside it.

    Everything inside wraps. Laid out as one fixed row -- a text column, then
    three 168 px thumbnails, with the people on an unwrapping line -- the card
    would not go below 953 px, and a window snapped to half a 1920 screen has
    about 712 to give it. It took the whole page over the edge and grew a
    horizontal scrollbar.
    """

    def __init__(self, main, cache, night, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.main = main
        outer = widgets.FlowLayout(self, 0, 18, 14)
        outer.setContentsMargins(20, 18, 20, 18)

        text = QWidget(self)
        text.setMinimumWidth(300)
        text.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        col = QVBoxLayout(text)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(7)
        head = QLabel("LAST NIGHT")
        head.setObjectName("SectionLabel")
        col.addWidget(head)

        day = datetime.date.fromisoformat(night["day"])
        title = QLabel(day.strftime("%A · %d %B %Y"))
        title.setStyleSheet("font-size:19px; font-weight:700; color:%s;"
                            % style.PAL["text"])
        col.addWidget(title)

        bits = []
        mins = int(night["mins"] or 0)
        if mins:
            bits.append("%dh %02dm in-world" % (mins // 60, mins % 60))
        if night["stops"]:
            bits.append("%d %s" % (night["stops"],
                                   fmt.plural(night["stops"], "stop")))
        if night["world_name"]:
            bits.append(night["world_name"])
        bits.append("%d %s" % (night["photos"],
                               fmt.plural(night["photos"], "photo"))
                    if night["photos"] else "no photographs")
        sub = _lab(" · ".join(bits), 12, "dim")
        sub.setWordWrap(True)
        col.addWidget(sub)

        if night["people"]:
            chips = QWidget(text)
            flow = widgets.FlowLayout(chips, 0, 6, 6)
            for name, m in night["people"]:
                flow.addWidget(_person_chip(main, name, _short_hours(m)))
            col.addWidget(chips)
        # no trailing stretch: it made the text block claim the card's full
        # height and left a band of empty plate under the people chips
        outer.addWidget(text)

        # The thumbnails go straight into the card's own flow rather than into a
        # flow of their own: a nested one is handed its sizeHint width, which is
        # one tile, so three pictures stacked into a column with the width for a
        # row sitting empty beside them.
        for r in night.get("shots", [])[:3]:
            item = MiniItem(r["id"], r["path"], r["mtime"], r["filesize"], 1)
            outer.addWidget(ThumbStripLabel(
                main, cache, item,
                lambda d=night["day"]: main.push_day(d), 168, 100))


def _person_chip(main, name, note):
    """A name you can click, in the pill the rest of the app uses for people."""
    c = QLabel("%s  %s" % (name, note) if note else name)
    c.setCursor(Qt.PointingHandCursor)
    c.setStyleSheet("background:%s; color:%s; border-radius:11px;"
                    "padding:3px 10px; font-size:11px;"
                    % (style.PAL["surface2"], style.PAL["text"]))
    c.mouseReleaseEvent = lambda _e, n=name: main.push_person(n)
    return c


def _short_hours(minutes):
    m = int(minutes or 0)
    return "%dm" % m if m < 60 else "%.1fh" % (m / 60.0)


class HomePage(QWidget):
    """The page behind the Home entry."""

    def __init__(self, main, cache, parent=None):
        super().__init__(parent)
        self.main = main
        self.cache = cache
        self.scroll, self.holder, self.vbox = widgets.scroll_body(self)
        self.head = widgets.PageHead(self, "Home")
        self.lab_title, self.lab_sub = self.head.lab_title, self.head.lab_sub
        self.btn_random = widgets.ghost_btn("Random day", "shuffle")
        self.btn_random.clicked.connect(self._random_day)
        self.head.add(self.btn_random)
        self.head.attach(self.scroll, reserve_in=self.vbox)
        self._shown = None            # see refresh()

    # ------------------------------------------------------------ building

    def refresh(self, force=False):
        """Rebuild, unless nothing this page reads has changed.

        The palette is part of the fingerprint on purpose: the labels here bake
        their colours into inline stylesheets, so a theme swapped while another
        page was open has to be picked up when this one comes back.
        """
        selfn = self.main.cfg.self_names
        stamp = (self.main.db.home_stamp(selfn),
                 style.PAL["bg"], self.main.cfg.get("accent"))
        if not force and stamp == self._shown:
            return
        self._shown = stamp

        while self.vbox.count():
            it = self.vbox.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        total, size, favs = self.main.db.counts()
        self.lab_sub.setText("%s %s · %s"
                             % (fmt.count_label(total), fmt.plural(total, "photo"),
                                fmt.human_size(size)))

        self._add_figures(total, size)
        self._add_last_night(selfn)
        self._add_shelf(self._memories_shelf())
        self._add_shelf(self._worlds_shelf())
        # The two lists go side by side because they are the same shape and
        # roughly the same height. Pairing a list with a SHELF instead, which is
        # what this page did first, leaves whichever column is shorter sitting
        # in a block of empty page -- two photographs on the left against six
        # rows on the right was most of a screen of nothing.
        self._add_columns(self._top_people(selfn), self._drifted(selfn))
        self.vbox.addStretch(1)

    def _add_figures(self, total, size):
        db = self.main.db
        days = db.distinct_days()
        box = QWidget()
        row = widgets.FlowLayout(box, 0, 12, 12)
        c1 = widgets.StatCard("image")
        c1.set(fmt.count_label(total), "photographs")
        c2 = widgets.StatCard("film")
        c2.set(fmt.human_size(size), "on disk")
        c3 = widgets.StatCard("calendar")
        c3.set(fmt.count_label(days), "days you took one")
        c4 = widgets.StatCard("globe")
        c4.set(fmt.count_label(self._world_count()), "worlds")
        for c in (c1, c2, c3, c4):
            # a flow gives every item its size hint, and StatCard is Expanding
            # with no width of its own -- without a floor they collapse to the
            # icon and the number is clipped
            c.setMinimumWidth(212)
            row.addWidget(c)
        self.vbox.addWidget(box)

    def _world_count(self):
        rows = self.main.db.recent_worlds(limit=10000, min_photos=1)
        return len(rows)

    def _add_last_night(self, selfn):
        night = self.main.db.last_night(selfn)
        if not night:
            return
        f = self.main.db.query_photos(_day_filter(night["day"]))
        night["shots"] = list(f)[:3]
        self.vbox.addWidget(LastNight(self.main, self.cache, night))

    def _add_shelf(self, shelf):
        if shelf is not None:
            self.vbox.addWidget(shelf)

    def _add_columns(self, left, right):
        """Two lists abreast, or stacked when there is no room for two.

        A fixed two-column row is what put this page's floor back up to 764 px
        after the shelves had already been taught to wrap. They go in a flow for
        the same reason everything else on the page does.
        """
        live = [w for w in (left, right) if w is not None]
        if not live:
            return
        if len(live) == 1:
            self.vbox.addWidget(live[0])
            return
        # A stretching row, not a flow: a flow hands each item its size hint and
        # never widens it, so on a full-screen window the two lists sat at their
        # minimum with a third of the page empty beside them. The floor is small
        # enough that both still fit side by side at half-screen.
        row = QHBoxLayout()
        row.setSpacing(24)
        for w in live:
            w.setMinimumWidth(260)
            row.addWidget(w, 1, Qt.AlignTop)
        box = QWidget()
        box.setLayout(row)
        self.vbox.addWidget(box)

    def _memories_shelf(self):
        today = datetime.date.today()
        mmdd = "%02d-%02d" % (today.month, today.day)
        rows = self.main.db.memories(mmdd, today.year)
        if not rows:
            return None
        shelf = Shelf("ON THIS DAY", today.strftime("%d %B"))
        for r in rows[:5]:
            day = "%s-%s" % (r["y"], mmdd)
            shots = list(self.main.db.query_photos(_day_filter(day)))[:1]
            item = (MiniItem(shots[0]["id"], shots[0]["path"], shots[0]["mtime"],
                             shots[0]["filesize"], 1) if shots else None)
            years = today.year - int(r["y"])
            shelf.add(CoverTile(
                self.main, self.cache, item,
                fmt.years_ago_label(years),
                "%d %s" % (r["cnt"], fmt.plural(r["cnt"], "photo")),
                lambda d=day: self.main.push_day(d)))
        return shelf

    def _top_people(self, selfn):
        rows = self.main.db.top_people(6, selfn) if hasattr(self.main.db, "top_people") \
            else None
        if not rows:
            return None
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        v.addLayout(_section("MOST PHOTOGRAPHED"))
        for r in rows:
            v.addWidget(RankRow(
                r["name"], "last seen %s" % r["last_day"] if "last_day" in r.keys()
                else "", str(r["c"]),
                lambda n=r["name"]: self.main.push_person(n), accent=True))
        return box

    def _worlds_shelf(self):
        rows = self.main.db.recent_worlds(6)
        if not rows:
            return None
        shelf = Shelf("WHERE YOU'VE BEEN LATELY")
        # photos_by_ids already hands back {id: row}
        by_id = self.main.db.photos_by_ids([r["cover_id"] for r in rows])
        for r in rows:
            c = by_id.get(r["cover_id"])
            item = (MiniItem(c["id"], c["path"], c["mtime"], c["filesize"], 1)
                    if c else None)
            shelf.add(CoverTile(
                self.main, self.cache, item, r["world_name"],
                "%d %s" % (r["c"], fmt.plural(r["c"], "photo")),
                lambda wid=r["world_id"], nm=r["world_name"]:
                    self.main.push_world(wid, nm)))
        return shelf

    def _drifted(self, selfn):
        """Regulars who stopped appearing. The only block here that is about an
        absence, and the only one built from a query that had no caller."""
        rows = self.main.db.people_last_seen(selfn, min_photos=8)
        today = datetime.date.today()
        out = []
        for r in rows:
            try:
                last = datetime.date.fromisoformat(r["last_at"][:10])
                first = datetime.date.fromisoformat(r["first_at"][:10])
            except (TypeError, ValueError):
                continue
            gap, run = (today - last).days, (last - first).days
            # A run as well as a gap: somebody photographed eight times in one
            # week and never again was a night out, not a friendship.
            if gap >= 90 and run >= 30:
                out.append((gap, run, r))
        if not out:
            return None
        # key on the gap alone: a plain reverse sort falls through to comparing
        # the sqlite3.Row when two people have been away the same number of days
        out.sort(key=lambda t: t[0], reverse=True)
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)
        v.addLayout(_section("YOU HAVEN'T SEEN THEM IN A WHILE",
                             "%d in all" % len(out) if len(out) > 4 else ""))
        for gap, run, r in out[:6]:
            v.addWidget(RankRow(
                r["name"],
                "%d %s over %d days" % (r["c"], fmt.plural(r["c"], "photo"), run),
                _gap_label(gap),
                lambda n=r["name"]: self.main.push_person(n)))
        return box

    # ------------------------------------------------------------ actions

    def _random_day(self):
        r = self.main.db.random_rich_day()
        if r:
            self.main.push_day(r["day"])
        else:
            self.main.toast("Not enough photos for that yet.", "info")


def _gap_label(days):
    """How long ago, in the coarsest unit that still separates two people.

    "a year" for everything between one and two was the first try, and on this
    library it printed three times in a row for gaps of 548, 442 and 414 days --
    the same label for people who drifted four months apart. Months carry on up
    to two years for that reason.
    """
    if days >= 730:
        return "%d years" % (days // 365)
    if days >= 60:
        return "%d months" % round(days / 30.4)
    return "%d days" % days


def _day_filter(day):
    from .db import PhotoFilter
    return PhotoFilter(day=day, sort_desc=False)
