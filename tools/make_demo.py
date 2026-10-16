r"""Build a throwaway, pseudonymised copy of the library for screenshots.

Documentation screenshots of a *social* app would otherwise publish two things
that are not the author's to publish: other people's VRChat display names (and,
on the People page, how often and since when they are seen), and the photos
themselves, which are personal and often have other people in frame.

So this builds a library that is structurally real and personally empty:
  * every display name, photographer and avatar name becomes a stable made-up
    one, and no made-up name is one that somebody in the library really has,
  * user ids are cleared, album names replaced, and secrets are stripped from
    the config,
  * every photo is replaced by a generated scene, with the thumbnail cache
    pre-filled so the app never re-analyses (which would flatten the duplicate
    groups the Cleanup page is meant to demonstrate).

World names, dates, counts and groupings are left alone — those are what the
screenshots are supposed to show. Every column of the schema is listed below
with what happens to it, and a library with a column that is not listed is
refused rather than copied with it.

    python tools\make_demo.py [--source DIR] [--out DIR] [--scenes N] [--keep-photos]
    .venv\Scripts\python.exe run.py --data-dir DIR --no-index --shot x.png --page moments

--no-index matters: an index pass would write the real names straight back in
from VRChat's still-growing log file.

The library it copies (--source, the real one by default) is only ever read.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from vrgallery import paths
from vrgallery.config import DEFAULTS as CONFIG_DEFAULTS

FIRST = ["Nova", "Pixel", "Juniper", "Echo", "Marlow", "Bramble", "Cinder", "Wren",
         "Quill", "Sable", "Tumble", "Vesper", "Onyx", "Pepper", "Rune", "Willow",
         "Fennec", "Halcyon", "Indigo", "Jasper", "Koda", "Lumen", "Mirth", "Nimbus",
         "Opal", "Puddle", "Quartz", "Ripple", "Sorrel", "Thistle", "Umber", "Vale"]
SUFFIX = ["", "", "", "_VR", "42", "_", "07", "x", "99", "_hm", "12"]
# avatar names carry real names just as often as display names do
AV_ADJ = ["Mossy", "Sunlit", "Velvet", "Copper", "Dappled", "Frosted", "Amber",
          "Twilight", "Cobalt", "Hazel", "Sable", "Crimson"]
AV_NOUN = ["Fox", "Otter", "Lynx", "Wolf", "Dragon", "Raccoon", "Hare", "Sparrow",
           "Tiger", "Deer", "Corgi", "Serval"]
# albums are named by hand, so anything at all can be in them
ALBUMS = ["Best of", "Favourites", "Sunsets", "Group photos", "Worlds to revisit",
          "Events"]

# ---------------------------------------------------------------- the schema

# What each column holds, and so what the demo does with it. build() refuses a
# library with a column that is in none of these: a column added later may well
# hold a name, and the safe answer to "what is this?" is not to publish it.
PEOPLE = {("photo_players", "name"), ("session_players", "name"),
          ("photo_tags", "name"), ("avatar_events", "player"),
          ("photos", "author_name")}            # -> made-up display names
AVATARS = {("photos", "avatar_name"), ("avatar_events", "avatar")}   # -> made up
IDS = {("photo_players", "user_id"), ("session_players", "user_id"),
       ("photos", "author_id")}                 # -> NULL
RENAMED = {("albums", "name")}                  # -> ALBUMS
FILES = {("photos", "path"), ("photos", "folder"),
         ("photos", "filename")}                # -> swap_in_scenes()
KEPT = {
    # worlds are public places and are what the screenshots are about; the log
    # columns hold file names like output_log_2026-08-20_21-14-03.txt
    "photos": {"id", "taken_at", "day", "width", "height", "filesize", "mtime",
               "world_id", "world_name", "meta_source", "favorite", "luma", "dhash",
               "scanned", "missing", "session_id", "instance_type", "region",
               "rating", "is_video", "deleted_at"},
    "photo_players": {"photo_id"},
    "photo_tags": {"id", "photo_id", "x", "y", "w", "h", "created_at", "sig"},
    "albums": {"id", "created_at"},
    "album_photos": {"album_id", "photo_id", "added_at"},
    "sessions": {"id", "log_file", "world_id", "world_name", "start_at", "end_at",
                 "instance_type", "region"},
    "session_players": {"session_id", "join_at", "leave_at"},
    "avatar_events": {"id", "log_file", "at"},
    "logs": {"file", "size", "mtime"},
    "meta": {"key", "value"},
}


def columns(con):
    """{(table, column)} of every table in the database."""
    out = set()
    for (table,) in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name NOT LIKE 'sqlite_%'").fetchall():
        for r in con.execute(f'PRAGMA table_info("{table}")'):
            out.add((table, r[1]))
    return out


def unclassified(con):
    """'table.column' for every column this file does not say what to do with."""
    known = PEOPLE | AVATARS | IDS | RENAMED | FILES | {
        (t, c) for t, cols in KEPT.items() for c in cols}
    return sorted(f"{t}.{c}" for t, c in columns(con) - known)


def _distinct(con, have, cols):
    out = set()
    for table, col in sorted(cols & have):
        out |= {r[0] for r in con.execute(
            f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL')}
    return {x for x in out if x}


# ---------------------------------------------------------------- made-up names

def tokens(name):
    """The words a name is made of, lower-cased, and the whole name.

    'Juniper', 'Juniper_VR', 'juniper.fox' and 'JuniperFox' all contain the word
    'juniper': a made-up 'Juniper42' next to any of them on a screenshot reads as
    that person.
    """
    words = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", name)
    return {w.lower() for w in words} | {name.lower()}


def usable(words, forbidden):
    """The words that are no part of any real name. If a library somehow uses
    every one of them, all of them: the exact check in pseudonyms() still holds."""
    keep = [w for w in words if w.lower() not in forbidden]
    return keep or list(words)


def alias(name, seed="vrgallery-demo", first=FIRST):
    """Stable pseudonym: the same input always yields the same fake name."""
    h = hashlib.sha1((seed + "|" + name).encode("utf-8", "replace")).digest()
    return first[h[0] % len(first)] + SUFFIX[h[1] % len(SUFFIX)] + (
        str(h[2] % 90 + 10) if h[3] % 3 == 0 else "")


def avatar_alias(name, adj=AV_ADJ, noun=AV_NOUN):
    h = hashlib.sha1(("avatar|" + name).encode("utf-8", "replace")).digest()
    return f"{adj[h[0] % len(adj)]} {noun[h[1] % len(noun)]}"


def pseudonyms(real, make, forbidden, sep=""):
    """{real: fake}, one fake per real name, and never a real name.

    Unique, because photo_players and photo_tags are UNIQUE(photo_id, name):
    two people collapsing onto one fake name would fail the update. And never
    equal -- in any case -- to a name that is in the library for real: then the
    made-up name IS somebody's name, and the screenshot shows that person, next
    to the photos and the evenings of somebody else.
    """
    mapping, taken = {}, set()
    for n in sorted(real):
        base = make(n)
        fake, i = base, 2
        while fake.lower() in taken or fake.lower() in forbidden:
            fake = f"{base}{sep}{i}"
            i += 1
        taken.add(fake.lower())
        mapping[n] = fake
    return mapping


# ---------------------------------------------------------------- scene art

SKIES = [
    ((28, 34, 72), (232, 138, 122)),      # dusk
    ((12, 16, 38), (46, 84, 146)),        # night
    ((126, 196, 232), (238, 244, 250)),   # clear day
    ((250, 186, 120), (120, 74, 122)),    # sunset
    ((16, 52, 60), (96, 190, 176)),       # teal morning
    ((44, 24, 60), (196, 92, 148)),       # neon
    ((196, 214, 226), (246, 248, 250)),   # overcast
    ((10, 24, 30), (28, 96, 108)),        # deep water
]


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def make_scene(seed, size=(1920, 1080)):
    """A plausible VR-world vista built from nothing but a seed.

    Not anybody's photo: a gradient sky, a light source, layered silhouettes and
    a few motes. Enough variety that a grid of them reads as a photo library.
    """
    import random

    from PIL import Image, ImageDraw, ImageFilter

    rnd = random.Random(seed)
    w, h = size
    top, bottom = SKIES[rnd.randrange(len(SKIES))]
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    horizon = int(h * rnd.uniform(0.55, 0.75))
    for y in range(h):
        t = min(1.0, y / max(1, horizon))
        d.line([(0, y), (w, y)], fill=_lerp(top, bottom, t ** 0.85))

    # a sun or moon, with a soft bloom
    if rnd.random() < 0.8:
        cx = rnd.randint(int(w * 0.1), int(w * 0.9))
        cy = rnd.randint(int(h * 0.12), horizon - 40)
        r = rnd.randint(int(h * 0.03), int(h * 0.09))
        glow = Image.new("RGB", (w, h), (0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse([cx - r * 3, cy - r * 3, cx + r * 3, cy + r * 3],
                   fill=(90, 84, 66))
        img = Image.blend(img, Image.blend(img, glow.filter(
            ImageFilter.GaussianBlur(r * 1.6)), 0.0), 0.0)
        d = ImageDraw.Draw(img)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(252, 248, 232))

    # motes / stars above the horizon
    for _ in range(rnd.randint(40, 160)):
        x = rnd.randint(0, w)
        y = rnd.randint(0, horizon)
        s = rnd.choice([1, 1, 1, 2])
        v = rnd.randint(180, 255)
        d.ellipse([x, y, x + s, y + s], fill=(v, v, min(255, v + 10)))

    # three receding silhouette layers
    layers = rnd.randint(2, 4)
    for layer in range(layers):
        depth = (layer + 1) / layers
        shade = _lerp(bottom, (8, 10, 16), 0.35 + 0.5 * depth)
        base = horizon + int((h - horizon) * (layer / max(1, layers)) * 0.55)
        pts = [(0, h)]
        x = 0
        while x < w:
            step = rnd.randint(int(w * 0.06), int(w * 0.2))
            peak = base - rnd.randint(int(h * 0.02), int(h * 0.22 * (1.2 - depth)))
            pts.append((x, peak))
            x += step
        pts.append((w, base))
        pts.append((w, h))
        d.polygon(pts, fill=shade)

    # a couple of upright structures, like a building or a torii in the distance
    if rnd.random() < 0.55:
        shade = _lerp(bottom, (6, 8, 14), 0.75)
        for _ in range(rnd.randint(1, 4)):
            bw = rnd.randint(int(w * 0.02), int(w * 0.07))
            bx = rnd.randint(0, w - bw)
            bh = rnd.randint(int(h * 0.08), int(h * 0.3))
            by = horizon + rnd.randint(-20, 60)
            d.rectangle([bx, by - bh, bx + bw, by + 10], fill=shade)

    # gentle vignette so the grid does not look like flat wallpaper
    vig = Image.new("L", (w, h), 0)
    ImageDraw.Draw(vig).ellipse([-w * 0.25, -h * 0.35, w * 1.25, h * 1.35], fill=255)
    vig = vig.filter(ImageFilter.GaussianBlur(w * 0.06))
    img = Image.composite(img, Image.new("RGB", (w, h), (6, 8, 12)), vig)
    return img


# VRChat's own file names are a date, a time and a size, and a recording's are
# usually a date and a time: digits and separators, nothing else. Any other
# name was given by hand and can say anything -- "with Juniper.png".
PLAIN_FILE = re.compile(r"^(VRChat_)?[0-9x_.\- ]+\.[A-Za-z0-9]{2,5}$")


def plain_filename(pid, filename):
    """The file name the stand-in gets: the real one only if it says nothing."""
    if filename and PLAIN_FILE.match(filename):
        return filename
    ext = os.path.splitext(filename or "")[1]
    if not re.fullmatch(r"\.[A-Za-z0-9]{2,5}", ext):
        ext = ".png"
    return f"VRChat_{pid}{ext}"


def swap_in_scenes(con, photo_dir, out_dir, count):
    """Repoint every photo at a generated scene and pre-render its thumbnail.

    The thumbnail is written under the exact cache key the app will look for, so
    the app never runs a deep scan on the stand-in — which matters because that
    would overwrite the stored perceptual hashes, and the Cleanup page's
    duplicate groups (a real, interesting property of the library) would
    collapse into one meaningless pile.
    """
    from vrgallery import imaging

    os.makedirs(photo_dir, exist_ok=True)
    thumb_dir = os.path.join(out_dir, "thumbs")
    os.makedirs(thumb_dir, exist_ok=True)

    import io

    # photos.path is UNIQUE, so every row needs its own filename. Hard links let
    # a few dozen generated files back thousands of paths for almost no disk.
    masters = []
    for i in range(count):
        src = os.path.join(photo_dir, f"_scene_{i:03d}.png")
        img = make_scene(i)
        img.save(src, "PNG")
        thumb = img.copy()
        thumb.thumbnail((imaging.THUMB_PX, imaging.THUMB_PX))
        buf = io.BytesIO()
        thumb.save(buf, "JPEG", quality=85)
        st = os.stat(src)
        masters.append({"src": src, "size": st.st_size, "mtime": st.st_mtime,
                        "dims": img.size, "thumb": buf.getvalue()})

    # The recorded filesize/mtime are kept exactly as they were: they drive the
    # size statistics the screenshots are meant to show, and the thumbnail cache
    # key is derived from them, so the stand-in thumbnails must be filed under
    # those values rather than the tiny stand-in file's own.
    rows = con.execute(
        "SELECT id, filename, filesize, mtime FROM photos ORDER BY id").fetchall()
    used = set()
    for pid, filename, filesize, mtime in rows:
        m = masters[pid % len(masters)]
        name = plain_filename(pid, filename)
        stem, ext = os.path.splitext(name)
        while name.lower() in used:
            stem += "_"
            name = stem + ext
        used.add(name.lower())
        dst = os.path.join(photo_dir, name)
        if not os.path.exists(dst):
            try:
                os.link(m["src"], dst)
            except OSError:
                shutil.copy2(m["src"], dst)
        key = imaging.thumb_key(dst, mtime or 0, filesize or 0)
        tp = os.path.join(thumb_dir, key + ".jpg")
        if not os.path.exists(tp):
            with open(tp, "wb") as f:
                f.write(m["thumb"])
        con.execute(
            "UPDATE photos SET path=?, folder=?, filename=?,"
            " width=?, height=?, scanned=1, missing=0 WHERE id=?",
            (dst, photo_dir, name, m["dims"][0], m["dims"][1], pid))
    con.commit()
    return len(masters)


def _copy_library(src_db, dst_db):
    """A copy of the library, made by reading its files and nothing else.

    The database and its WAL are copied as they are, and the COPY is
    checkpointed. Never the original: a checkpoint is a write, and even a
    read-only SQLite connection leaves -wal and -shm files behind next to a WAL
    database. A copy torn by the app writing at that very moment fails the
    integrity check instead of turning up later as an odd library.
    """
    for suffix in ("", "-wal"):
        if os.path.exists(src_db + suffix):
            shutil.copyfile(src_db + suffix, dst_db + suffix)
    con = sqlite3.connect(dst_db)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    if ok != "ok":
        con.close()
        raise sqlite3.DatabaseError(f"the copy is damaged ({ok})")
    return con


def _replace(con, table, col, mapping):
    """One UPDATE per column through a temporary map, not one per name."""
    con.execute("DROP TABLE IF EXISTS temp._demo_map")
    con.execute("CREATE TEMP TABLE _demo_map(was TEXT PRIMARY KEY, now TEXT)")
    con.executemany("INSERT INTO temp._demo_map VALUES(?,?)", mapping.items())
    con.execute(
        f'UPDATE "{table}" SET "{col}"=(SELECT now FROM temp._demo_map'
        f' WHERE was="{table}"."{col}")'
        f' WHERE "{col}" IN (SELECT was FROM temp._demo_map)')
    con.execute("DROP TABLE temp._demo_map")


def anonymise(con, self_names=()):
    """Pseudonymise a copied library in place. -> (people map, avatar map, ids)

    self_names (the config's own names) are real names too, and go through the
    same map as the photographer column, so "Shot by" still recognises your
    own photos and stays hidden on them.
    """
    have = columns(con)
    people = _distinct(con, have, PEOPLE) | {n for n in self_names if n}
    avatars = _distinct(con, have, AVATARS)
    ids = _distinct(con, have, IDS)
    # No made-up name may BE a real one, of a person or of an avatar, in any
    # case; and no word of a made-up display name may be a word of a real one.
    # The word lists hold ordinary words, and real players use them too.
    real = {n.lower() for n in people | avatars}
    person_words = set().union(*(tokens(n) for n in people)) if people else set()
    avatar_words = set().union(*(tokens(n) for n in avatars)) if avatars else set()
    first = usable(FIRST, person_words | avatar_words)
    adj, noun = usable(AV_ADJ, person_words), usable(AV_NOUN, person_words)
    mapping = pseudonyms(people, lambda n: alias(n, first=first), real)
    av_map = pseudonyms(avatars, lambda n: avatar_alias(n, adj, noun), real, sep=" ")
    for table, col in sorted(PEOPLE & have):
        _replace(con, table, col, mapping)
    for table, col in sorted(AVATARS & have):
        _replace(con, table, col, av_map)
    # user ids identify people just as well as names do: the photographer's
    # among them, which on most photos is the library's owner
    for table, col in sorted(IDS & have):
        con.execute(f'UPDATE "{table}" SET "{col}"=NULL')
    if ("albums", "name") in have:
        ids_ = [r[0] for r in con.execute("SELECT id FROM albums ORDER BY id")]
        # two passes: the name is UNIQUE, and a real album may already be
        # called what another one is about to become
        con.execute("UPDATE albums SET name='_demo_' || id")
        for i, aid in enumerate(ids_):
            con.execute("UPDATE albums SET name=? WHERE id=?",
                        (ALBUMS[i] if i < len(ALBUMS) else f"Album {i + 1}", aid))
    con.commit()
    return mapping, av_map, ids


def verify(db_path, mapping, av_map, ids, albums):
    """Problems with a finished demo database, read back from the file itself."""
    problems = []
    real = {n.lower() for n in list(mapping) + list(av_map)}
    con = sqlite3.connect(db_path)
    try:
        have = columns(con)
        for table, col in sorted((PEOPLE | AVATARS) & have):
            for (v,) in con.execute(f'SELECT DISTINCT "{col}" FROM "{table}"'):
                if v and v.lower() in real:
                    problems.append(f"{table}.{col} still holds a real name")
                    break
        for table, col in sorted(IDS & have):
            n = con.execute(f'SELECT COUNT(*) FROM "{table}"'
                            f' WHERE "{col}" IS NOT NULL').fetchone()[0]
            if n:
                problems.append(f"{table}.{col}: {n} ids left")
        if ("albums", "name") in have:
            left = {r[0] for r in con.execute("SELECT name FROM albums")} & set(albums)
            if left - set(ALBUMS):
                problems.append("an album kept its real name")
    finally:
        con.close()
    # Free pages keep what an UPDATE replaced until a VACUUM: look at the bytes.
    # Ids only -- a short real name can turn up inside a world's name honestly.
    with open(db_path, "rb") as f:
        data = f.read()
    if any(len(i) >= 6 and i.encode("utf-8") in data for i in ids):
        problems.append("a real user id is still in the file")
    return problems


def build(source, out, scenes=64, keep_photos=False, log=print):
    """Build the demo library at out from the one at source. -> exit code."""
    src_db = os.path.join(source, paths.DB_NAME)
    if not os.path.exists(src_db):
        log("no library at", src_db)
        return 1
    out = os.path.abspath(out)
    src_n, out_n = os.path.normcase(os.path.abspath(source)), os.path.normcase(out)
    if out_n == src_n or out_n.startswith(src_n.rstrip("\\/") + os.sep):
        log("refusing to build", out, "- it is the library itself, or inside it")
        return 1
    if os.path.isdir(out):
        # only ever remove a folder we made ourselves
        if not os.path.exists(os.path.join(out, ".vrgallery-demo")):
            log("refusing to touch", out, "- not a demo folder")
            return 1
        thumbs = os.path.join(out, "thumbs")
        if os.path.isdir(thumbs):
            subprocess.run(["cmd", "/c", "rmdir", thumbs], capture_output=True)
        shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out, exist_ok=True)
    open(os.path.join(out, ".vrgallery-demo"), "w").close()

    dst_db = os.path.join(out, paths.DB_NAME)
    try:
        con = _copy_library(src_db, dst_db)
    except sqlite3.DatabaseError as e:
        log("could not copy the library:", e, "- close VR Gallery and try again")
        return 1
    unknown = unclassified(con)
    if unknown:
        con.close()
        os.remove(dst_db)
        log("refusing: make_demo does not know what these columns hold:",
            ", ".join(unknown))
        log("say so in PEOPLE / AVATARS / IDS / RENAMED / KEPT in tools/make_demo.py")
        return 1

    src_cfg = {}
    try:
        with open(os.path.join(source, "config.json"), "r", encoding="utf-8") as f:
            src_cfg = json.load(f)
    except (OSError, ValueError):
        pass
    if not isinstance(src_cfg, dict):
        src_cfg = {}
    albums = [r[0] for r in con.execute("SELECT name FROM albums")] if (
        ("albums", "name") in columns(con)) else []
    mapping, av_map, ids = anonymise(con, src_cfg.get("self_names") or [])

    if keep_photos:
        # share the real thumbnail cache instead of duplicating gigabytes
        link = subprocess.run(["cmd", "/c", "mklink", "/J",
                               os.path.join(out, "thumbs"),
                               os.path.join(source, "thumbs")],
                              capture_output=True, text=True)
        if link.returncode != 0:
            os.makedirs(os.path.join(out, "thumbs"), exist_ok=True)
    else:
        os.makedirs(os.path.join(out, "thumbs"), exist_ok=True)

    photo_dir = os.path.join(out, "photos")
    if not keep_photos:
        n_scenes = swap_in_scenes(con, photo_dir, out, scenes)
        log(f"{n_scenes} generated scenes stand in for every photo")
    # an UPDATE leaves the old value in a free page until the file is rebuilt
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.execute("VACUUM")
    con.close()

    # config: only what the app reads, pseudonymised self names, no secrets
    cfg = {k: src_cfg[k] for k in CONFIG_DEFAULTS if k in src_cfg}
    cfg["self_names"] = [mapping[n] for n in src_cfg.get("self_names") or [] if n]
    for secret in ("webhook_url", "api_token", "frame_dir", "frame_publish_cmd",
                   "backup_dir", "adb_path"):
        cfg[secret] = ""
    if not keep_photos:
        cfg["folders"] = [photo_dir]    # the real library must stay out of sight
    cfg["api_enabled"] = False          # never open a port from the demo copy
    cfg["close_to_tray"] = False
    cfg["start_minimized"] = False
    cfg["window"] = [80, 60, 1500, 940, False]
    with open(os.path.join(out, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    problems = verify(dst_db, mapping, av_map, ids, albums)
    if problems:
        for p in problems:
            log("NOT SAFE TO PUBLISH:", p)
        return 2
    log(f"demo library at {out}")
    log(f"{len(mapping)} display names and {len(av_map)} avatar names "
        f"pseudonymised, none of them a real one; {len(ids)} user ids and "
        f"{len(albums)} album names gone")
    log("self names ->", cfg["self_names"])
    log(f'open it with: run.py --data-dir "{out}" --no-index')
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=paths.APPDIR,
                    help="the library to copy (only ever read); the real one by default")
    ap.add_argument("--out", default=os.path.join(os.environ.get("TEMP", "."),
                                                  "vrgallery-demo"))
    ap.add_argument("--scenes", type=int, default=64,
                    help="how many generated scenes to spread over the library")
    ap.add_argument("--keep-photos", action="store_true",
                    help="show the real photos (never do this for anything public)")
    a = ap.parse_args()
    return build(os.path.abspath(a.source), a.out, a.scenes, a.keep_photos)


if __name__ == "__main__":
    sys.exit(main())
