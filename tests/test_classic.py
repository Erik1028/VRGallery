"""The Windows 95 look (Settings > Appearance > Look; see vrgallery/classic.py).

It is applied once at start-up and it changes process-wide things -- the Qt
style, the palette, the font, and QPainterPath.addRoundedRect /
QPainter.drawRoundedRect / QWidget.setStyleSheet, which it squares off. So the
window is built in a CHILD process here: applied in this one, the square
corners would leak into every test that runs after it.

The pure parts (captions, stylesheet folding, the pixel icons) are tested
in-process: importing classic.py changes nothing until apply() is called.
"""
import json
import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("PySide6")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------------------- the pure parts

@pytest.mark.parametrize("text, want", [
    ("ON THIS DAY", "On this day"),
    ("WHERE YOU'VE BEEN LATELY", "Where you've been lately"),
    ("LAST IN VRCHAT", "Last in VRChat"),
    ("LOCAL API", "Local API"),
    ("TIME OF DAY — when the camera comes out", "Time of day — when the camera comes out"),
    ("SEPTEMBER 18", "September 18"),
    ("Already in sentence case", "Already in sentence case"),
    ("1,860", "1,860"),
    ("", ""),
])
def test_captions_are_in_sentence_case(text, want):
    from vrgallery import classic
    assert classic.sentence(text) == want


def test_a_modern_stylesheet_is_folded_into_1995():
    from vrgallery import classic
    css = ("QFrame#X { background:#111; border-radius: 10px; border-top-left-radius:4px;"
           " font-size: 13px; letter-spacing: 1.2px; } QLabel { font-size:21px; }")
    out = classic.classic_css(css)
    assert "radius" not in out
    assert "letter-spacing" not in out
    assert "font-size: 11px" in out, "body text is not 8 pt"
    assert "font-size: %dpx" % classic.HEADING_PX in out, "a heading is not the heading size"
    assert "background:#111" in out, "folding took more than it should"


def test_every_pixel_icon_is_16_by_16_in_vga_colours():
    from vrgallery import classic
    for name, rows in classic.ICONS.items():
        assert len(rows) == 16, name
        for r in rows:
            assert len(r) == 16, (name, r)
            assert set(r) <= set(classic.VGA) | {"."}, (name, set(r) - set(classic.VGA))


def test_every_page_in_the_tree_has_a_picture():
    from vrgallery import classic
    from vrgallery.mainwindow import NAV
    keys = {e[0] for e in NAV if e is not None} | {"settings"}
    assert keys <= set(classic.NAV_ICONS), keys - set(classic.NAV_ICONS)
    assert set(classic.NAV_ICONS.values()) <= set(classic.ICONS)
    tree_keys = {"home", "settings"} | {k for _g, ks in classic.NavTree.GROUPS for k in ks}
    assert keys == tree_keys, "a page is missing from the tree, or the tree has one too many"


# ------------------------------------------------------ the window, in a child

