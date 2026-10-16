"""tools/make_demo.py: the pseudonymised copy behind every public screenshot.

Everything here runs on a library made up on the spot, in a temporary folder.
What it proves is what a screenshot must never show: a real display name, a
photographer, a user id, an album's real name -- and a made-up name that is
really somebody's: the word list is ordinary words, and ordinary words are what
people call themselves.
"""
import hashlib
import importlib.util
import json
import os
import re
import sqlite3

import pytest

from vrgallery import paths

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# real names here are words of make_demo's own list, as they can be in a library
PEOPLE = ["Juniper", "Marlow", "Quill", "Puddle", "nova_VR", "PixelFan",
          "thistle.fox", "SelfTester"]
AVATARS = ["Amber Fox", "Juniper's Otter", "Mossy Otter"]
SELF = "SelfTester"


@pytest.fixture(scope="module")
def make_demo():
    spec = importlib.util.spec_from_file_location(
        "make_demo", os.path.join(ROOT, "tools", "make_demo.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _library(folder):
    """A small library with every kind of name in it, at folder."""
    paths.set_appdir(str(folder))
    from vrgallery.db import Database
    db = Database()
    con = db._conn
    for pid in range(1, 25):
        day = f"2025-{pid % 12 + 1:02d}-1{pid % 9}"
        fn = (f"with {PEOPLE[pid % 4]} {pid}.png" if pid % 7 == 0 else
              f"VRChat_{day}_20-00-{pid:02d}.000_3840x2160.png")
        mine = pid % 3 != 0
        con.execute(
            "INSERT INTO photos(id, path, folder, filename, taken_at, day, filesize,"
            " mtime, world_id, world_name, avatar_name, author_name, author_id)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, os.path.join(str(folder), "p", fn), os.path.join(str(folder), "p"),
             fn, f"{day}T20:00:{pid:02d}", day, 1000 + pid, float(pid),
             "wrld_test-lake", "Quiet Lake", AVATARS[pid % 3],
             SELF if mine else PEOPLE[pid % 7],
             "usr_test-self" if mine else f"usr_test-{pid % 7}"))
        for n in PEOPLE[pid % 3: pid % 3 + 3]:
            con.execute("INSERT INTO photo_players VALUES(?,?,?)",
                        (pid, n, "usr_test-" + n.lower()))
        con.execute("INSERT INTO photo_tags(photo_id, name, x, y) VALUES(?,?,.5,.5)",
                    (pid, PEOPLE[pid % 5]))
    sid = con.execute("INSERT INTO sessions(log_file, world_id, world_name, start_at,"
                      " end_at) VALUES('output_log_2025-01-10_20-00-00.txt',"
                      " 'wrld_test-lake', 'Quiet Lake', '2025-01-10T20:00:00',"
                      " '2025-01-10T23:00:00')").lastrowid
    for n in PEOPLE:
        con.execute("INSERT INTO session_players VALUES(?,?,?,?,?)",
                    (sid, n, "usr_test-" + n.lower(), "2025-01-10T20:00:00", None))
        con.execute("INSERT INTO avatar_events(log_file, at, player, avatar)"
                    " VALUES('x.txt', '2025-01-10T20:00:00', ?, ?)",
                    (n, AVATARS[len(n) % 3]))
    # the second one is already called what the first is about to become
    con.execute("INSERT INTO albums(name) VALUES('Trip with Juniper')")
    con.execute("INSERT INTO albums(name) VALUES('Best of')")
    con.commit()
    db.close()
    with open(os.path.join(str(folder), "config.json"), "w", encoding="utf-8") as f:
        json.dump({"self_names": [SELF], "webhook_url": "https://example.invalid/hook",
                   "api_token": "secret-token", "folders": [str(folder)],
                   "not_a_setting": "Juniper's phone number"}, f)
    return os.path.join(str(folder), paths.DB_NAME)


def _snapshot(folder):
    out = {}
    for name in sorted(os.listdir(folder)):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            with open(p, "rb") as f:
                out[name] = hashlib.sha1(f.read()).hexdigest()
        else:
            out[name] = "dir"
    return out


@pytest.fixture(scope="module")
def built(make_demo, tmp_path_factory):
    base = tmp_path_factory.mktemp("demo")
    src, out = base / "library", base / "demo"
    _library(src)
    before = _snapshot(str(src))
    code = make_demo.build(str(src), str(out), scenes=1, log=lambda *a: None)
    return {"code": code, "src": str(src), "out": str(out), "before": before}


def _values(db, table, col):
    con = sqlite3.connect(db)
    try:
        return [r[0] for r in con.execute(f"SELECT {col} FROM {table}")]
    finally:
        con.close()


def test_it_builds_and_the_library_it_copies_is_only_read(built):
    assert built["code"] == 0
    assert _snapshot(built["src"]) == built["before"], \
        "not a byte changed, and no -wal or -shm left beside the real library"


def test_no_real_name_survives_anywhere(built, make_demo):
    db = os.path.join(built["out"], paths.DB_NAME)
    real = {n.lower() for n in PEOPLE + AVATARS}
    seen = []
    for table, col in sorted(make_demo.PEOPLE | make_demo.AVATARS):
        vals = [v for v in _values(db, table, col) if v]
        assert vals, f"{table}.{col} should still have names in it"
        assert not {v.lower() for v in vals} & real, f"{table}.{col} kept a real name"
        seen += vals
    with open(db, "rb") as f:
        data = f.read()
    # in the bytes, so a page the VACUUM should have dropped cannot hide one
    for name in PEOPLE + AVATARS + ["Trip with Juniper", "Juniper"]:
        assert name.encode() not in data, f"{name!r} is still in the file"


def test_a_made_up_name_is_never_a_word_of_a_real_one(built, make_demo):
    """Juniper42 next to a real Juniper reads as Juniper. Not one word of the
    list that is part of a real name may be used."""
    db = os.path.join(built["out"], paths.DB_NAME)
    real_words = set().union(*(make_demo.tokens(n) for n in PEOPLE + AVATARS))
    for table, col in sorted(make_demo.PEOPLE):
        for v in _values(db, table, col):
            word = re.match(r"[A-Za-z]+", v).group(0).lower()
            assert word not in real_words, f"{v!r} is built on a real name"


def test_even_a_library_that_uses_every_word_gets_no_real_name(make_demo):
    """With every word of the list taken there is nothing left to filter, and
    the exact check alone has to keep a made-up name from being a real one."""
    real = set(make_demo.FIRST) | {w + "07" for w in make_demo.FIRST}
    forbidden = {n.lower() for n in real}
    first = make_demo.usable(make_demo.FIRST, forbidden)
    assert first == make_demo.FIRST
    fakes = make_demo.pseudonyms(
        real, lambda n: make_demo.alias(n, first=first), forbidden)
    assert len({v.lower() for v in fakes.values()}) == len(real), "one each"
    assert not {v.lower() for v in fakes.values()} & forbidden


def test_user_ids_are_gone_the_photographers_too(built, make_demo):
    db = os.path.join(built["out"], paths.DB_NAME)
    for table, col in sorted(make_demo.IDS):
        assert set(_values(db, table, col)) == {None}, f"{table}.{col}"
    with open(db, "rb") as f:
        assert b"usr_test" not in f.read()


def test_your_own_photos_still_know_they_are_yours(built):
    """The photographer and the config's self names go through one map, so the
    lightbox still hides "Shot by" on your own shots."""
    with open(os.path.join(built["out"], "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    db = os.path.join(built["out"], paths.DB_NAME)
    authors = _values(db, "photos", "author_name")
    assert len(cfg["self_names"]) == 1 and cfg["self_names"][0] in authors
    assert authors.count(cfg["self_names"][0]) == 16           # 2 of every 3
    assert cfg["webhook_url"] == "" and cfg["api_token"] == ""
    assert "not_a_setting" not in cfg, "only the settings the app reads"
    assert cfg["folders"] == [os.path.join(built["out"], "photos")]


def test_albums_and_hand_named_files_are_renamed(built, make_demo):
    db = os.path.join(built["out"], paths.DB_NAME)
    assert _values(db, "albums", "name") == make_demo.ALBUMS[:2]
    names = _values(db, "photos", "filename")
    assert not [n for n in names if "with" in n], names
    assert "VRChat_7.png" in names
    assert "VRChat_2025-02-11_20-00-01.000_3840x2160.png" in names, \
        "VRChat's own file names say nothing and stay"


def test_every_column_of_the_schema_is_accounted_for(make_demo, tmp_path):
    """A new column must be classified in make_demo before a demo can be built:
    it may well hold a name."""
    paths.set_appdir(str(tmp_path / "fresh"))
    from vrgallery.db import Database
    db = Database()
    try:
        assert make_demo.unclassified(db._conn) == []
    finally:
        db.close()


def test_a_column_it_does_not_know_stops_the_build(make_demo, tmp_path):
    src = _library(tmp_path / "library")
    con = sqlite3.connect(src)
    con.execute("ALTER TABLE photos ADD COLUMN nickname TEXT")
    con.commit()
    con.close()
    out = tmp_path / "demo"
    lines = []
    assert make_demo.build(str(tmp_path / "library"), str(out), scenes=1,
                           log=lambda *a: lines.append(" ".join(map(str, a)))) == 1
    assert "photos.nickname" in " ".join(lines)
    assert not (out / paths.DB_NAME).exists()
