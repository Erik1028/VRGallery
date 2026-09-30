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
2025-on and simply shows fewer rows before that. The sitting card reaches into
the log window and gets away with it because it only ever asks for the LAST
sitting -- or the one happening now -- which is the one thing that window always
holds. A block with nothing to say hides itself rather than rendering an empty
frame.
"""
import datetime
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import fmt, icons, style, vrclog, widgets, winutil
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
    lab = QLabel(style.caps(title))
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


LIVE_EXE = "VRChat.exe"

# A night belongs to the evening it started on. Six in the morning is where a
# VR night ends in this library: 32% of sessions start between midnight and
# six, and read by calendar date every one of them was "the next day".
NIGHT_TURNS = datetime.timedelta(hours=6)


def sitting_label(start, end, live, now):
    """The heading for a sitting, in the words you would use for it.

    "LAST NIGHT" was a constant, so on a Wednesday lunchtime it sat above a
    Tuesday afternoon, and a week later above the same Tuesday afternoon.

    The part of the day is read from the MIDDLE of the sitting, not its start:
    one that began at 11:02 and ran to 16:23 was an afternoon, and was headed
    "morning". And only a night is dated from six in the morning. Applied to an
    afternoon too, that shift kept Tuesday's afternoon "THIS AFTERNOON" until
    six on Wednesday -- at one in the morning, over a line saying "Tuesday".
    """
    if live:
        return "RIGHT NOW · IN VRCHAT"
    mid = start + (end - start) / 2
    night = end.date() > start.date() or mid.hour >= 18 or mid.hour < 6
    if night:
        part = "NIGHT"
        eve, today = (start - NIGHT_TURNS).date(), (now - NIGHT_TURNS).date()
    else:
        part = "MORNING" if mid.hour < 12 else "AFTERNOON"
        eve, today = start.date(), now.date()
    ago = (today - eve).days
    if ago <= 0:
        return {"NIGHT": "TONIGHT", "MORNING": "THIS MORNING",
                "AFTERNOON": "THIS AFTERNOON"}[part]
    if ago == 1:
        return "LAST NIGHT" if night else "YESTERDAY " + part
    if ago < 7:
        return "%s %s" % (fmt.DAYS[eve.weekday()].upper(), part)
    # a plain date is the START's date, as the line under it is: "SEPTEMBER 18"
    # over "Saturday · September 19 · 00:30" was one sitting with two dates
    return "%s %d" % (fmt.MONTHS[start.month - 1].upper(), start.day)


def is_live(newest_log):
    """Is the game running, and is the newest session in the library the one it
    is writing? Both: the game alone would call a sitting from yesterday "right
    now" in the seconds between the game starting and the log pass catching up.
    Shared by the Home card and the title bar, so the two can never disagree."""
    if not newest_log or not winutil.process_running(LIVE_EXE):
        return False
    logs = vrclog.find_logs()
    return bool(logs) and os.path.basename(logs[-1]) == newest_log


def live_minutes(sit, now):
    """In-world time of a sitting that is still going: what the log has, plus
    the session running since its last line. Not "now - start", which counted
    the gaps between game restarts that a sitting takes in."""
    return sit["mins"] + max(0.0, (now - sit["end"]).total_seconds() / 60)


def _span(minutes):
    m = int(round(minutes or 0))
    return "%dm" % m if m < 60 else "%dh %02dm" % (m // 60, m % 60)


def _short_hours(minutes):
    m = int(minutes or 0)
    return "%dm" % m if m < 60 else "%.1fh" % (m / 60.0)


def _keep(text):
    """One bit of a " · " line that must not break inside itself when the line
    wraps: "3h 00m" and "in-world" on different lines read as two facts."""
    return text.replace(" ", "\u00a0")


class PersonChip(Clickable):
    """A person from the sitting, as a pill.

    A link only when there is somewhere to go: somebody you spent the evening
    with but never photographed has no person page worth the name, and the chip
    that opened one anyway landed on "Nothing here", which reads as a broken
    library. Those chips are plain and say why on hover.
    """

    def __init__(self, main, person, live=False, parent=None):
        target = person.get("photo_name")
        super().__init__((lambda n=target: main.push_person(n)) if target else None,
                         parent)
        self.setObjectName("HomeRow")
        self._sync()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 3, 10, 3)
        lay.setSpacing(6)
        if live and person.get("present"):
            dot = QLabel("●")
            dot.setStyleSheet("color:%s; font-size:9px;" % style.PAL["ok"])
            dot.setToolTip("In the instance with you now")
            lay.addWidget(dot)
        lay.addWidget(_lab(person["name"], 11, "text" if target else "dim"))
        lay.addWidget(_lab(_short_hours(person["minutes"]), 11, "faint"))
        tips = []
        if live and person.get("present"):
            tips.append("In the instance with you now")
        if not target:
            tips.append("No photographs of %s yet" % person["name"])
        elif target != person["name"]:
            tips.append("Photographed as %s" % target)
        if tips:
            self.setToolTip("\n".join(tips))

    def _sync(self):
        self.setStyleSheet(
            "QFrame#HomeRow { background:%s; border-radius:11px; }"
            % (style.PAL["hover"] if self._hover and self._on_click
               else style.PAL["surface2"]))


class SittingCard(QFrame):
    """The last stretch of time in VRChat, or the one happening now.

    This is the one block on the page built from the logs, and the only one that
    has to be: it only ever asks about the most recent sitting, which is the one
    thing a log window a month deep is guaranteed to hold.

    While the game is running it is live -- the world you are in, since when,
    who is in the room with you, what you are wearing -- and it keeps its clock
    moving between rebuilds through tick(). Once the game closes it becomes the
    sitting that just ended, headed in the words you would use for it.

    Laid out as the text, which stretches, and a ThumbStrip, which fits as many
    photographs as the width allows and says "+N" for the rest. Two earlier
    shapes failed at opposite ends. One fixed row -- text, then three 168 px
    tiles -- would not go below 953 px, and half a 1920 screen gives the page
    about 712. A flow fixed that and broke the wide case instead: a flow places
    every item at its size hint and never stretches one, so the text column sat
    at its 300 px floor and wrapped "no / photographs" onto two lines beside a
    card that was mostly empty.
    """

    def __init__(self, main, cache, sit, live, now, open_photos, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.main = main
        self._sit = sit
        self._live = live
        outer = QHBoxLayout(self)
        outer.setContentsMargins(20, 18, 20, 18)
        outer.setSpacing(20)

        text = QWidget(self)
        text.setMinimumWidth(260)
        col = QVBoxLayout(text)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(7)

        head = QLabel(style.caps(sitting_label(sit["start"], sit["end"], live, now)))
        head.setObjectName("SectionLabel")
        if live:
            head.setStyleSheet("color:%s;" % style.PAL["ok"])
        col.addWidget(head)

        worlds = sit["worlds"]
        where = (sit["world_name"] if live else (worlds[0][1] if worlds else "")) \
            or "Somewhere in VRChat"
        title = QLabel(where)
        title.setWordWrap(True)
        title.setStyleSheet("font-size:19px; font-weight:700; color:%s;"
                            % style.PAL["text"])
        col.addWidget(title)

        self._sub = _lab("", 12, "dim")
        self._sub.setWordWrap(True)
        col.addWidget(self._sub)
        self.tick(now)

        # Live, only the people in the room now. Under "RIGHT NOW" a row that
        # also held everybody met earlier in the night read as "these six are
        # here with me" when five of them had left hours ago; a 9 px dot was
        # the only difference. The rest are counted, not listed.
        people = list(sit["people"])
        if live:
            here = [d for d in people if d["present"]]
            gone = sit["people_total"] - len(here)
            people, more, more_word = here, gone, "earlier"
        else:
            more = sit["people_total"] - min(6, len(people))
            more_word = "more"
        if people or more > 0:
            chips = QWidget(text)
            flow = widgets.FlowLayout(chips, 0, 6, 6)
            for d in people[:6]:
                flow.addWidget(PersonChip(main, d, live))
            if live:
                more += max(0, len(people) - 6)
            if more > 0:
                flow.addWidget(_lab("+%d %s" % (more, more_word), 11, "faint"))
            col.addWidget(chips)
        outer.addWidget(text, 1, Qt.AlignTop)

        # Newest first: on a live card that is the picture you just took. Every
        # tile opens the whole sitting in the lightbox at its own photograph --
        # not the day, because a sitting that crosses midnight is two days and
        # the day page for either is the wrong set of pictures.
        #
        # Only the tiles that could ever be on screen are built -- a card is
        # never wider than eight -- and "+N" is told how many more there are.
        # Building one per photo made two hundred widgets, each registered for
        # repaints, to show five. "+N" opens the sitting at its start: it
        # stands for the older photographs that did not fit, and opening at
        # the newest, as it first did, landed on the tile already beside it.
        ids = sit["photo_ids"]
        if ids:
            from .pages import ThumbStrip
            SHOW = 8
            strip = ThumbStrip(max_h=100)
            newest = ids[-SHOW:]
            rows = main.db.photos_by_ids(newest)
            for pid in reversed(newest):
                r = rows.get(pid)
                if r is None:
                    continue
                strip.add(main, cache,
                          MiniItem(r["id"], r["path"], r["mtime"], r["filesize"], 1),
                          lambda i=ids.index(pid): open_photos(ids, i))
            strip.set_more(lambda: open_photos(ids, 0), len(ids) - len(newest))
            # As wide as its tiles want and no wider: a strip that took three
            # fifths of the card left a single photograph floating mid-card.
            k = min(len(ids), SHOW)
            strip.setMaximumWidth(int(k * 100 * ThumbStrip.RATIO + (k - 1) * ThumbStrip.GAP))
            outer.addWidget(strip, 1, Qt.AlignTop)
        # with no photographs the text has the whole card: holding room for a
        # strip that is not there wrapped "no / photographs" at 40% of the width

    def tick(self, now):
        """Rewrite the line that depends on the clock. Cheap: one label."""
        sit, bits = self._sit, []
        start, end = sit["start"], sit["end"]
        if self._live:
            bits.append("since %s" % start.strftime("%H:%M"))
            # In-world time, the same measure the card shows once the game
            # closes: the sessions logged so far plus the one still running.
            # "now - start" counted the gaps too -- a sitting takes in restarts
            # up to 90 minutes apart -- and one read 8h 17m live and 6h 34m a
            # minute after quitting.
            bits.append("%s in-world so far" % _span(live_minutes(sit, now)))
            kind = vrclog.INSTANCE_LABELS.get(sit["instance_type"], "")
            if kind:
                bits.append(kind)
            if sit["avatar"]:
                bits.append("as %s" % sit["avatar"])
        else:
            # the grid's day headers say "Sunday · September 20"; so does this
            bits.append("%s · %s %d" % (fmt.DAYS[start.weekday()],
                                        fmt.MONTHS[start.month - 1], start.day))
            tail = end.strftime("%H:%M")
            if end.date() != start.date():
                tail += " " + fmt.DAYS[end.weekday()][:3]
            bits.append("%s → %s" % (start.strftime("%H:%M"), tail))
            bits.append("%s in-world" % _span(sit["mins"]))
            n = len(sit["worlds"])
            if n > 1:
                bits.append("%d worlds" % n)
        n = len(sit["photo_ids"])
        bits.append("%d %s" % (n, fmt.plural(n, "photo")) if n else "no photographs")
        self._sub.setText(" · ".join(_keep(b) for b in bits))


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
        self._card_shown = None
        self._card = None
        self._dirty = False
        # Once a minute while the page is on screen: long enough to cost nothing,
        # short enough that a sitting's clock, the switch to "right now" when the
        # game starts and back when it closes, and "on this day" at midnight all
        # land without anybody having to leave the page and come back.
        self._clock = QTimer(self)
        self._clock.setInterval(60000)
        self._clock.timeout.connect(self._on_clock)

    def showEvent(self, ev):
        super().showEvent(ev)
        self._clock.start()
        if self._dirty:
            QTimer.singleShot(0, self.refresh)

    def _on_screen(self):
        return self.isVisible() and not self.window().isMinimized()

    def hideEvent(self, ev):
        self._clock.stop()
        super().hideEvent(ev)

    def _on_clock(self):
        if self.isVisible():
            self.refresh()

    def _live(self, newest_log):
        """Is the game running, and is the newest session in the library the
        one it is writing? Both, or the card would call a sitting from yesterday
        "right now" in the seconds between the game starting and the log pass
        catching up."""
        return is_live(newest_log)

    # ------------------------------------------------------------ building

    def refresh(self, force=False):
        """Rebuild, unless nothing this page reads has changed.

        The palette is part of the fingerprint on purpose: the labels here bake
        their colours into inline stylesheets, so a theme swapped while another
        page was open has to be picked up when this one comes back.
        """
        # Not while nobody can see it. The app lives in the tray, Home stays
        # the current page there, and every log pass during an evening in
        # VRChat rebuilt it for nobody. It catches up when it is shown.
        if not force and not self._on_screen():
            self._dirty = True
            return
        self._dirty = False
        selfn = self.main.cfg.self_names
        now = datetime.datetime.now()
        photos, sessions = self.main.db.home_stamp(selfn)
        live = self._live(sessions[-1])
        # Two fingerprints. The page's: what the figures, shelves and lists
        # read, plus today's date, because "on this day" is today -- without it
        # the page reopened from the tray in the morning said "ON THIS DAY 22
        # September" on the 23rd. The card's: the sessions, which move on every
        # log pass while the game runs, the evening's date for its heading, and
        # whether the game is live.
        stamp = (photos, tuple(sorted(selfn)), style.PAL["bg"],
                 self.main.cfg.get("accent"), datetime.date.today())
        card_stamp = (sessions, (now - NIGHT_TURNS).date(), now.date(), live)
        if not force and stamp == self._shown:
            if card_stamp != self._card_shown:
                self._rebuild_card(selfn, now, live, card_stamp)
            elif self._card is not None:
                self._card.tick(now)
            return
        self._shown = stamp
        self._card_shown = card_stamp
        self._now, self._is_live = now, live

        self._card = None
        while self.vbox.count():
            it = self.vbox.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        total, size, favs = self.main.db.counts()
        self.lab_sub.setText("%s %s · %s"
                             % (fmt.count_label(total), fmt.plural(total, "photo"),
                                fmt.human_size(size)))

        self._add_figures(total, size)
        self._add_sitting(selfn)
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

    def _add_sitting(self, selfn):
        sit = self.main.db.last_sitting(
            selfn, until=self._now if self._is_live else None)
        if not sit:
            return
        self._card = SittingCard(self.main, self.cache, sit, self._is_live,
                                 self._now, self._open_photos)
        self.vbox.addWidget(self._card)

    def _rebuild_card(self, selfn, now, live, card_stamp):
        """Just the card, in its place. What changes every fifteen seconds while
        the game runs is the evening, not the library."""
        self._card_shown = card_stamp
        self._now, self._is_live = now, live
        old = self._card
        idx = self.vbox.indexOf(old) if old is not None else 1  # after the figures
        self._card = None
        if old is not None:
            self.vbox.removeWidget(old)
            old.hide()
            old.deleteLater()
        sit = self.main.db.last_sitting(selfn, until=now if live else None)
        if sit:
            self._card = SittingCard(self.main, self.cache, sit, live, now,
                                     self._open_photos)
            self.vbox.insertWidget(max(0, idx), self._card)

    def _open_photos(self, ids, pos):
        """The sitting's photographs in the lightbox, starting at `pos`.

        Not the day: a sitting that crosses midnight is two days, and the day
        page for either of them is the wrong set of pictures."""
        from .gridmodel import PhotoItem
        rows = self.main.db.photos_by_ids_full(ids)
        items = [PhotoItem(r) for r in rows]
        if items:
            self.main.open_lightbox(self, items, max(0, min(pos, len(items) - 1)))

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


class LivePill(Clickable):
    """Where you are in VRChat, in the title bar, on every page.

    Mixtape keeps a now-playing pill in its caption strip; this is VR Gallery's.
    Erik asked for this one piece of Mixtape's design and nothing else of it
    (2026-09-25). It is there whether or not the game runs, on purpose: gone
    whenever the game was closed, the title bar would change height each time
    VRChat started or stopped and every page under it would jump.

    The world is the title, alone. The first version led with "In VRChat · " /
    "Last in VRChat · ", which ate a third of the line, so the one thing worth
    reading was the part that got cut -- Erik's own screenshot ended at "VUdon
    Vehicles - Desert (Open ...". The state is a small tag at the head of the
    second line instead, in the letter-spaced capitals Home's own headings
    wear: IN VRCHAT in the Home card's green, LAST IN VRCHAT in grey. While the
    game runs the tile is green and carries an online dot on its corner; between
    sessions it is a grey tile like the ones on Home's stat cards, and the title
    is a step quieter than live but not greyed out -- the first version's idle
    pill read as a disabled control (2026-09-27, picked by three judges from
    four variants rendered in the real window).

    It reads exactly what the Home card reads (last_sitting, is_live,
    live_minutes), so the two cannot tell different stories. A click opens Home.
    """

    HEIGHT = 40      # 6 px of air above and below it in the 52 px title bar
    TILE = 32
    INSET = 4        # tile to the inside of the border; its radius is 10 - 4
    MAX_W = 380

    def __init__(self, main, parent=None):
        super().__init__(lambda: main.activate("home"), parent)
        self.main = main
        self.setObjectName("LivePill")
        self.setFixedHeight(self.HEIGHT)
        self.setMinimumWidth(240)
        self.setMaximumWidth(self.MAX_W)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._key = None
        self._sit = None
        self._live = False
        self._dirty = False
        self._clock = QTimer(self)
        self._clock.setInterval(60000)
        self._clock.timeout.connect(self.refresh)
        if style.CLASSIC:
            self._classic_layout()
            self.hide()
            return
        lay = QHBoxLayout(self)
        lay.setContentsMargins(self.INSET, 0, 12, 0)
        lay.setSpacing(10)
        self._tile = _PillTile(self.TILE, self)
        lay.addWidget(self._tile, 0, Qt.AlignVCenter)
        col = QVBoxLayout()
        # the text block, cap top to last baseline, lands on the pill's middle
        col.setContentsMargins(0, 1, 0, 0)
        col.setSpacing(0)
        self._title = widgets.ElidedLabel("")
        self._title.setFixedHeight(18)       # a whole line: descenders survive eliding
        self._sub = _PillFacts()
        self._sub.setFixedHeight(15)
        self._sub.setStyleSheet("font-size:11px;")
        col.addWidget(self._title)
        col.addWidget(self._sub)
        col.addStretch(1)
        lay.addLayout(col, 1)
        self._dot = _PillDot(self)
        self._dot.hide()
        self.hide()                  # until there is a sitting to talk about

    def _classic_layout(self):
        """The Windows 95 look: a sunken panel of the status bar -- the globe,
        the world, then the state and the facts, on one line."""
        from . import classic
        self.setFixedHeight(classic.STATUS_H - 2)
        self.setMinimumWidth(200)
        self.setMaximumWidth(560)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 0, 6, 0)
        lay.setSpacing(5)
        self._tile = QLabel()
        self._tile.setFixedSize(16, 16)
        self._tile.setPixmap(classic.icon("globe"))
        lay.addWidget(self._tile, 0, Qt.AlignVCenter)
        self._title = widgets.ElidedLabel("")
        lay.addWidget(self._title, 1)
        self._sub = _PillFacts()
        self._sub.setFixedHeight(16)
        lay.addWidget(self._sub, 0)
        self._dot = QWidget(self)    # 1995 had no presence dot; the tag says it
        self._dot.hide()

    def paintEvent(self, ev):
        if style.CLASSIC:
            from PySide6.QtGui import QPainter
            from . import classic
            p = QPainter(self)
            classic.bevel(p, self.rect(), "thin")
            p.end()
            return
        super().paintEvent(ev)

    # a press here is a click on the pill, not the start of a window drag: the
    # title bar under it turns every unclaimed press into startSystemMove, and
    # the system move swallows the release the click needs
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            ev.accept()
            return
        super().mousePressEvent(ev)

    def showEvent(self, ev):
        super().showEvent(ev)
        self._clock.start()

    def hideEvent(self, ev):
        self._clock.stop()
        super().hideEvent(ev)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._place_dot()

    def _place_dot(self):
        """On the tile's bottom-right corner, wherever the layout put the tile,
        and far enough in that its ring clears the pill's border."""
        dot = getattr(self, "_dot", None)
        if dot is None:
            return
        g = self._tile.geometry()
        dot.move(g.right() - 11, g.bottom() - 11)
        dot.raise_()

    def _sync(self):
        if style.CLASSIC:
            self.update()            # painted: a sunken status-bar panel
            return
        P = style.PAL
        self.setStyleSheet(
            "QFrame#LivePill { background:%s; border:1px solid %s; border-radius:10px; }"
            % (P["hover"] if self._hover else P["surface"],
               P["border2"] if self._hover else P["border"]))
        dot = getattr(self, "_dot", None)
        if dot is not None:
            dot.update()             # its ring is the pill's colour, hover included

    def refresh(self, force=False):
        win = self.window()
        if not force and (not win.isVisible() or win.isMinimized()):
            self._dirty = True
            return
        self._dirty = False
        now = datetime.datetime.now()
        selfn = self.main.cfg.self_names
        _photos, sessions = self.main.db.home_stamp(selfn)
        live = is_live(sessions[-1])
        key = (sessions, live, (now - NIGHT_TURNS).date(), now.date(),
               style.PAL["bg"])
        if not force and key == self._key:
            self.tick(now)
            return
        self._key = key
        sit = self.main.db.last_sitting(selfn, until=now if live else None)
        if not sit:
            self._sit = None
            self.hide()
            return
        self._sit, self._live = sit, live
        self._paint_state()
        self.tick(now)
        self.show()

    def _where(self):
        sit = self._sit
        return (sit["world_name"] if self._live
                else (sit["worlds"][0][1] if sit["worlds"] else "")) or "Unnamed world"

    def _paint_state(self):
        P = style.PAL
        live = self._live
        self._tile.live = live
        self._tile.update()
        self._title.setText(self._where())
        title = P["text"] if live else _blend(P["text"], P["dim"], 0.25)
        self._title.setStyleSheet("color:%s; font-size:13px; font-weight:600;" % title)
        f = self._sub
        if live:
            f.tag, f.tag_colour = "IN VRCHAT", P["ok"]
        else:
            # a step brighter than `faint`, which fell under 4.5:1 on hover
            f.tag, f.tag_colour = "LAST IN VRCHAT", _blend(P["faint"], P["dim"], 0.55)
        if style.CLASSIC:
            f.tag = "In VRChat:" if live else "Last in VRChat:"
            f.tag_colour = P["ok"] if live else P["text"]
        f.fact_colour, f.sep_colour = P["dim"], P["faint"]
        f.updateGeometry()
        f.update()
        self._dot.setVisible(live and not style.CLASSIC)
        self._place_dot()
        self._sync()

    def tick(self, now):
        """The line that depends on the clock. One label."""
        sit = self._sit
        if sit is None:
            return
        n = len(sit["photo_ids"])
        if self._live:
            bits = [vrclog.INSTANCE_LABELS.get(sit["instance_type"], ""),
                    "%s in-world" % _span(live_minutes(sit, now))]
        else:
            when = sitting_label(sit["start"], sit["end"], False, now)
            bits = [when[:1] + when[1:].lower(), "%s in-world" % _span(sit["mins"])]
        if n:
            bits.append("%d %s" % (n, fmt.plural(n, "photo")))
        self._sub.setText(" · ".join(b for b in bits if b))
        if style.CLASSIC:
            # on one line with the world: the facts keep their width and the
            # world's name is what gets elided (the tooltip has all of it)
            self._sub.setMinimumWidth(self._sub.full_width())
        # the bar elides a long name; the tooltip is where the whole of it is
        self.setToolTip("%s\n%s\n%s\nClick to open Home"
                        % ("In VRChat now" if self._live else "Last in VRChat",
                           self._where(), self._sub.text().replace("\u00a0", " ")))


def _blend(a, b, t):
    """#rrggbb from a to b: t=0 is a, t=1 is b. Derived from the palette in
    force, so every palette gets its own in-between."""
    from PySide6.QtGui import QColor
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * t),
                  round(ca.green() + (cb.green() - ca.green()) * t),
                  round(ca.blue() + (cb.blue() - ca.blue()) * t)).name()