CHILD = textwrap.dedent(r'''
    import json, os, sys
    sys.path.insert(0, ROOT)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from vrgallery import paths
    paths.set_appdir(LIB)
    paths.ensure_dirs()
    from PySide6.QtCore import QRectF
    from PySide6.QtGui import QPainterPath
    from PySide6.QtWidgets import QApplication, QLabel
    app = QApplication([])
    from vrgallery import classic, style
    from vrgallery.config import Config
    from vrgallery.db import Database
    cfg = Config()
    cfg.set("onboarded", True, save=False)
    cfg.set("check_updates", False, save=False)
    cfg.set("api_enabled", False, save=False)
    cfg.set("skin", "win95", save=False)
    # exactly what app.py does with a saved "win95"
    style.set_classic(True)
    classic.apply(app)
    # read before the stylesheet goes on, which wraps the style in a proxy
    # that reports no name of its own
    style_name = app.style().name()
    style.apply_palette("ember")
    app.setStyleSheet(style.build_qss("orchid"))
    from vrgallery.mainwindow import MainWindow
    win = MainWindow(app, cfg, Database(), auto_index=False)
    win.resize(1200, 800)
    win.show()
    for _ in range(30):
        app.processEvents()
    out = {}
    out["style"] = style_name
    out["bg"] = style.PAL["bg"]
    out["accent"] = style.accent("orchid")["a"]
    out["caption_h"] = win.titlebar.height()
    out["caption_buttons"] = [type(b).__name__ for b in
                              (win.titlebar.btn_min, win.titlebar.btn_max, win.titlebar.btn_close)]
    out["pill_in_status_bar"] = win.live_pill.parentWidget() is win.statusbar
    out["status_text"] = win.lab_status.text()
    t = win.nav_tree
    t.setCurrentItem(t._items["worlds"])
    app.processEvents()
    out["tree_opens_worlds"] = win.stack.currentWidget() is win.page_worlds
    win.activate("home")
    out["activate_selects_home"] = t.currentItem() is t._items["home"]
    p = QPainterPath()
    p.addRoundedRect(QRectF(0, 0, 40, 40), 10, 10)
    out["rounded_is_a_rect"] = p.elementCount() == 5
    lab = QLabel("x")
    lab.setStyleSheet("border-radius: 8px; font-size: 13px;")
    out["inline_css"] = lab.styleSheet()
    cap = QLabel("WHERE YOU MEET")
    cap.setObjectName("SectionLabel")
    cap.show()
    app.processEvents()
    out["caption"] = cap.text()
    # the review (2026-09-30): after a drill-down the highlighted page was dead
    from PySide6.QtCore import QPoint, Qt as _Qt
    from PySide6.QtTest import QTest
    def click(key_or_item):
        it = t._items[key_or_item] if isinstance(key_or_item, str) else key_or_item
        r = t.visualItemRect(it)
        QTest.mouseClick(t.viewport(), _Qt.LeftButton, _Qt.NoModifier,
                         QPoint(r.x() + 30, r.center().y()))
        app.processEvents()
    click("worlds")
    out["click_opens_worlds"] = win.stack.currentWidget() is win.page_worlds
    win.push_world("wrld_x", "Some world")
    app.processEvents()
    out["drill_clears_tree"] = t.currentItem() is None
    click("worlds")
    out["click_after_drill_goes_back"] = win.stack.currentWidget() is win.page_worlds
    win.push_world("wrld_x", "Some world")
    app.processEvents()
    t.select("worlds")              # as if the tree still showed it
    click("worlds")
    out["click_on_current_navigates"] = win.stack.currentWidget() is win.page_worlds
    folder = t.topLevelItem(1)       # Library
    click(folder)
    out["folder_click_keeps_page"] = (t.currentItem() is t._items["worlds"]
                                      and t._items["worlds"].isSelected())
    out["saved_accent"] = style.saved_accent("orchid")["a"]
    out["qwidget_rule"] = [l for l in classic.qss().splitlines() if l.startswith("QWidget {")][0]
    from vrgallery import widgets as _w
    b = _w.ghost_btn("Go", "check", primary=True)
    img = b.icon().pixmap(16, 16).toImage()
    out["primary_icon_dark"] = max(img.pixelColor(x, y).lightness()
                                   for x in range(img.width()) for y in range(img.height())
                                   if img.pixelColor(x, y).alpha() > 200) < 100
    win.titlebar.toggle_max()
    app.processEvents()
    out["max_glyph"] = win.titlebar.btn_max.glyph
    win._quitting = True
    win.close()
    print("RESULT " + json.dumps(out))
''')


@pytest.fixture(scope="module")
def classic_window(tmp_path_factory):
    lib = str(tmp_path_factory.mktemp("classiclib"))
    code = "ROOT = %r\nLIB = %r\n" % (ROOT, lib) + CHILD
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       env=env, timeout=120, encoding="utf-8")
    line = [l for l in r.stdout.splitlines() if l.startswith("RESULT ")]
    assert line, "the Windows 95 window did not build:\n" + r.stdout + r.stderr
    return json.loads(line[-1][len("RESULT "):])


def test_the_controls_are_drawn_by_the_windows_style(classic_window):
    assert classic_window["style"].lower() == "windows"


def test_1995_has_one_palette_whatever_theme_and_accent_are_saved(classic_window):
    assert classic_window["bg"] == "#c0c0c0"
    assert classic_window["accent"] == "#000080"


def test_the_caption_is_1995s(classic_window):
    assert classic_window["caption_h"] == 18
    assert classic_window["caption_buttons"] == ["CaptionButton"] * 3


def test_maximise_turns_into_restore(classic_window):
    assert classic_window["max_glyph"] == "restore"


def test_where_you_are_is_on_the_status_bar(classic_window):
    assert classic_window["pill_in_status_bar"]
    assert "photos" in classic_window["status_text"], "a blank status bar"


def test_the_tree_is_the_navigation(classic_window):
    assert classic_window["tree_opens_worlds"], "picking Worlds in the tree did not open it"
    assert classic_window["activate_selects_home"], "the tree does not follow the page"


def test_corners_are_square(classic_window):
    assert classic_window["rounded_is_a_rect"]
    assert "radius" not in classic_window["inline_css"]
    assert "11px" in classic_window["inline_css"]


def test_the_highlighted_page_is_always_a_way_back(classic_window):
    """After a drill-down into a world the tree showed Worlds and clicking it
    did nothing; Back was the only way out (review, 2026-09-30)."""
    w = classic_window
    assert w["click_opens_worlds"]
    assert w["drill_clears_tree"], "a drill-down left a page highlighted"
    assert w["click_after_drill_goes_back"]
    assert w["click_on_current_navigates"], "a click on the highlighted page did nothing"


def test_a_folder_click_leaves_the_open_page_highlighted(classic_window):
    assert classic_window["folder_click_keeps_page"]


def test_menus_and_disabled_text_take_their_colours_from_the_palette(classic_window):
    """A stylesheet colour on QWidget overrode the palette in every state: the
    hovered menu item was black on navy, disabled text stayed black."""
    assert "color" not in classic_window["qwidget_rule"]


