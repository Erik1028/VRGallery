"""SQLite store: photos, per-photo people, albums, parsed log sessions.

One shared connection guarded by an RLock; safe to call from worker threads.
"""
import os
import sqlite3
import threading
from dataclasses import dataclass, field

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS photos(
  id INTEGER PRIMARY KEY,
  path TEXT UNIQUE NOT NULL,
  folder TEXT,
  filename TEXT,
  taken_at TEXT,
  day TEXT,
  width INTEGER DEFAULT 0,
  height INTEGER DEFAULT 0,
  filesize INTEGER DEFAULT 0,
  mtime REAL DEFAULT 0,
  world_id TEXT,
  world_name TEXT,
  meta_source TEXT DEFAULT 'none',
  favorite INTEGER DEFAULT 0,
  luma REAL,
  dhash TEXT,
  scanned INTEGER DEFAULT 0,
  missing INTEGER DEFAULT 0,
  avatar_name TEXT,
  session_id INTEGER,
  instance_type TEXT,
  region TEXT,
  rating INTEGER DEFAULT 0,
  is_video INTEGER DEFAULT 0,
  deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_photos_taken ON photos(taken_at);
CREATE INDEX IF NOT EXISTS idx_photos_day ON photos(day);
CREATE INDEX IF NOT EXISTS idx_photos_world ON photos(world_id);

CREATE TABLE IF NOT EXISTS photo_players(
  photo_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  user_id TEXT,
  PRIMARY KEY(photo_id, name)
);
CREATE INDEX IF NOT EXISTS idx_pp_name ON photo_players(name);

-- where in the frame somebody is: x/y are fractions of the image, so they
-- survive resizing, cropping-free re-encoding and any display size
-- x/y is the top-left of the box and w/h its size, all as fractions of the
-- image, so a tag keeps its place at any zoom, window size or re-encode
CREATE TABLE IF NOT EXISTS photo_tags(
  id INTEGER PRIMARY KEY,
  photo_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  x REAL NOT NULL,
  y REAL NOT NULL,
  w REAL DEFAULT 0,
  h REAL DEFAULT 0,
  created_at TEXT,
  -- the colour fingerprint of the box, so the next one like it can be named
  -- without asking. See facesig. Zero length means "tried and could not".
  sig BLOB
);
CREATE INDEX IF NOT EXISTS idx_tags_photo ON photo_tags(photo_id);
CREATE INDEX IF NOT EXISTS idx_tags_name ON photo_tags(name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_uniq ON photo_tags(photo_id, name);

CREATE TABLE IF NOT EXISTS albums(
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  created_at TEXT
);
CREATE TABLE IF NOT EXISTS album_photos(
  album_id INTEGER NOT NULL,
  photo_id INTEGER NOT NULL,
  added_at TEXT,
  PRIMARY KEY(album_id, photo_id)
);

CREATE TABLE IF NOT EXISTS sessions(
  id INTEGER PRIMARY KEY,
  log_file TEXT,
  world_id TEXT,
  world_name TEXT,
  start_at TEXT,
  end_at TEXT,
  instance_type TEXT,
  region TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_at);
CREATE TABLE IF NOT EXISTS session_players(
  session_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  user_id TEXT,
  join_at TEXT,
  leave_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sp_session ON session_players(session_id);

CREATE TABLE IF NOT EXISTS avatar_events(
  id INTEGER PRIMARY KEY,
  log_file TEXT,
  at TEXT NOT NULL,
  player TEXT NOT NULL,
  avatar TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_av_at ON avatar_events(at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_av_uniq ON avatar_events(at, player, avatar);

CREATE TABLE IF NOT EXISTS logs(
  file TEXT PRIMARY KEY,
  size INTEGER,
  mtime REAL
);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""


@dataclass
class PhotoFilter:
    text: str = ""
    world_id: str = ""
    person: str = ""
    favorites: bool = False
    album_id: int = 0
    day: str = ""            # exact YYYY-MM-DD
    avatar: str = ""
    session_id: int = 0
    date_from: str = ""      # inclusive YYYY-MM-DD
    date_to: str = ""        # inclusive YYYY-MM-DD
    instance_type: str = ""
    min_rating: int = 0
    media: str = ""          # '', 'photo' or 'video'
    sort_desc: bool = True

    def is_plain(self):
        return not (self.text or self.world_id or self.person or self.favorites
                    or self.album_id or self.day or self.avatar or self.session_id
                    or self.date_from or self.date_to or self.instance_type
                    or self.min_rating or self.media)


class Database:
    def __init__(self, path=None):
        paths.ensure_dirs()
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path or paths.DB_PATH, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript("PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;")
            self._conn.executescript(SCHEMA)
            self._migrate()
            self._conn.commit()

    def _migrate(self):
        """Add columns introduced after a library was first created."""
        have = {r["name"] for r in self._conn.execute("PRAGMA table_info(photos)")}
        for col, decl in (("avatar_name", "TEXT"), ("session_id", "INTEGER"),
                          ("instance_type", "TEXT"), ("region", "TEXT"),
                          ("rating", "INTEGER DEFAULT 0"),
                          ("is_video", "INTEGER DEFAULT 0"),
                          ("deleted_at", "TEXT"),
                          ("author_name", "TEXT"), ("author_id", "TEXT")):
            if col not in have:
                self._conn.execute(f"ALTER TABLE photos ADD COLUMN {col} {decl}")
        have_t = {r["name"] for r in self._conn.execute("PRAGMA table_info(photo_tags)")}
        if have_t:                       # tags started life as a bare point
            for col, decl in (("w", "REAL DEFAULT 0"), ("h", "REAL DEFAULT 0"),
                              ("sig", "BLOB")):
                if col not in have_t:
                    self._conn.execute(
                        f"ALTER TABLE photo_tags ADD COLUMN {col} {decl}")
        have_s = {r["name"] for r in self._conn.execute("PRAGMA table_info(sessions)")}
        for col, decl in (("instance_type", "TEXT"), ("region", "TEXT")):
            if col not in have_s:
                self._conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} {decl}")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_photos_avatar ON photos(avatar_name)")
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_photos_session ON photos(session_id)")

    closed = False        # see close(): slots check this before querying

    def close(self):
        with self._lock:
            self.closed = True
            try:
                self._conn.commit()
                self._conn.close()
            except Exception:
                pass

    # ---------- photos: indexing ----------

    def known_files(self):
        """path -> (id, filesize, mtime, scanned)"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, path, filesize, mtime, scanned FROM photos").fetchall()
        return {r["path"]: (r["id"], r["filesize"], r["mtime"], r["scanned"]) for r in rows}

    def upsert_photos(self, items):
        """items: list of dicts(path, folder, filename, taken_at, day, filesize, mtime)."""
        if not items:
            return
        # tolerate callers that predate a column rather than failing on a
        # missing named binding
        items = [{"is_video": 0, **it} for it in items]
        with self._lock:
            self._conn.executemany(
                """INSERT INTO photos(path, folder, filename, taken_at, day, filesize,
                                      mtime, is_video)
                   VALUES(:path, :folder, :filename, :taken_at, :day, :filesize,
                          :mtime, :is_video)
                   ON CONFLICT(path) DO UPDATE SET
                     filesize=excluded.filesize, mtime=excluded.mtime,
                     taken_at=excluded.taken_at, day=excluded.day,
                     is_video=excluded.is_video, missing=0,
                     deleted_at=NULL""",
                items)
            self._conn.commit()

    def set_missing(self, present_paths, folder_roots):
        """Photos under any of folder_roots not present anymore -> missing=1."""
        with self._lock:
            rows = self._conn.execute("SELECT id, path, missing FROM photos").fetchall()
            gone, back = [], []
            for r in rows:
                p = r["path"]
                under = any(p.lower().startswith(root.lower().rstrip("\\") + os.sep)
                            for root in folder_roots)
                if not under:
                    continue
                if p in present_paths:
                    if r["missing"]:
                        back.append((r["id"],))
                else:
                    if not r["missing"]:
                        gone.append((r["id"],))
            if gone:
                self._conn.executemany("UPDATE photos SET missing=1 WHERE id=?", gone)
            if back:
                self._conn.executemany("UPDATE photos SET missing=0 WHERE id=?", back)
            self._conn.commit()
        return len(gone)

    def set_deep(self, pid, width, height, luma, dhash):
        with self._lock:
            self._conn.execute(
                "UPDATE photos SET width=?, height=?, luma=?, dhash=?, scanned=1 WHERE id=?",
                (width, height, luma, dhash, pid))
            self._conn.commit()

    def set_meta_photo(self, pid, meta):
        """What the photo file itself says, from imaging.parse_photo_meta.

        The instance type and region are only written when the metadata
        actually carried them: log correlation may already have filled them in,
        and a photo without an instanceId must not blank that out.
        """
        with self._lock:
            self._conn.execute(
                "UPDATE photos SET world_id=?, world_name=?, meta_source=?,"
                " author_name=?, author_id=? WHERE id=?",
                (meta.get("world_id"), meta.get("world_name"),
                 meta.get("source") or "vrcx",
                 meta.get("author_name"), meta.get("author_id"), pid))
            if meta.get("instance_type"):
                self._conn.execute(
                    "UPDATE photos SET instance_type=?, region=? WHERE id=?",
                    (meta["instance_type"], meta.get("region") or "", pid))
            self._conn.execute("DELETE FROM photo_players WHERE photo_id=?", (pid,))
            self._conn.executemany(
                "INSERT OR IGNORE INTO photo_players(photo_id, name, user_id) VALUES(?,?,?)",
                [(pid, n, u) for n, u in meta.get("players") or []])
            self._conn.commit()

    def set_meta_vrcx(self, pid, world_id, world_name, players):
        """The older three-argument form, for anything still calling it."""
        self.set_meta_photo(pid, {"world_id": world_id, "world_name": world_name,
                                  "players": players, "source": "vrcx"})

    def apply_log_matches(self, matches, keep_avatars=False):
        """matches: list of dicts with keys
             id, session_id, avatar, world_id, world_name, source, players[(name,uid)]

        session_id and avatar always come from the logs (VRCX metadata carries
        neither), while world/people from VRCX metadata — embedded in the file
        itself — always beat log correlation.
        """
        if not matches:
            return
        with self._lock:
            if keep_avatars:
                self._conn.executemany(
                    "UPDATE photos SET session_id=?, instance_type=?, region=? "
                    "WHERE id=?",
                    [(m["session_id"], m["instance_type"], m["region"], m["id"])
                     for m in matches])
            else:
                self._conn.executemany(
                    "UPDATE photos SET session_id=?, avatar_name=?, instance_type=?,"
                    " region=? WHERE id=?",
                    [(m["session_id"], m["avatar"], m["instance_type"], m["region"],
                      m["id"]) for m in matches])
            log_side = [m for m in matches if m["source"] != "vrcx"]
            if log_side:
                self._conn.executemany(
                    "UPDATE photos SET world_id=?, world_name=?, meta_source=? "
                    "WHERE id=? AND meta_source != 'vrcx'",
                    [(m["world_id"], m["world_name"], m["source"], m["id"]) for m in log_side])
                self._conn.executemany(
                    "DELETE FROM photo_players WHERE photo_id=?",
                    [(m["id"],) for m in log_side])
                rows = [(m["id"], n, u) for m in log_side for n, u in m["players"]]
                if rows:
                    self._conn.executemany(
                        "INSERT OR IGNORE INTO photo_players(photo_id, name, user_id) "
                        "VALUES(?,?,?)", rows)
            self._conn.commit()

    def photos_for_log_match(self):
        with self._lock:
            return self._conn.execute(
                "SELECT id, taken_at, meta_source FROM photos "
                "WHERE missing=0 AND taken_at IS NOT NULL"
            ).fetchall()

    def update_path(self, pid, new_path, new_size, new_mtime):
        with self._lock:
            self._conn.execute(
                "UPDATE photos SET path=?, filename=?, filesize=?, mtime=? WHERE id=?",
                (new_path, os.path.basename(new_path), new_size, new_mtime, pid))
            self._conn.commit()

    # ---------- logs / sessions ----------

    def forget_logs(self):
        """Drop the 'already parsed' marks so every log file is read again."""
        with self._lock:
            self._conn.execute("DELETE FROM logs")
            self._conn.commit()

    def logs_state(self):
        with self._lock:
            rows = self._conn.execute("SELECT file, size, mtime FROM logs").fetchall()
        return {r["file"]: (r["size"], r["mtime"]) for r in rows}

    def replace_log_sessions(self, log_file, size, mtime, sessions, avatar_events=()):
        """sessions: dicts(world_id, world_name, start, end, players=[(name,uid,join,leave)]).
        avatar_events: [(iso, player, avatar)] for the whole log file."""
        with self._lock:
            cur = self._conn.cursor()
            old = cur.execute("SELECT id FROM sessions WHERE log_file=?", (log_file,)).fetchall()
            if old:
                ids = [(r["id"],) for r in old]
                cur.executemany("DELETE FROM session_players WHERE session_id=?", ids)
                cur.execute("DELETE FROM sessions WHERE log_file=?", (log_file,))
            cur.execute("DELETE FROM avatar_events WHERE log_file=?", (log_file,))
            if avatar_events:
                cur.executemany(
                    "INSERT OR IGNORE INTO avatar_events(log_file, at, player, avatar) "
                    "VALUES(?,?,?,?)",
                    [(log_file, at, who, av) for at, who, av in avatar_events])
            for s in sessions:
                cur.execute(
                    "INSERT INTO sessions(log_file, world_id, world_name, start_at, end_at,"
                    " instance_type, region) VALUES(?,?,?,?,?,?,?)",
                    (log_file, s["world_id"], s["world_name"], s["start"], s["end"],
                     s.get("instance_type") or "", s.get("region") or ""))
                sid = cur.lastrowid
                cur.executemany(
                    "INSERT INTO session_players(session_id, name, user_id, join_at, leave_at) "
                    "VALUES(?,?,?,?,?)",
                    [(sid, n, u, j, l) for n, u, j, l in s["players"]])
            cur.execute(
                "INSERT INTO logs(file, size, mtime) VALUES(?,?,?) "
                "ON CONFLICT(file) DO UPDATE SET size=excluded.size, mtime=excluded.mtime",
                (log_file, size, mtime))
            self._conn.commit()

    def all_sessions(self):
        with self._lock:
            ses = self._conn.execute(
                "SELECT id, world_id, world_name, start_at, end_at, instance_type, region "
                "FROM sessions ORDER BY start_at").fetchall()
            pls = self._conn.execute(
                "SELECT session_id, name, user_id, join_at, leave_at FROM session_players"
            ).fetchall()
        by_sid = {}
        for p in pls:
            by_sid.setdefault(p["session_id"], []).append(
                (p["name"], p["user_id"], p["join_at"], p["leave_at"]))
        out = []
        for s in ses:
            out.append({"id": s["id"], "world_id": s["world_id"],
                        "world_name": s["world_name"],
                        "start": s["start_at"], "end": s["end_at"],
                        "instance_type": s["instance_type"], "region": s["region"],
                        "players": by_sid.get(s["id"], [])})
        return out

    def self_avatar_events(self, self_names):
        """[(iso, avatar)] for the local user, oldest first."""
        if not self_names:
            return []
        q = ",".join("?" * len(self_names))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT at, avatar FROM avatar_events WHERE player IN ({q}) ORDER BY at",
                list(self_names)).fetchall()
        return [(r["at"], r["avatar"]) for r in rows]

    def known_players(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT player FROM avatar_events").fetchall()
        return {r["player"] for r in rows}

    # ---------- queries for the UI ----------

    def _filter_sql(self, f: PhotoFilter, self_names=()):
        where = ["p.missing=0"]
        params = []
        if f.favorites:
            where.append("p.favorite=1")
        if f.world_id:
            where.append("p.world_id=?")
            params.append(f.world_id)
        if f.day:
            where.append("p.day=?")
            params.append(f.day)
        if f.person:
            # somebody hand-tagged in the frame counts too, even when the logs
            # never saw them (an old photo, a name typed in by hand)
            where.append(
                "(EXISTS(SELECT 1 FROM photo_players pp WHERE pp.photo_id=p.id AND pp.name=?)"
                " OR EXISTS(SELECT 1 FROM photo_tags pt WHERE pt.photo_id=p.id AND pt.name=?))")
            params += [f.person, f.person]
        if f.avatar:
            where.append("p.avatar_name=?")
            params.append(f.avatar)
        if f.session_id:
            where.append("p.session_id=?")
            params.append(f.session_id)
        if f.date_from:
            where.append("p.day >= ?")
            params.append(f.date_from)
        if f.date_to:
            where.append("p.day <= ?")
            params.append(f.date_to)
        if f.instance_type:
            where.append("p.instance_type=?")
            params.append(f.instance_type)
        if f.min_rating:
            where.append("p.rating >= ?")
            params.append(int(f.min_rating))
        if f.media == "video":
            where.append("p.is_video=1")
        elif f.media == "photo":
            where.append("p.is_video=0")
        if f.album_id:
            where.append("p.id IN (SELECT photo_id FROM album_photos WHERE album_id=?)")
            params.append(f.album_id)
        if f.text:
            # % and _ are LIKE wildcards: someone typing "50%" wants that text,
            # not "everything containing 50"
            escaped = (f.text.replace("\\", "\\\\").replace("%", "\\%")
                       .replace("_", "\\_"))
            like = "%" + escaped + "%"
            where.append(
                "(p.world_name LIKE ? ESCAPE '\\' OR p.filename LIKE ? ESCAPE '\\' "
                "OR EXISTS(SELECT 1 FROM photo_players pp WHERE pp.photo_id=p.id "
                "AND pp.name LIKE ? ESCAPE '\\') "
                "OR EXISTS(SELECT 1 FROM photo_tags pt WHERE pt.photo_id=p.id "
                "AND pt.name LIKE ? ESCAPE '\\'))")
            params += [like, like, like, like]
        return " AND ".join(where), params

    def query_photos(self, f: PhotoFilter):
        where, params = self._filter_sql(f)
        order = "DESC" if f.sort_desc else "ASC"
        sql = (f"SELECT p.id, p.path, p.taken_at, p.day, p.world_id, p.world_name, "
               f"p.favorite, p.width, p.height, p.filesize, p.meta_source, p.mtime, "
               f"p.avatar_name, p.session_id, p.instance_type, p.rating, p.is_video "
               f"FROM photos p WHERE {where} ORDER BY p.taken_at {order}, p.id {order}")
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def counts(self):
        with self._lock:
            r = self._conn.execute(
                "SELECT COUNT(*) c, COALESCE(SUM(filesize),0) s, "
                "SUM(CASE WHEN favorite=1 THEN 1 ELSE 0 END) f "
                "FROM photos WHERE missing=0").fetchone()
        return r["c"], r["s"], r["f"] or 0

    def photo(self, pid):
        with self._lock:
            r = self._conn.execute("SELECT * FROM photos WHERE id=?", (pid,)).fetchone()
            pl = self._conn.execute(
                "SELECT name, user_id FROM photo_players WHERE photo_id=? ORDER BY name",
                (pid,)).fetchall()
        return r, [(p["name"], p["user_id"]) for p in pl]

    def set_rating(self, pids, stars):
        stars = max(0, min(5, int(stars)))
        with self._lock:
            self._conn.executemany("UPDATE photos SET rating=? WHERE id=?",
                                   [(stars, p) for p in pids])
            self._conn.commit()

    def region_summary(self, year=""):
        yr = " AND substr(day,1,4)=?" if year else ""
        y = [str(year)] if year else []
        with self._lock:
            return self._conn.execute(
                f"SELECT region, COUNT(*) c FROM photos "
                f"WHERE missing=0 AND region IS NOT NULL AND region != ''{yr} "
                f"GROUP BY region ORDER BY c DESC", y).fetchall()

    def instance_summary(self, year=""):
        yr = " AND substr(day,1,4)=?" if year else ""
        y = [str(year)] if year else []
        with self._lock:
            return self._conn.execute(
                f"SELECT instance_type, COUNT(*) c FROM photos "
                f"WHERE missing=0 AND instance_type IS NOT NULL AND instance_type != ''{yr} "
                f"GROUP BY instance_type ORDER BY c DESC", y).fetchall()

    def set_favorite(self, pids, on):
        with self._lock:
            self._conn.executemany("UPDATE photos SET favorite=? WHERE id=?",
                                   [(1 if on else 0, p) for p in pids])
            self._conn.commit()

    def favorites_of(self, pids):
        if not pids:
            return set()
        q = ",".join("?" * len(pids))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT id FROM photos WHERE favorite=1 AND id IN ({q})", list(pids)).fetchall()
        return {r["id"] for r in rows}

    def mark_recycled(self, pids, when=""):
        """`deleted_at` is what separates "the app put this in the Recycle Bin"
        from "the file simply is not there any more", which also sets missing."""
        with self._lock:
            self._conn.executemany(
                "UPDATE photos SET missing=1, deleted_at=? WHERE id=?",
                [(when, p) for p in pids])
            self._conn.commit()

    def recently_deleted(self, limit=500):
        with self._lock:
            return self._conn.execute(
                "SELECT id, path, taken_at, day, world_name, favorite, filesize, mtime, "
                "deleted_at FROM photos "
                "WHERE missing=1 AND deleted_at IS NOT NULL AND deleted_at != '' "
                "ORDER BY deleted_at DESC, taken_at DESC LIMIT ?", (limit,)).fetchall()

    def restore_photos(self, pids):
        with self._lock:
            self._conn.executemany(
                "UPDATE photos SET missing=0, deleted_at=NULL WHERE id=?",
                [(p,) for p in pids])
            self._conn.commit()

    # ---------- periods (years / months) ----------

    def period_summary(self, level, year=""):
        """Year or month cards: [(key, count, bytes, cover_id)].

        The cover is the best photo of the period -- a favourite, else the
        highest rated, else the newest -- so a year is not represented by
        whatever happened to be last.
        """
        span = 4 if level == "year" else 7
        where = ["missing=0", "day IS NOT NULL", "is_video=0"]
        params = []
        if year:
            where.append("substr(day,1,4)=?")
            params.append(str(year))
        w = " AND ".join(where)
        with self._lock:
            return self._conn.execute(
                f"""SELECT substr(day,1,{span}) k, COUNT(*) c, COALESCE(SUM(filesize),0) b,
                        (SELECT p2.id FROM photos p2
                          WHERE p2.missing=0 AND p2.is_video=0
                            AND substr(p2.day,1,{span})=substr(p.day,1,{span})
                          ORDER BY p2.favorite DESC, p2.rating DESC, p2.taken_at DESC
                          LIMIT 1) cover_id
                   FROM photos p WHERE {w}
                   GROUP BY k ORDER BY k DESC""", params).fetchall()

    # ---------- in-frame tags ----------

    def photo_tags(self, photo_id):
        """[(name, x, y, w, h)] — box in image fractions."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, x, y, w, h FROM photo_tags WHERE photo_id=? ORDER BY name",
                (photo_id,)).fetchall()
        return [(r["name"], r["x"], r["y"], r["w"] or 0.0, r["h"] or 0.0) for r in rows]

    def tags_for_photos(self, ids):
        ids = [i for i in ids if i]
        if not ids:
            return {}
        q = ",".join("?" * len(ids))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT photo_id, name, x, y, w, h FROM photo_tags "
                f"WHERE photo_id IN ({q})", list(ids)).fetchall()
        out = {}
        for r in rows:
            out.setdefault(r["photo_id"], []).append(
                (r["name"], r["x"], r["y"], r["w"] or 0.0, r["h"] or 0.0))
        return out

    def set_photo_tag(self, photo_id, name, x, y, w=0.0, h=0.0, when="", sig=None):
        """Placing the same name twice moves and resizes the existing box.

        The signature is overwritten along with the box, NULL included: a box
        that has moved no longer looks like what its old signature recorded, and
        a NULL is simply a note to work it out again later.
        """
        vals = (float(x), float(y), float(w), float(h))
        with self._lock:
            self._conn.execute(
                "INSERT INTO photo_tags(photo_id, name, x, y, w, h, created_at, sig) "
                "VALUES(?,?,?,?,?,?,?,?) "
                "ON CONFLICT(photo_id, name) DO UPDATE SET x=?, y=?, w=?, h=?, sig=?",
                (photo_id, name) + vals + (when, sig) + vals + (sig,))
            self._conn.commit()

    def tag_sigs_for(self, names):
        """{name: [signature, ...]} for the people worth considering.

        The caller narrows `names` to whoever the logs put in that instance --
        that restriction is most of why the guess is any good.
        """
        names = [n for n in dict.fromkeys(names) if n]
        if not names:
            return {}
        out = {}
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, sig FROM photo_tags WHERE sig IS NOT NULL "
                "AND length(sig) > 0 AND name IN (%s)" % ",".join("?" * len(names)),
                names).fetchall()
        for r in rows:
            out.setdefault(r["name"], []).append(bytes(r["sig"]))
        return out

    def tags_needing_sig(self, limit=500):
        """Tags placed before signatures existed, or whose box has since moved."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT t.photo_id, t.name, t.x, t.y, t.w, t.h, p.path "
                "FROM photo_tags t JOIN photos p ON p.id = t.photo_id "
                "WHERE t.sig IS NULL AND p.missing = 0 LIMIT ?", (limit,)).fetchall()
        return [(r["photo_id"], r["name"], r["x"], r["y"],
                 r["w"] or 0.0, r["h"] or 0.0, r["path"]) for r in rows]

    def set_tag_sigs(self, rows):
        """[(sig, photo_id, name), ...] in one transaction.

        A box that could not produce one is stored as a zero-length blob rather
        than left NULL, so the next index pass does not decode its photo again
        to fail in the same way.
        """
        if not rows:
            return
        with self._lock:
            self._conn.executemany(
                "UPDATE photo_tags SET sig=? WHERE photo_id=? AND name=?", rows)
            self._conn.commit()

    def remove_photo_tag(self, photo_id, name):
        with self._lock:
            self._conn.execute("DELETE FROM photo_tags WHERE photo_id=? AND name=?",
                               (photo_id, name))
            self._conn.commit()

    def tag_names(self, limit=200):
        """Everyone ever tagged, most used first — the picker's memory."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, COUNT(*) c FROM photo_tags GROUP BY name "
                "ORDER BY c DESC, name LIMIT ?", (limit,)).fetchall()
        return [r["name"] for r in rows]

    def tagged_count(self):
        with self._lock:
            r = self._conn.execute(
                "SELECT COUNT(DISTINCT photo_id) c FROM photo_tags").fetchone()
        return r["c"] if r else 0

    # ---------- albums ----------

    def albums(self):
        with self._lock:
            return self._conn.execute(
                """SELECT a.id, a.name, COUNT(ap.photo_id) AS cnt,
                       (SELECT p.id FROM album_photos ap2 JOIN photos p ON p.id=ap2.photo_id
                        WHERE ap2.album_id=a.id AND p.missing=0 AND p.is_video=0
                        ORDER BY p.taken_at DESC LIMIT 1) AS cover_id
                   FROM albums a LEFT JOIN album_photos ap ON ap.album_id=a.id
                   GROUP BY a.id ORDER BY a.name COLLATE NOCASE""").fetchall()

    def photos_by_ids(self, ids):
        ids = [i for i in ids if i]
        if not ids:
            return {}
        q = ",".join("?" * len(ids))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT id, path, mtime, filesize, scanned FROM photos WHERE id IN ({q})",
                list(ids)).fetchall()
        return {r["id"]: r for r in rows}

    def create_album(self, name, created_at):
        with self._lock:
            try:
                cur = self._conn.execute(
                    "INSERT INTO albums(name, created_at) VALUES(?,?)", (name, created_at))
                self._conn.commit()
                return cur.lastrowid
            except sqlite3.IntegrityError:
                r = self._conn.execute("SELECT id FROM albums WHERE name=?", (name,)).fetchone()
                return r["id"] if r else 0

    def rename_album(self, aid, name):
        with self._lock:
            try:
                self._conn.execute("UPDATE albums SET name=? WHERE id=?", (name, aid))
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def delete_album(self, aid):
        with self._lock:
            self._conn.execute("DELETE FROM album_photos WHERE album_id=?", (aid,))
            self._conn.execute("DELETE FROM albums WHERE id=?", (aid,))
            self._conn.commit()

    def album_add(self, aid, pids, added_at):
        with self._lock:
            self._conn.executemany(
                "INSERT OR IGNORE INTO album_photos(album_id, photo_id, added_at) VALUES(?,?,?)",
                [(aid, p, added_at) for p in pids])
            self._conn.commit()

    def album_remove(self, aid, pids):
        with self._lock:
            self._conn.executemany(
                "DELETE FROM album_photos WHERE album_id=? AND photo_id=?",
                [(aid, p) for p in pids])
            self._conn.commit()

    def album_name(self, aid):
        with self._lock:
            r = self._conn.execute("SELECT name FROM albums WHERE id=?", (aid,)).fetchone()
        return r["name"] if r else ""

    # ---------- browse: worlds / people ----------

    def worlds_summary(self):
        with self._lock:
            return self._conn.execute(
                """SELECT p.world_id, COUNT(*) cnt, MAX(p.taken_at) last,
                        (SELECT p2.world_name FROM photos p2 WHERE p2.world_id=p.world_id
                          AND p2.world_name IS NOT NULL ORDER BY p2.taken_at DESC LIMIT 1) name,
                        (SELECT p3.id FROM photos p3 WHERE p3.world_id=p.world_id
                          AND p3.missing=0 AND p3.is_video=0
              ORDER BY p3.taken_at DESC LIMIT 1) cover_id
                   FROM photos p
                   WHERE p.missing=0 AND p.world_id IS NOT NULL
                   GROUP BY p.world_id ORDER BY cnt DESC""").fetchall()

    def people_summary(self, self_names):
        ex = ""
        params = []
        if self_names:
            ex = " AND pp.name NOT IN (%s)" % ",".join("?" * len(self_names))
            params = list(self_names)
        with self._lock:
            return self._conn.execute(
                f"""SELECT pp.name, COUNT(DISTINCT pp.photo_id) cnt, MAX(p.taken_at) last,
                        (SELECT p2.id FROM photos p2 JOIN photo_players q ON q.photo_id=p2.id
                          WHERE q.name=pp.name AND p2.missing=0 AND p2.is_video=0
                          ORDER BY p2.taken_at DESC LIMIT 1) cover_id
                   FROM photo_players pp JOIN photos p ON p.id=pp.photo_id
                   WHERE p.missing=0{ex}
                   GROUP BY pp.name ORDER BY cnt DESC""", params).fetchall()

    def avatars_summary(self):
        with self._lock:
            return self._conn.execute(
                """SELECT p.avatar_name name, COUNT(*) cnt, MAX(p.taken_at) last,
                        (SELECT p2.id FROM photos p2 WHERE p2.avatar_name=p.avatar_name
                          AND p2.missing=0 AND p2.is_video=0
              ORDER BY p2.taken_at DESC LIMIT 1) cover_id
                   FROM photos p
                   WHERE p.missing=0 AND p.avatar_name IS NOT NULL AND p.avatar_name != ''
                   GROUP BY p.avatar_name ORDER BY cnt DESC""").fetchall()

    def sessions_with_photos(self, limit=400):
        """Sessions that actually produced photos, newest first."""
        with self._lock:
            return self._conn.execute(
                """SELECT s.id, s.world_id, s.world_name, s.start_at, s.end_at,
                        s.instance_type, s.region,
                        COUNT(p.id) cnt, COALESCE(SUM(p.filesize),0) bytes,
                        MIN(p.taken_at) first_shot, MAX(p.taken_at) last_shot,
                        (SELECT p2.id FROM photos p2 WHERE p2.session_id=s.id AND p2.missing=0
               AND p2.is_video=0
                          ORDER BY p2.favorite DESC, p2.taken_at LIMIT 1) cover_id
                   FROM sessions s JOIN photos p ON p.session_id=s.id AND p.missing=0
                   GROUP BY s.id ORDER BY s.start_at DESC LIMIT ?""", (limit,)).fetchall()

    def session_people(self, session_id, self_names=()):
        ex = ""
        params = [session_id]
        if self_names:
            ex = " AND name NOT IN (%s)" % ",".join("?" * len(self_names))
            params += list(self_names)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT DISTINCT name FROM session_players WHERE session_id=?{ex} "
                f"ORDER BY name COLLATE NOCASE", params).fetchall()
        return [r["name"] for r in rows]

    def session_row(self, session_id):
        with self._lock:
            return self._conn.execute(
                "SELECT id, world_id, world_name, start_at, end_at FROM sessions WHERE id=?",
                (session_id,)).fetchone()

    def hashed_photos(self):
        with self._lock:
            return self._conn.execute(
                "SELECT id, path, taken_at, day, world_name, favorite, filesize, mtime, "
                "dhash, luma FROM photos "
                "WHERE missing=0 AND dhash IS NOT NULL ORDER BY taken_at").fetchall()

    # ---------- memories / stats ----------

    def memories(self, mmdd, before_year):
        with self._lock:
            return self._conn.execute(
                """SELECT substr(day,1,4) y, COUNT(*) cnt FROM photos
                   WHERE missing=0 AND substr(day,6,5)=? AND substr(day,1,4) < ?
                   GROUP BY y ORDER BY y DESC""", (mmdd, str(before_year))).fetchall()

    def distinct_days(self):
        """How many separate days you actually took a photograph on."""
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(DISTINCT day) c FROM photos "
                "WHERE missing=0 AND day IS NOT NULL").fetchone()["c"]

    def top_people(self, limit=6, self_names=()):
        """Who appears in the most photographs, with when you last saw them."""
        ex, params = "", []
        if self_names:
            ex = " AND pp.name NOT IN (%s)" % ",".join("?" * len(self_names))
            params = list(self_names)
        with self._lock:
            return self._conn.execute(
                f"""SELECT pp.name, COUNT(DISTINCT pp.photo_id) c, MAX(p.day) last_day
                    FROM photo_players pp JOIN photos p ON p.id=pp.photo_id
                    WHERE p.missing=0{ex}
                    GROUP BY pp.name ORDER BY c DESC LIMIT ?""",
                params + [limit]).fetchall()

    # A sitting ends at the first break longer than this. The log keeps a row
    # per instance visit, and a world hop, a crash-and-rejoin or a quick reload
    # are all a few minutes apart; going to sleep and coming back is not.
    # Measured on a month of logs: 60, 90, 120 and 180 minutes give 46, 40, 38
    # and 38 sittings -- 90 is where the count stops being sensitive to it.
    SITTING_GAP_MIN = 90

    def last_sitting(self, self_names=(), until=None):
        """The most recent stretch of time in VRChat, summed up.

        NOT a calendar day. The first version of this grouped sessions by the
        date they started on, and 24 of the 40 sittings in the logs cross
        midnight: the tail of a night landed on the next date and was added to
        that afternoon, so the card could report "9h 16m, 12 stops" for two
        different evenings glued together. A sitting is instead a run of
        sessions with no break longer than SITTING_GAP_MIN.

        People who were still in the instance when the log ended have no leave
        time -- VRChat writes nothing when you quit -- and they are usually the
        ones who stayed longest. Their time runs to the end of the session
        rather than being dropped, which is what the rest of the app already
        does with a missing leave. While the game is running, that is everybody
        in the room right now, and `present` says so.

        People are keyed by user id where the log has one, so a friend who
        changed display name mid-month is one person, shown under the latest
        name. Your own rows are left out by name AND by the ids those names
        carry, so a renamed you is still you.

        `until` extends the photo window to now while a sitting is still going:
        the log's last line is behind the screenshot you just took.

        -> dict, or None when there are no sessions at all (a fresh install, or
        a library whose logs were never seen -- the logs only reach back as far
        as the app has been running).
        """
        from datetime import datetime as _dt, timedelta as _td

        def when(s):
            try:
                return _dt.fromisoformat(s[:19])
            except (TypeError, ValueError):
                return None

        def span(a, b):
            """Minutes from a to b. The log's times are local wall clock, so the
            night the clocks go back a session inside the repeated hour ends
            "before" it began, and clamping that to zero lost it and everybody
            in it. A negative span of under an hour is that, and gets its hour
            back. (A session that straddles the change still reads an hour
            short: the log carries no zone, so there is nothing to tell by.)"""
            d = (b - a).total_seconds() / 60
            if -60 <= d < 0:
                d += 60
            return max(0.0, d)

        with self._lock:
            rows = self._conn.execute(
                "SELECT id, log_file, world_id, world_name, instance_type, start_at, "
                "COALESCE(end_at, start_at) end_at FROM sessions "
                "WHERE start_at IS NOT NULL ORDER BY start_at DESC LIMIT 400").fetchall()
            if not rows:
                return None
            sit = [rows[0]]
            for r in rows[1:]:
                gap = (when(sit[-1]["start_at"]) - when(r["end_at"])).total_seconds() / 60
                if gap > self.SITTING_GAP_MIN:
                    break
                sit.append(r)
            sit.reverse()                                  # oldest first
            ids = [r["id"] for r in sit]
            q = ",".join("?" * len(ids))
            last = sit[-1]
            start = when(sit[0]["start_at"])
            end = max(when(r["end_at"]) for r in sit)

            worlds = {}
            mins = 0.0
            for r in sit:
                m = span(when(r["start_at"]), when(r["end_at"]))
                mins += m
                key = r["world_id"] or r["world_name"] or "?"
                w = worlds.setdefault(key, [r["world_id"], r["world_name"] or "", 0.0])
                w[2] += m
                if r["world_name"]:
                    w[1] = r["world_name"]                 # the latest name wins

            players = self._conn.execute(
                f"""SELECT sp.name, sp.user_id, sp.join_at, sp.leave_at, sp.session_id,
                        COALESCE(s.end_at, s.start_at) s_end
                    FROM session_players sp JOIN sessions s ON s.id=sp.session_id
                    WHERE sp.session_id IN ({q})""", ids).fetchall()
            selfn = set(self_names)
            self_ids = {p["user_id"] for p in players
                        if p["name"] in selfn and p["user_id"]}
            people = {}
            for p in players:
                if p["name"] in selfn or (p["user_id"] and p["user_id"] in self_ids):
                    continue
                j = when(p["join_at"])
                l = when(p["leave_at"]) or when(p["s_end"])
                if j is None or l is None:
                    continue
                key = p["user_id"] or ("name:" + p["name"])
                d = people.setdefault(key, {"name": p["name"], "user_id": p["user_id"],
                                            "minutes": 0.0, "present": False,
                                            "_seen": j})
                d["minutes"] += span(j, l)
                if j >= d["_seen"]:
                    d["_seen"], d["name"] = j, p["name"]
                if p["session_id"] == last["id"] and p["leave_at"] is None:
                    d["present"] = True
            # By time together. "Present" is NOT a sort key here: for a sitting
            # that is over it only means "still in the room when the log ended",
            # and sorting on it put somebody with 160 minutes behind five people
            # with under an hour. The page puts present people first itself, and
            # only while the game is actually running.
            ranked = sorted(people.values(), key=lambda d: -d["minutes"])
            keep = ranked[:8] + [d for d in ranked[8:] if d["present"]][:8]
            for d in ranked:
                d.pop("_seen", None)
                d["photo_name"] = None
            ranked = keep
            for d in ranked:
                # the name the person page knows them by, if they are in any
                # photograph at all -- a chip for somebody who is not opens an
                # empty grid, which reads as a broken library
                # By id first, so a friend photographed under an older name
                # still gets a link; then by name, because photo metadata from
                # before ids were recorded -- or from another tool -- has none.
                r = None
                if d["user_id"]:
                    r = self._conn.execute(
                        "SELECT pp.name FROM photo_players pp JOIN photos ph "
                        "ON ph.id=pp.photo_id WHERE pp.user_id=? AND ph.missing=0 "
                        "ORDER BY ph.taken_at DESC LIMIT 1", (d["user_id"],)).fetchone()
                if r is None:
                    r = self._conn.execute(
                        "SELECT pp.name FROM photo_players pp JOIN photos ph "
                        "ON ph.id=pp.photo_id WHERE pp.name=? AND ph.missing=0 LIMIT 1",
                        (d["name"],)).fetchone()
                d["photo_name"] = r["name"] if r else None

            hi = max(end, until) if until else end
            lo_s = start.isoformat()
            hi_s = (hi + _td(minutes=10)).isoformat()
            photo_ids = [r["id"] for r in self._conn.execute(
                f"""SELECT id FROM photos WHERE missing=0 AND is_video=0
                    AND (session_id IN ({q}) OR (taken_at >= ? AND taken_at <= ?))
                    ORDER BY taken_at""", ids + [lo_s, hi_s])]

            avatar = None
            if selfn:
                sq = ",".join("?" * len(selfn))
                r = self._conn.execute(
                    f"SELECT avatar FROM avatar_events WHERE player IN ({sq}) "
                    f"AND at >= ? AND at <= ? ORDER BY at DESC LIMIT 1",
                    list(selfn) + [lo_s, hi_s]).fetchone()
                avatar = r["avatar"] if r else None

        return {
            "start": start, "end": end, "mins": mins, "sessions": len(sit),
            "log_file": last["log_file"], "instance_type": last["instance_type"] or "",
            "world_id": last["world_id"], "world_name": last["world_name"] or "",
            "worlds": sorted(([w[0], w[1], w[2]] for w in worlds.values()),
                             key=lambda w: -w[2]),
            "people": ranked, "people_total": len(people),
            "photo_ids": photo_ids, "avatar": avatar,
        }

    def recent_worlds(self, limit=5, min_photos=3):
        """Places you have been lately, newest first, with a cover each."""
        with self._lock:
            return self._conn.execute(
                """SELECT p.world_id, MAX(p.world_name) world_name, COUNT(*) c,
                        MAX(p.day) last_day,
                        (SELECT q.id FROM photos q WHERE q.world_id=p.world_id
                          AND q.missing=0 AND q.is_video=0
                          ORDER BY q.taken_at DESC LIMIT 1) cover_id
                   FROM photos p
                   WHERE p.missing=0 AND p.world_id IS NOT NULL AND p.world_name<>''
                   GROUP BY p.world_id HAVING c>=?
                   ORDER BY last_day DESC LIMIT ?""",
                (min_photos, limit)).fetchall()

    def home_stamp(self, self_names=()):
        """Cheap fingerprint of everything the home page reads, so a visit that
        would rebuild the identical page can skip the work -- the same guard the
        sessions and moments pages already use."""
        with self._lock:
            a = self._conn.execute(
                "SELECT COUNT(*) c, MAX(taken_at) m, COALESCE(SUM(filesize),0) b "
                "FROM photos WHERE missing=0").fetchone()
            # MAX(end_at) and the filled-in leaves, not just the session count:
            # an evening spent in one instance adds no session at all, it only
            # makes the last one longer and fills in who left. With the count
            # alone the card froze at whatever it said when first drawn.
            b = self._conn.execute(
                "SELECT COUNT(*) c, MAX(start_at) m, MAX(end_at) e FROM sessions").fetchone()
            c = self._conn.execute(
                "SELECT COUNT(*) c, COUNT(leave_at) l FROM session_players").fetchone()
            d = self._conn.execute("SELECT COUNT(*) c FROM avatar_events").fetchone()
            f = self._conn.execute(
                "SELECT log_file FROM sessions ORDER BY start_at DESC LIMIT 1").fetchone()
        # Two parts, because they change at very different rates. The session
        # part moves on EVERY log pass while the game runs -- every fifteen
        # seconds or so -- and folded into one fingerprint it rebuilt the whole
        # page each time, thumbnails and all, to change one card. The page
        # rebuilds on the photo part; the session part only rebuilds the card.
        # The newest session's log file goes LAST in it on purpose: the page
        # compares that with the log the game is writing to decide "live".
        return ((a["c"], a["m"], a["b"]),
                (b["c"], b["m"], b["e"], c["c"], c["l"], d["c"],
                 f["log_file"] if f else None))

    def random_rich_day(self, min_photos=5):
        with self._lock:
            return self._conn.execute(
                """SELECT day, COUNT(*) c FROM photos WHERE missing=0 AND day IS NOT NULL
                   GROUP BY day HAVING c>=? ORDER BY RANDOM() LIMIT 1""",
                (min_photos,)).fetchone()

    def stats(self, self_names, year=""):
        """Whole-library figures, or one year of them when `year` is given."""
        ex = ""
        params = []
        if self_names:
            ex = " AND pp.name NOT IN (%s)" % ",".join("?" * len(self_names))
            params = list(self_names)
        # `p.` for the queries that join, bare for the ones that do not
        yr = " AND substr(day,1,4)=?" if year else ""
        yrp = " AND substr(p.day,1,4)=?" if year else ""
        y = [str(year)] if year else []
        with self._lock:
            tot = self._conn.execute(
                f"SELECT COUNT(*) c, COALESCE(SUM(filesize),0) s FROM photos "
                f"WHERE missing=0{yr}", y).fetchone()
            worlds = self._conn.execute(
                f"SELECT COUNT(DISTINCT world_id) c FROM photos "
                f"WHERE missing=0 AND world_id IS NOT NULL{yr}", y).fetchone()
            people = self._conn.execute(
                f"SELECT COUNT(DISTINCT pp.name) c FROM photo_players pp "
                f"JOIN photos p ON p.id=pp.photo_id WHERE p.missing=0{yrp}{ex}",
                y + params).fetchone()
            busiest = self._conn.execute(
                f"SELECT day, COUNT(*) c FROM photos WHERE missing=0 AND day IS NOT NULL{yr} "
                f"GROUP BY day ORDER BY c DESC, day DESC LIMIT 1", y).fetchone()
            months = self._conn.execute(
                f"SELECT substr(day,1,7) m, COUNT(*) c FROM photos "
                f"WHERE missing=0 AND day IS NOT NULL{yr} GROUP BY m ORDER BY m", y).fetchall()
            top_worlds = self._conn.execute(
                f"""SELECT COALESCE(
                        (SELECT p2.world_name FROM photos p2 WHERE p2.world_id=p.world_id
                          AND p2.world_name IS NOT NULL ORDER BY p2.taken_at DESC LIMIT 1),
                        p.world_id) name, COUNT(*) c
                   FROM photos p WHERE p.missing=0 AND p.world_id IS NOT NULL{yrp}
                   GROUP BY p.world_id ORDER BY c DESC LIMIT 10""", y).fetchall()
            top_people = self._conn.execute(
                f"""SELECT pp.name, COUNT(DISTINCT pp.photo_id) c FROM photo_players pp
                    JOIN photos p ON p.id=pp.photo_id WHERE p.missing=0{yrp}{ex}
                    GROUP BY pp.name ORDER BY c DESC LIMIT 10""", y + params).fetchall()
            hours = self._conn.execute(
                f"SELECT substr(taken_at,12,2) h, COUNT(*) c FROM photos "
                f"WHERE missing=0 AND taken_at IS NOT NULL{yr} "
                f"GROUP BY h ORDER BY h", y).fetchall()
            top_avatars = self._conn.execute(
                f"SELECT avatar_name name, COUNT(*) c FROM photos "
                f"WHERE missing=0 AND avatar_name IS NOT NULL AND avatar_name != ''{yr} "
                f"GROUP BY avatar_name ORDER BY c DESC LIMIT 10", y).fetchall()
            sessions = self._conn.execute(
                f"SELECT COUNT(DISTINCT session_id) c FROM photos "
                f"WHERE missing=0 AND session_id IS NOT NULL{yr}", y).fetchone()
        return {"total": tot["c"], "bytes": tot["s"], "worlds": worlds["c"],
                "people": people["c"], "busiest": busiest,
                "months": months, "top_worlds": top_worlds,
                "top_people": top_people, "hours": hours,
                "top_avatars": top_avatars, "sessions": sessions["c"]}

    def person_stats(self, name, self_names=()):
        """Everything the People detail page needs about one person."""
        with self._lock:
            basic = self._conn.execute(
                """SELECT COUNT(*) photos, MIN(p.taken_at) first_at, MAX(p.taken_at) last_at,
                        COUNT(DISTINCT p.session_id) sessions,
                        COUNT(DISTINCT p.world_id) worlds
                   FROM photo_players pp JOIN photos p ON p.id=pp.photo_id
                   WHERE pp.name=? AND p.missing=0""", (name,)).fetchone()
            worlds = self._conn.execute(
                """SELECT COALESCE(p.world_name, p.world_id) name, COUNT(*) c
                   FROM photo_players pp JOIN photos p ON p.id=pp.photo_id
                   WHERE pp.name=? AND p.missing=0 AND p.world_id IS NOT NULL
                   GROUP BY p.world_id ORDER BY c DESC LIMIT 5""", (name,)).fetchall()
            months = self._conn.execute(
                """SELECT substr(p.day,1,7) m, COUNT(*) c
                   FROM photo_players pp JOIN photos p ON p.id=pp.photo_id
                   WHERE pp.name=? AND p.missing=0 AND p.day IS NOT NULL
                   GROUP BY m ORDER BY m""", (name,)).fetchall()
            # people who show up in the same photos
            ex = ""
            params = [name, name]
            if self_names:
                ex = " AND q.name NOT IN (%s)" % ",".join("?" * len(self_names))
                params += list(self_names)
            together = self._conn.execute(
                f"""SELECT q.name, COUNT(*) c FROM photo_players pp
                    JOIN photo_players q ON q.photo_id = pp.photo_id
                    JOIN photos p ON p.id = pp.photo_id
                    WHERE pp.name=? AND q.name != ? AND p.missing=0{ex}
                    GROUP BY q.name ORDER BY c DESC LIMIT 6""", params).fetchall()
            first_session = self._conn.execute(
                """SELECT s.world_name, s.start_at FROM session_players sp
                   JOIN sessions s ON s.id = sp.session_id
                   WHERE sp.name=? ORDER BY s.start_at LIMIT 1""", (name,)).fetchone()
        return {"basic": basic, "worlds": worlds, "months": months,
                "together": together, "first_session": first_session}

    def people_last_seen(self, self_names=(), min_photos=8):
        """Regulars and when you last saw them — feeds the 'drifted apart' list."""
        ex = ""
        params = []
        if self_names:
            ex = " AND pp.name NOT IN (%s)" % ",".join("?" * len(self_names))
            params = list(self_names)
        params.append(min_photos)
        with self._lock:
            return self._conn.execute(
                f"""SELECT pp.name, COUNT(*) c, MAX(p.taken_at) last_at,
                        MIN(p.taken_at) first_at
                    FROM photo_players pp JOIN photos p ON p.id=pp.photo_id
                    WHERE p.missing=0{ex}
                    GROUP BY pp.name HAVING c >= ? ORDER BY last_at DESC""",
                params).fetchall()

    def moments_stamp(self, self_names=()):
        """Cheap fingerprint of everything moment detection depends on, so the
        page can skip a full rebuild when nothing relevant changed."""
        with self._lock:
            a = self._conn.execute(
                "SELECT COUNT(*) c, MAX(taken_at) m FROM photos WHERE missing=0").fetchone()
            b = self._conn.execute("SELECT COUNT(*) c FROM photo_players").fetchone()
        return (a["c"], a["m"], b["c"], tuple(sorted(self_names)))

    def sessions_stamp(self, self_names=()):
        """Cheap fingerprint of everything the session list is built from.

        The page tears down and rebuilds every card, every people chip and every
        thumbnail strip on each visit, which measured 93 ms on a library of 160
        sessions -- felt every single time you click Sessions, for a list that
        had not changed. The photo count is in here because deleting a shot
        changes a card's tally and its cover.
        """
        with self._lock:
            a = self._conn.execute(
                "SELECT COUNT(*) c, MAX(start_at) m FROM sessions").fetchone()
            b = self._conn.execute(
                "SELECT COUNT(*) c, MAX(id) m FROM photos"
                " WHERE session_id IS NOT NULL AND missing=0"
                " AND deleted_at IS NULL").fetchone()
            c = self._conn.execute(
                "SELECT COUNT(*) c FROM session_players").fetchone()
        return (a["c"], a["m"], b["c"], b["m"], c["c"], tuple(sorted(self_names)))

    def moment_rows(self):
        with self._lock:
            return self._conn.execute(
                "SELECT id, taken_at, day, world_name FROM photos "
                "WHERE missing=0 AND taken_at IS NOT NULL ORDER BY taken_at").fetchall()

    def players_by_photo(self, self_names=()):
        ex = ""
        params = []
        if self_names:
            ex = " WHERE name NOT IN (%s)" % ",".join("?" * len(self_names))
            params = list(self_names)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT photo_id, name FROM photo_players{ex}", params).fetchall()
        out = {}
        for r in rows:
            out.setdefault(r["photo_id"], []).append(r["name"])
        return out

    def storage_forecast(self):
        with self._lock:
            months = self._conn.execute(
                "SELECT substr(day,1,7) m, COALESCE(SUM(filesize),0) b, COUNT(*) c "
                "FROM photos WHERE missing=0 AND day IS NOT NULL "
                "GROUP BY m ORDER BY m").fetchall()
            png = self._conn.execute(
                "SELECT COUNT(*) c, COALESCE(SUM(filesize),0) b FROM photos "
                "WHERE missing=0 AND lower(path) LIKE '%.png'").fetchone()
        return {"months": months, "png_count": png["c"], "png_bytes": png["b"]}

    def photos_by_ids_full(self, ids):
        ids = [i for i in ids if i]
        if not ids:
            return []
        q = ",".join("?" * len(ids))
        with self._lock:
            return self._conn.execute(
                f"SELECT id, path, taken_at, day, world_id, world_name, favorite, width, "
                f"height, filesize, meta_source, mtime, avatar_name, session_id, "
                f"instance_type, rating, is_video "
                f"FROM photos WHERE id IN ({q}) ORDER BY taken_at",
                list(ids)).fetchall()

    def all_photo_paths(self):
        with self._lock:
            return self._conn.execute(
                "SELECT id, path, day, filesize FROM photos WHERE missing=0 "
                "ORDER BY taken_at").fetchall()

    # ---------- year in review ----------

    def years(self):
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT substr(day,1,4) y FROM photos "
                "WHERE missing=0 AND day IS NOT NULL ORDER BY y DESC").fetchall()
        return [int(r["y"]) for r in rows if (r["y"] or "").isdigit()]

    def year_photos(self, year):
        with self._lock:
            return self._conn.execute(
                "SELECT id, path, filesize, mtime, taken_at FROM photos "
                "WHERE missing=0 AND substr(day,1,4)=? ORDER BY taken_at",
                (str(year),)).fetchall()

    def year_active_days(self, year):
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT day FROM photos WHERE missing=0 AND substr(day,1,4)=?",
                (str(year),)).fetchall()
        return [r["day"] for r in rows]

    def year_world_ids(self, year):
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT world_id FROM photos "
                "WHERE missing=0 AND world_id IS NOT NULL AND substr(day,1,4)=?",
                (str(year),)).fetchall()
        return [r["world_id"] for r in rows]

    def year_top_worlds(self, year, limit=6):
        with self._lock:
            return self._conn.execute(
                """SELECT COALESCE(
                        (SELECT p2.world_name FROM photos p2 WHERE p2.world_id=p.world_id
                          AND p2.world_name IS NOT NULL ORDER BY p2.taken_at DESC LIMIT 1),
                        p.world_id) name, COUNT(*) c
                   FROM photos p
                   WHERE p.missing=0 AND p.world_id IS NOT NULL AND substr(p.day,1,4)=?
                   GROUP BY p.world_id ORDER BY c DESC LIMIT ?""",
                (str(year), limit)).fetchall()

    def year_top_people(self, year, limit=6, self_names=()):
        ex = ""
        params = [str(year)]
        if self_names:
            ex = " AND pp.name NOT IN (%s)" % ",".join("?" * len(self_names))
            params += list(self_names)
        params.append(limit)
        with self._lock:
            return self._conn.execute(
                f"""SELECT pp.name, COUNT(DISTINCT pp.photo_id) c
                    FROM photo_players pp JOIN photos p ON p.id=pp.photo_id
                    WHERE p.missing=0 AND substr(p.day,1,4)=?{ex}
                    GROUP BY pp.name ORDER BY c DESC LIMIT ?""", params).fetchall()

    def year_people_count(self, year, self_names=()):
        ex = ""
        params = [str(year)]
        if self_names:
            ex = " AND pp.name NOT IN (%s)" % ",".join("?" * len(self_names))
            params += list(self_names)
        with self._lock:
            r = self._conn.execute(
                f"SELECT COUNT(DISTINCT pp.name) c FROM photo_players pp "
                f"JOIN photos p ON p.id=pp.photo_id "
                f"WHERE p.missing=0 AND substr(p.day,1,4)=?{ex}", params).fetchone()
        return r["c"] if r else 0

    def year_top_avatars(self, year, limit=3):
        with self._lock:
            return self._conn.execute(
                "SELECT avatar_name name, COUNT(*) c FROM photos "
                "WHERE missing=0 AND substr(day,1,4)=? AND avatar_name IS NOT NULL "
                "AND avatar_name != '' GROUP BY avatar_name ORDER BY c DESC LIMIT ?",
                (str(year), limit)).fetchall()

    def year_best_candidates(self, year, limit=400):
        """Ranked pool for the poster; the caller thins it out for visual variety."""
        with self._lock:
            return self._conn.execute(
                """SELECT p.id, p.path, p.filesize, p.mtime, p.favorite, p.day,
                        p.dhash, p.world_id,
                        (SELECT COUNT(*) FROM photo_players pp WHERE pp.photo_id=p.id) np
                   FROM photos p
                   WHERE p.missing=0 AND p.is_video=0 AND substr(p.day,1,4)=?
                     AND (p.luma IS NULL OR p.luma > 18)
                   ORDER BY p.favorite DESC, np DESC, p.taken_at DESC LIMIT ?""",
                (str(year), limit)).fetchall()

    # ---------- cleanup ----------

    def unscanned(self, limit=0):
        sql = ("SELECT id, path, mtime, filesize FROM photos "
               "WHERE missing=0 AND scanned=0 AND is_video=0 ORDER BY taken_at DESC")
        if limit:
            sql += f" LIMIT {int(limit)}"
        with self._lock:
            return self._conn.execute(sql).fetchall()

    def black_photos(self, luma_max=8.0):
        with self._lock:
            return self._conn.execute(
                "SELECT id, path, taken_at, day, world_name, favorite, filesize, mtime "
                "FROM photos WHERE missing=0 AND scanned=1 AND luma IS NOT NULL AND luma<=? "
                "ORDER BY taken_at DESC", (luma_max,)).fetchall()

    def photos_time_ordered(self):
        # burst detection is about the camera being held down; a recording that
        # happens to start mid-burst is not part of it
        with self._lock:
            return self._conn.execute(
                "SELECT id, path, taken_at, day, world_name, favorite, filesize, mtime, "
                "dhash FROM photos WHERE missing=0 AND is_video=0 AND taken_at IS NOT NULL "
                "ORDER BY taken_at").fetchall()

    def largest(self, limit=200):
        with self._lock:
            return self._conn.execute(
                "SELECT id, path, taken_at, day, world_name, favorite, filesize, mtime "
                "FROM photos WHERE missing=0 AND is_video=0 "
                "ORDER BY filesize DESC LIMIT ?", (limit,)).fetchall()

    def photos_for_meta_reread(self):
        """(id, path) for every photo still on disk, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, path FROM photos WHERE missing=0 AND is_video=0"
                " ORDER BY id").fetchall()
        return [(r["id"], r["path"]) for r in rows]

    # ---------- meta kv ----------

    def get_meta(self, key, default=None):
        with self._lock:
            r = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def set_meta(self, key, value):
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
            self._conn.commit()