def _ink_on(fill):
    """The glyph colour for a coloured tile, as Mixtape's Theme.OnColor picks
    it: the page's own dark on a light fill, white on a dark one. White on the
    mint live tile measured 1.7:1."""
    from PySide6.QtGui import QColor
    c = QColor(fill)
    luma = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
    return style.PAL["bg"] if luma > 145 else "#ffffff"


class _PillTile(QWidget):
    """The pill's rounded tile with the globe. Painted rather than a pixmap, so
    it is drawn at the DPR of whichever screen the window is on now."""

    RADIUS = 6.0
    GLYPH = 18       # 32 - 18 is even: the glyph sits on whole pixels

    def __init__(self, size, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.live = False

    def moveEvent(self, ev):
        super().moveEvent(ev)
        place = getattr(self.parent(), "_place_dot", None)
        if place is not None:
            place()

    def paintEvent(self, _ev):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
        P = style.PAL
        s = self.width()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        body = QPainterPath()
        body.addRoundedRect(QRectF(0, 0, s, s), self.RADIUS, self.RADIUS)
        if self.live:
            ok = QColor(P["ok"])
            g = QLinearGradient(0, 0, 0, s)
            g.setColorAt(0, ok.lighter(108))
            g.setColorAt(1, ok.darker(112))
            p.fillPath(body, g)
            glyph = _ink_on(P["ok"])
        else:
            # a grey tile like the stat cards' on Home, with a rim so it is a
            # tile and not a patch of the pill it sits on
            p.fillPath(body, QColor(_blend(P["surface2"], P["border2"], 0.5)))
            rim = QPainterPath()
            rim.addRoundedRect(QRectF(0.5, 0.5, s - 1, s - 1),
                               self.RADIUS - 0.5, self.RADIUS - 0.5)
            p.setPen(QPen(QColor(P["border2"]), 1))
            p.setBrush(Qt.NoBrush)
            p.drawPath(rim)
            glyph = P["dim"]
        gs = self.GLYPH
        ic = icons.pixmap("globe", glyph, gs, self.devicePixelRatioF(), width=2.0)
        off = (s - gs) // 2
        p.drawPixmap(QRectF(off, off, gs, gs), ic, QRectF(0, 0, ic.width(), ic.height()))
        p.end()


class _PillDot(QWidget):
    """The online dot on the live tile's corner, ringed in the pill's own
    colour so it reads as cut out of the tile -- the presence badge every chat
    app uses. Still: a dot that pulsed all evening would be the one thing on
    screen that never stopped moving."""

    SIZE = 15
    CORE = 3.5       # centred on a half pixel: a 7 px dot with whole-pixel edges
    RING = 2.0

    def __init__(self, pill):
        super().__init__(pill)
        self.pill = pill
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, _ev):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QColor, QPainter
        P = style.PAL
        c = QPointF(7.5, 7.5)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(P["hover"] if self.pill._hover else P["surface"]))
        p.drawEllipse(c, self.CORE + self.RING, self.CORE + self.RING)
        p.setBrush(QColor(P["ok"]))
        p.drawEllipse(c, self.CORE, self.CORE)
        p.end()