def test_exports_keep_the_chosen_accent(classic_window):
    """Posters and contact sheets keep their dark ground in 1995 too; navy on
    it was 1.2:1."""
    assert classic_window["saved_accent"] == "#c064ff"


def test_a_primary_buttons_icon_is_dark_on_the_grey_face(classic_window):
    assert classic_window["primary_icon_dark"]


def test_captions_shown_once_are_not_shouted(classic_window):
    assert classic_window["caption"] == "Where you meet"


# ------------------------------------------------- the switch, in Settings

@pytest.fixture()
def modern(tmp_path):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from vrgallery import paths
    paths.set_appdir(str(tmp_path / "lib"))
    paths.ensure_dirs()
    from vrgallery.config import Config
    from vrgallery.db import Database
    from vrgallery.mainwindow import MainWindow
    cfg = Config()
    cfg.set("onboarded", True, save=False)
    cfg.set("check_updates", False, save=False)
    cfg.set("api_enabled", False, save=False)
    win = MainWindow(app, cfg, Database(), auto_index=False)
    yield win
    win._quitting = True
    win.close()


def test_choosing_windows_95_saves_it_and_offers_a_restart(modern, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from vrgallery import pages
    asked, restarted = [], []
    monkeypatch.setattr(pages.QMessageBox, "question",
                        lambda *a, **k: (asked.append(a[2]), QMessageBox.No)[1])
    monkeypatch.setattr(modern, "restart_app", lambda: restarted.append(1))
    s = modern.page_settings
    s._set_skin("win95")
    assert modern.cfg.get("skin") == "win95"
    assert asked and "restart" in asked[0].lower()
    assert not restarted, "restarted although the answer was No"
    assert [b.isChecked() for _k, b in s._skins] == [False, True]
    monkeypatch.setattr(pages.QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    s._set_skin("win95")             # asked again, and this time Yes
    assert restarted == [1]


def test_picking_the_look_already_on_does_not_ask(modern, monkeypatch):
    from vrgallery import pages
    monkeypatch.setattr(pages.QMessageBox, "question",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked")))
    modern.page_settings._set_skin("modern")


def test_after_no_the_same_click_offers_the_restart_again(modern, monkeypatch):
    """The prompt is asked against the look that is RUNNING: after "No" the
    saved choice is already Windows 95, and that used to make the click do
    nothing, with no other way to restart."""
    from PySide6.QtWidgets import QMessageBox
    from vrgallery import pages
    asked = []
    monkeypatch.setattr(pages.QMessageBox, "question",
                        lambda *a, **k: (asked.append(1), QMessageBox.No)[1])
    s = modern.page_settings
    s._set_skin("win95")
    s._set_skin("win95")
    assert asked == [1, 1]
    s._set_skin("modern")            # the look on screen: nothing to restart
    assert asked == [1, 1]
    assert modern.cfg.get("skin") == "modern"


def test_a_dev_restart_runs_run_py(modern, monkeypatch):
    """Not sys.argv[0]: under `python -m vrgallery` that is __main__.py, which
    fails on its relative import when run as a script."""
    from PySide6.QtCore import QProcess
    started = []
    monkeypatch.setattr(QProcess, "startDetached",
                        lambda prog, args, cwd=None: (started.append((prog, list(args))), (True, 1))[1])
    monkeypatch.setattr(modern, "quit_app", lambda: None)
    monkeypatch.setattr("sys.argv", [os.path.join(ROOT, "vrgallery", "__main__.py")])
    modern.restart_app()
    prog, args = started[0]
    assert args[0] == os.path.join(ROOT, "run.py")
    assert args[-1] == "--restarted"


def test_a_restart_starts_a_copy_that_waits_for_the_lock(modern, monkeypatch):
    from PySide6.QtCore import QProcess
    started, quit_ = [], []
    monkeypatch.setattr(QProcess, "startDetached",
                        lambda prog, args, cwd=None: (started.append(list(args)), (True, 1))[1])
    monkeypatch.setattr(modern, "quit_app", lambda: quit_.append(1))
    modern.restart_app()
    assert started and started[0][-1] == "--restarted"
    assert quit_ == [1]


def test_a_failed_restart_keeps_this_copy_open(modern, monkeypatch):
    from PySide6.QtCore import QProcess
    quit_ = []
    monkeypatch.setattr(QProcess, "startDetached", lambda *a, **k: (False, 0))
    monkeypatch.setattr(modern, "quit_app", lambda: quit_.append(1))
    modern.restart_app()
    assert not quit_, "closed with nothing started to replace it"


@pytest.mark.parametrize("argv, want", [
    ([], ["--restarted"]),
    (["--data-dir", r"D:\lib", "--no-index"], ["--data-dir", r"D:\lib", "--no-index", "--restarted"]),
    (["--data-dir=D:\\lib"], ["--data-dir=D:\\lib", "--restarted"]),
    (["--tray", "--shot", "x.png", "--restarted"], ["--restarted"]),
])
def test_a_restarted_copy_comes_back_on_the_same_library(argv, want):
    """Not on the default one, and not hidden in the tray."""
    from vrgallery.mainwindow import restart_args
    assert restart_args(argv) == want