class _PillFacts(widgets.ElidedLabel):
    """The pill's second line: the state tag, then the facts.

    One painter pass, so the 10 px tag and the 11 px facts share one baseline
    exactly -- two labels of two sizes side by side each centre themselves and
    land a pixel apart. `text()` is the facts alone. The " · " between facts is
    a step fainter than the facts, and each one is centred between the INK on
    either side of it: by the advances, "Invite+ · 1h" put it a pixel right of
    centre (the "+" carries a wide right bearing, a tabular "1" a wide left one).
    """

    GAP = 7          # tag to facts
    SPACING = 0.8    # the tag's letter-spacing, px

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.tag = ""
        self.tag_colour = self.fact_colour = self.sep_colour = "#ffffff"

    def _tag_font(self):
        from PySide6.QtGui import QFont, QFontInfo
        f = QFont(self.font())
        px = self.font().pixelSize()
        if px <= 0:
            px = QFontInfo(self.font()).pixelSize()
        f.setWeight(QFont.Bold)
        if style.CLASSIC:
            return f                 # 1995's bold, at the line's own size
        f.setPixelSize(max(9, px - 1))
        f.setLetterSpacing(QFont.AbsoluteSpacing, self.SPACING)
        return f

    def tag_width(self):
        from PySide6.QtGui import QFontMetricsF
        if not self.tag:
            return 0.0
        spacing = 0.0 if style.CLASSIC else self.SPACING
        return (QFontMetricsF(self._tag_font()).horizontalAdvance(self.tag)
                - spacing + self.GAP)

    def full_width(self):
        # Digits measured as zeros: the clock in this line changes every
        # minute, and a width that followed it would re-centre the pill in the
        # title bar each time "1h 09m" became "1h 10m".
        import re
        from PySide6.QtGui import QFontMetricsF
        steady = re.sub(r"\d", "0", self._full)
        return int(self.tag_width() + QFontMetricsF(self.font()).horizontalAdvance(steady)) + 2

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(self.full_width(), super().sizeHint().height())

    def paintEvent(self, _ev):
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QColor, QFontMetricsF, QPainter
        f = self.font()
        fm = QFontMetricsF(f)
        base = round((self.height() - fm.height()) / 2 + fm.ascent())
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        x = 0.0
        if self.tag:
            p.setFont(self._tag_font())
            p.setPen(QColor(self.tag_colour))
            p.drawText(QPointF(x, base), self.tag)
            x += self.tag_width()
        p.setFont(f)
        text = fm.elidedText(self._full, Qt.ElideRight, max(0.0, self.width() - x))
        sep = " · "
        parts = text.split(sep)
        starts = []
        for part in parts:
            starts.append(x)
            x += fm.horizontalAdvance(part) + fm.horizontalAdvance(sep)
        p.setPen(QColor(self.fact_colour))
        for x0, part in zip(starts, parts):
            p.drawText(QPointF(x0, base), part)
        dot = fm.tightBoundingRect("·")
        p.setPen(QColor(self.sep_colour))
        for i in range(1, len(parts)):
            a, b = parts[i - 1], parts[i]
            left = starts[i - 1] + (fm.tightBoundingRect(a).right() if a.strip() else 0)
            right = starts[i] + (fm.tightBoundingRect(b).left() if b.strip() else 0)
            p.drawText(QPointF(round((left + right) / 2 - dot.width() / 2 - dot.left()), base),
                       "·")
        p.end()
