"""SQLite-backed persistent music library for ISAI.

The database lives in the user application data directory, never inside the
source tree. All public methods use parameterized SQL and return plain data.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from PySide6.QtCore import QStandardPaths

APP_DATA_LOCATION = QStandardPaths.StandardLocation.AppDataLocation
DB_FILENAME = "library.db"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class TrackRecord:
    """A track row as stored in the library database."""

    id: int
    file_path: str
    title: str
    artist: str
    album: str
    album_artist: str
    track_number: int | None
    disc_number: int | None
    genre: str
    year: int | None
    duration: int
    format: str
    bitrate: int | None
    file_size: int
    file_mtime_ns: int | None
    date_added: str
    artwork_path: str | None
    last_played: str | None = None


@dataclass(frozen=True)
class PlaylistRecord:
    id: int
    name: str
    description: str
    date_created: str
    date_modified: str
    track_count: int = 0


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


TRACK_COLUMNS = """
    id, file_path, title, artist, album, album_artist, track_number,
    disc_number, genre, year, duration, format, bitrate, file_size,
    file_mtime_ns, date_added, artwork_path, last_played
"""
TRACK_COLUMNS_T = """
    t.id, t.file_path, t.title, t.artist, t.album, t.album_artist, t.track_number,
    t.disc_number, t.genre, t.year, t.duration, t.format, t.bitrate, t.file_size,
    t.file_mtime_ns, t.date_added, t.artwork_path, t.last_played
"""

TRACK_FIELDS = (
    "file_path",
    "title",
    "artist",
    "album",
    "album_artist",
    "track_number",
    "disc_number",
    "genre",
    "year",
    "duration",
    "format",
    "bitrate",
    "file_size",
    "file_mtime_ns",
    "date_added",
    "artwork_path",
)

SUPPORTED_EXTENSIONS = frozenset({".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"})


def default_data_dir() -> Path:
    """Return the per-user ISAI data directory, creating it if needed."""
    location = QStandardPaths.writableLocation(APP_DATA_LOCATION)
    if not location:
        location = str(Path.home() / ".local" / "share" / "ISAI")
    path = Path(location)
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_db_path() -> Path:
    return default_data_dir() / DB_FILENAME


def default_artwork_dir() -> Path:
    path = default_data_dir() / "artwork"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _row_to_track(row: sqlite3.Row) -> TrackRecord:
    keys = set(row.keys())
    return TrackRecord(
        id=int(row["id"]),
        file_path=str(row["file_path"]),
        title=str(row["title"]),
        artist=str(row["artist"]),
        album=str(row["album"]),
        album_artist=str(row["album_artist"]),
        track_number=row["track_number"],
        disc_number=row["disc_number"],
        genre=str(row["genre"] or ""),
        year=row["year"],
        duration=int(row["duration"] or 0),
        format=str(row["format"] or ""),
        bitrate=row["bitrate"],
        file_size=int(row["file_size"] or 0),
        file_mtime_ns=row["file_mtime_ns"] if "file_mtime_ns" in keys else None,
        date_added=str(row["date_added"]),
        artwork_path=row["artwork_path"],
        last_played=row["last_played"] if "last_played" in keys else None,
    )


class LibraryDatabase:
    """Small SQLite service for the ISAI music library."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _initialize(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    artist TEXT NOT NULL,
                    album TEXT NOT NULL,
                    album_artist TEXT NOT NULL,
                    track_number INTEGER,
                    disc_number INTEGER,
                    genre TEXT NOT NULL DEFAULT '',
                    year INTEGER,
                    duration INTEGER NOT NULL DEFAULT 0,
                    format TEXT NOT NULL DEFAULT '',
                    bitrate INTEGER,
                    file_size INTEGER NOT NULL DEFAULT 0,
                    file_mtime_ns INTEGER,
                    date_added TEXT NOT NULL,
                    artwork_path TEXT,
                    last_played TEXT
                )
                """
            )
            # Lightweight migration for existing databases.
            existing_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(tracks)").fetchall()
            }
            if "file_mtime_ns" not in existing_columns:
                conn.execute("ALTER TABLE tracks ADD COLUMN file_mtime_ns INTEGER")
            if "last_played" not in existing_columns:
                conn.execute("ALTER TABLE tracks ADD COLUMN last_played TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist COLLATE NOCASE)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album COLLATE NOCASE, album_artist COLLATE NOCASE)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tracks_title ON tracks(title COLLATE NOCASE)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tracks_date_added ON tracks(date_added DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tracks_last_played ON tracks(last_played DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    date_created TEXT NOT NULL,
                    date_modified TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id INTEGER NOT NULL,
                    track_id INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    date_added TEXT NOT NULL,
                    FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                    FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE,
                    UNIQUE(playlist_id, track_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS favorites (
                    track_id INTEGER PRIMARY KEY,
                    date_added TEXT NOT NULL,
                    FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_playlist_tracks_playlist_pos ON playlist_tracks(playlist_id, position)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_playlist_tracks_track ON playlist_tracks(track_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_favorites_date_added ON favorites(date_added DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS library_folders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL UNIQUE,
                    date_added TEXT NOT NULL,
                    last_scanned TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_library_folders_path ON library_folders(path)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queue_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    current_queue_index INTEGER NOT NULL DEFAULT -1,
                    current_position_ms INTEGER NOT NULL DEFAULT 0,
                    shuffle_enabled INTEGER NOT NULL DEFAULT 0,
                    repeat_mode TEXT NOT NULL DEFAULT 'off',
                    updated_at TEXT NOT NULL
                )
                """
            )
            qs_cols = {row["name"] for row in conn.execute("PRAGMA table_info(queue_state)").fetchall()}
            if "current_file_path" not in qs_cols:
                conn.execute("ALTER TABLE queue_state ADD COLUMN current_file_path TEXT")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS queue_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    queue_order INTEGER NOT NULL,
                    track_id INTEGER,
                    file_path TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    artist TEXT NOT NULL DEFAULT '',
                    album TEXT NOT NULL DEFAULT '',
                    duration INTEGER NOT NULL DEFAULT 0,
                    artwork_path TEXT,
                    FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE SET NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_queue_items_order ON queue_items(queue_order)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_info (
                    version INTEGER NOT NULL
                )
                """
            )
            row = conn.execute("SELECT version FROM schema_info LIMIT 1").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_info(version) VALUES (?)", (SCHEMA_VERSION,)
                )

    # ----------------------------------------------------------------- tracks

    def add_track(self, track: dict) -> int:
        with self.connect() as conn:
            cur = conn.execute(self._insert_sql(), self._track_values(track))
            return int(cur.lastrowid)

    def add_tracks(self, tracks: list[dict]) -> int:
        if not tracks:
            return 0
        with self.connect() as conn:
            conn.executemany(
                self._insert_sql(),
                [self._track_values(track) for track in tracks],
            )
            return len(tracks)

    def upsert_track(self, track: dict) -> None:
        with self.connect() as conn:
            conn.execute(self._upsert_sql(), self._track_values(track))

    def get_track(self, track_id: int) -> TrackRecord | None:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT {TRACK_COLUMNS} FROM tracks WHERE id = ?", (int(track_id),)
            ).fetchone()
        return _row_to_track(row) if row else None

    def get_track_by_path(self, file_path: str | Path) -> TrackRecord | None:
        path = str(Path(file_path))
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT {TRACK_COLUMNS} FROM tracks WHERE file_path = ?", (path,)
            ).fetchone()
        return _row_to_track(row) if row else None

    def get_scan_index(self) -> dict[str, tuple[int | None, int | None, str | None, str | None]]:
        """Lightweight index for scanner: path -> (file_size, file_mtime_ns, date_added, artwork_path)."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT file_path, file_size, file_mtime_ns, date_added, artwork_path FROM tracks"
            ).fetchall()
        index: dict[str, tuple[int | None, int | None, str | None, str | None]] = {}
        for row in rows:
            index[str(row["file_path"])] = (
                row["file_size"],
                row["file_mtime_ns"],
                row["date_added"],
                row["artwork_path"],
            )
        return index

    def get_all_tracks(
        self, order_by: str = "title", descending: bool = False
    ) -> list[TrackRecord]:
        order_sql = self._order_sql(order_by, descending=descending)
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT {TRACK_COLUMNS} FROM tracks {order_sql}"
            ).fetchall()
        return [_row_to_track(row) for row in rows]

    def search_tracks(
        self, query: str, order_by: str = "title", descending: bool = False
    ) -> list[TrackRecord]:
        needle = f"%{query.strip().lower()}%"
        order_sql = self._order_sql(order_by, descending=descending)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {TRACK_COLUMNS} FROM tracks
                WHERE lower(title) LIKE ?
                   OR lower(artist) LIKE ?
                   OR lower(album) LIKE ?
                   OR lower(genre) LIKE ?
                {order_sql}
                """,
                (needle, needle, needle, needle),
            ).fetchall()
        return [_row_to_track(row) for row in rows]

    def update_track(self, track_id: int, **fields) -> bool:
        allowed = set(TRACK_FIELDS) | {"last_played"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return False
        assignments = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [int(track_id)]
        with self.connect() as conn:
            cur = conn.execute(
                f"UPDATE tracks SET {assignments} WHERE id = ?", values
            )
            return cur.rowcount > 0

    def remove_track(self, track_id: int) -> bool:
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM tracks WHERE id = ?", (int(track_id),))
            return cur.rowcount > 0

    def remove_track_by_path(self, file_path: str | Path) -> bool:
        path = str(Path(file_path))
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM tracks WHERE file_path = ?", (path,))
            return cur.rowcount > 0

    def track_count(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM tracks").fetchone()
        return int(row["c"] if row else 0)

    def mark_played(self, file_path: str | Path, played_at: str) -> None:
        path = str(Path(file_path))
        with self.connect() as conn:
            conn.execute(
                "UPDATE tracks SET last_played = ? WHERE file_path = ?",
                (played_at, path),
            )

    # --------------------------------------------------------------- summaries

    def get_recently_added(self, limit: int = 20) -> list[TrackRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {TRACK_COLUMNS} FROM tracks
                ORDER BY datetime(date_added) DESC, id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [_row_to_track(row) for row in rows]

    def get_recently_played(self, limit: int = 20) -> list[TrackRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {TRACK_COLUMNS} FROM tracks
                WHERE last_played IS NOT NULL AND last_played != ''
                ORDER BY datetime(last_played) DESC, id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [_row_to_track(row) for row in rows]

    def get_albums(
        self, query: str = "", sort_by: str = "title", descending: bool = False
    ) -> list[dict]:
        where = ""
        params: list = []
        if query.strip():
            needle = f"%{query.strip().lower()}%"
            where = "WHERE lower(album) LIKE ? OR lower(album_artist) LIKE ?"
            params.extend([needle, needle])
        desc = "DESC" if descending else "ASC"
        order_map = {
            "title": f"album COLLATE NOCASE {desc}, album_artist COLLATE NOCASE ASC",
            "artist": f"album_artist COLLATE NOCASE {desc}, album COLLATE NOCASE ASC",
            "track_count": f"track_count {desc}, album COLLATE NOCASE ASC",
        }
        order = order_map.get(sort_by, order_map["title"])
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    album,
                    album_artist,
                    MIN(COALESCE(NULLIF(artwork_path, ''), NULL)) AS artwork_path,
                    COUNT(*) AS track_count,
                    MIN(year) AS year
                FROM tracks
                {where}
                GROUP BY album COLLATE NOCASE, album_artist COLLATE NOCASE
                ORDER BY {order}
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_artists(
        self, query: str = "", sort_by: str = "name", descending: bool = False
    ) -> list[dict]:
        where = ""
        params: list = []
        if query.strip():
            needle = f"%{query.strip().lower()}%"
            where = "WHERE lower(artist) LIKE ?"
            params.append(needle)
        desc = "DESC" if descending else "ASC"
        order_map = {
            "name": f"artist COLLATE NOCASE {desc}",
            "track_count": f"track_count {desc}, artist COLLATE NOCASE ASC",
            "album_count": f"album_count {desc}, artist COLLATE NOCASE ASC",
        }
        order = order_map.get(sort_by, order_map["name"])
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    artist,
                    COUNT(*) AS track_count,
                    COUNT(DISTINCT album COLLATE NOCASE) AS album_count
                FROM tracks
                {where}
                GROUP BY artist COLLATE NOCASE
                ORDER BY {order}
                """,
                params,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_album_tracks(self, album: str, album_artist: str) -> list[TrackRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {TRACK_COLUMNS} FROM tracks
                WHERE album = ? COLLATE NOCASE AND album_artist = ? COLLATE NOCASE
                ORDER BY COALESCE(disc_number, 1), COALESCE(track_number, 9999), title COLLATE NOCASE
                """,
                (album, album_artist),
            ).fetchall()
        return [_row_to_track(row) for row in rows]

    # ------------------------------------------------------------------- utils

    def has_file_path(self, file_path: str | Path) -> bool:
        return self.get_track_by_path(file_path) is not None

    def _insert_sql(self) -> str:
        columns = ", ".join(TRACK_FIELDS)
        placeholders = ", ".join("?" for _ in TRACK_FIELDS)
        return f"INSERT INTO tracks ({columns}) VALUES ({placeholders})"

    def _upsert_sql(self) -> str:
        columns = ", ".join(TRACK_FIELDS)
        placeholders = ", ".join("?" for _ in TRACK_FIELDS)
        updates = []
        for field in TRACK_FIELDS:
            if field == "file_path":
                continue
            if field == "date_added":
                updates.append(
                    "date_added=CASE "
                    "WHEN excluded.date_added IS NULL OR excluded.date_added = '' "
                    "THEN tracks.date_added ELSE excluded.date_added END"
                )
            else:
                updates.append(f"{field}=excluded.{field}")
        return (
            f"INSERT INTO tracks ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT(file_path) DO UPDATE SET {', '.join(updates)}"
        )

    @staticmethod
    def _track_values(track: dict) -> tuple:
        return tuple(track.get(field) for field in TRACK_FIELDS)

    @staticmethod
    def _order_sql(order_by: str, descending: bool = False) -> str:
        # Direction applies to the primary key; secondary keys keep a stable natural order.
        desc = "DESC" if descending else "ASC"
        asc = "ASC" if descending else "DESC"  # for recent/year inverted semantics
        mapping = {
            "title": f"ORDER BY title COLLATE NOCASE {desc}, artist COLLATE NOCASE ASC, album COLLATE NOCASE ASC",
            "artist": f"ORDER BY artist COLLATE NOCASE {desc}, album COLLATE NOCASE ASC, COALESCE(disc_number, 1) ASC, COALESCE(track_number, 9999) ASC, title COLLATE NOCASE ASC",
            "album": f"ORDER BY album COLLATE NOCASE {desc}, album_artist COLLATE NOCASE ASC, COALESCE(disc_number, 1) ASC, COALESCE(track_number, 9999) ASC, title COLLATE NOCASE ASC",
            "duration": f"ORDER BY duration {desc}, title COLLATE NOCASE ASC",
            "date_added": f"ORDER BY datetime(date_added) {desc}, id {desc}",
            "recent": f"ORDER BY datetime(date_added) {asc}, id {asc}",
            "year": f"ORDER BY COALESCE(year, 0) {asc}, title COLLATE NOCASE ASC",
        }
        return mapping.get(order_by, mapping["title"])

    # -------------------------------------------------------------- playlists

    def create_playlist(self, name: str, description: str = "") -> int:
        clean = (name or "").strip()
        if not clean:
            raise ValueError("Playlist name cannot be empty.")
        desc = (description or "").strip()
        now = utc_now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id FROM playlists WHERE lower(name) = lower(?) LIMIT 1",
                (clean,),
            ).fetchone()
            if existing is not None:
                raise ValueError("A playlist with that name already exists.")
            cur = conn.execute(
                """
                INSERT INTO playlists(name, description, date_created, date_modified)
                VALUES (?, ?, ?, ?)
                """,
                (clean, desc, now, now),
            )
            return int(cur.lastrowid)

    def rename_playlist(self, playlist_id: int, new_name: str) -> bool:
        clean = (new_name or "").strip()
        if not clean:
            raise ValueError("Playlist name cannot be empty.")
        pid = int(playlist_id)
        now = utc_now_iso()
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM playlists WHERE id = ?", (pid,)).fetchone()
            if row is None:
                return False
            dup = conn.execute(
                "SELECT id FROM playlists WHERE lower(name) = lower(?) AND id != ? LIMIT 1",
                (clean, pid),
            ).fetchone()
            if dup is not None:
                raise ValueError("A playlist with that name already exists.")
            conn.execute(
                "UPDATE playlists SET name = ?, date_modified = ? WHERE id = ?",
                (clean, now, pid),
            )
            return True

    def delete_playlist(self, playlist_id: int) -> bool:
        pid = int(playlist_id)
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM playlists WHERE id = ?", (pid,))
            return cur.rowcount > 0

    def get_playlist(self, playlist_id: int) -> PlaylistRecord | None:
        pid = int(playlist_id)
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT p.id, p.name, p.description, p.date_created, p.date_modified,
                       COUNT(pt.id) AS track_count
                FROM playlists p
                LEFT JOIN playlist_tracks pt ON pt.playlist_id = p.id
                WHERE p.id = ?
                GROUP BY p.id
                """,
                (pid,),
            ).fetchone()
        if row is None:
            return None
        return PlaylistRecord(
            id=int(row["id"]),
            name=str(row["name"]),
            description=str(row["description"] or ""),
            date_created=str(row["date_created"]),
            date_modified=str(row["date_modified"]),
            track_count=int(row["track_count"] or 0),
        )

    def get_playlists(self) -> list[PlaylistRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT p.id, p.name, p.description, p.date_created, p.date_modified,
                       COUNT(pt.id) AS track_count
                FROM playlists p
                LEFT JOIN playlist_tracks pt ON pt.playlist_id = p.id
                GROUP BY p.id
                ORDER BY lower(p.name) ASC, p.id ASC
                """
            ).fetchall()
        return [
            PlaylistRecord(
                id=int(r["id"]),
                name=str(r["name"]),
                description=str(r["description"] or ""),
                date_created=str(r["date_created"]),
                date_modified=str(r["date_modified"]),
                track_count=int(r["track_count"] or 0),
            )
            for r in rows
        ]

    def add_track_to_playlist(self, playlist_id: int, track_id: int) -> bool:
        pid, tid = int(playlist_id), int(track_id)
        now = utc_now_iso()
        with self.connect() as conn:
            p = conn.execute("SELECT id FROM playlists WHERE id = ?", (pid,)).fetchone()
            t = conn.execute("SELECT id FROM tracks WHERE id = ?", (tid,)).fetchone()
            if p is None or t is None:
                return False
            dup = conn.execute(
                "SELECT id FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
                (pid, tid),
            ).fetchone()
            if dup is not None:
                return False
            pos_row = conn.execute(
                "SELECT COALESCE(MAX(position), -1) AS max_pos FROM playlist_tracks WHERE playlist_id = ?",
                (pid,),
            ).fetchone()
            next_pos = int(pos_row["max_pos"] if pos_row else -1) + 1
            conn.execute(
                """
                INSERT INTO playlist_tracks(playlist_id, track_id, position, date_added)
                VALUES (?, ?, ?, ?)
                """,
                (pid, tid, next_pos, now),
            )
            conn.execute(
                "UPDATE playlists SET date_modified = ? WHERE id = ?",
                (now, pid),
            )
            return True

    def remove_track_from_playlist(self, playlist_id: int, track_id: int) -> bool:
        pid, tid = int(playlist_id), int(track_id)
        now = utc_now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM playlist_tracks WHERE playlist_id = ? AND track_id = ?",
                (pid, tid),
            )
            if cur.rowcount <= 0:
                return False
            rows = conn.execute(
                "SELECT id FROM playlist_tracks WHERE playlist_id = ? ORDER BY position ASC, id ASC",
                (pid,),
            ).fetchall()
            for idx, row in enumerate(rows):
                conn.execute(
                    "UPDATE playlist_tracks SET position = ? WHERE id = ?",
                    (idx, int(row["id"])),
                )
            conn.execute("UPDATE playlists SET date_modified = ? WHERE id = ?", (now, pid))
            return True

    def reorder_playlist_tracks(self, playlist_id: int, ordered_track_ids: list[int]) -> bool:
        pid = int(playlist_id)
        ordered = [int(tid) for tid in ordered_track_ids]
        if len(ordered) != len(set(ordered)):
            raise ValueError("Duplicate track IDs in playlist reorder.")
        now = utc_now_iso()
        with self.connect() as conn:
            p = conn.execute("SELECT id FROM playlists WHERE id = ?", (pid,)).fetchone()
            if p is None:
                return False
            existing_rows = conn.execute(
                "SELECT track_id FROM playlist_tracks WHERE playlist_id = ? ORDER BY position ASC, id ASC",
                (pid,),
            ).fetchall()
            existing = [int(r["track_id"]) for r in existing_rows]
            if sorted(existing) != sorted(ordered):
                raise ValueError("Reorder list must contain the same tracks as the playlist.")
            for idx, tid in enumerate(ordered):
                conn.execute(
                    "UPDATE playlist_tracks SET position = ? WHERE playlist_id = ? AND track_id = ?",
                    (idx, pid, tid),
                )
            conn.execute("UPDATE playlists SET date_modified = ? WHERE id = ?", (now, pid))
            return True

    def get_playlist_tracks(self, playlist_id: int) -> list[TrackRecord]:
        pid = int(playlist_id)
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {TRACK_COLUMNS_T}
                FROM playlist_tracks pt
                JOIN tracks t ON t.id = pt.track_id
                WHERE pt.playlist_id = ?
                ORDER BY pt.position ASC, pt.id ASC
                """,
                (pid,),
            ).fetchall()
        return [_row_to_track(r) for r in rows]

    # --------------------------------------------------------------- favorites

    def add_favorite(self, track_id: int) -> bool:
        tid = int(track_id)
        now = utc_now_iso()
        with self.connect() as conn:
            t = conn.execute("SELECT id FROM tracks WHERE id = ?", (tid,)).fetchone()
            if t is None:
                return False
            exists = conn.execute(
                "SELECT track_id FROM favorites WHERE track_id = ?", (tid,)
            ).fetchone()
            if exists is not None:
                return False
            conn.execute(
                "INSERT INTO favorites(track_id, date_added) VALUES (?, ?)",
                (tid, now),
            )
            return True

    def remove_favorite(self, track_id: int) -> bool:
        tid = int(track_id)
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM favorites WHERE track_id = ?", (tid,))
            return cur.rowcount > 0

    def is_favorite(self, track_id: int) -> bool:
        tid = int(track_id)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM favorites WHERE track_id = ? LIMIT 1", (tid,)
            ).fetchone()
        return row is not None

    def get_favorites(self) -> list[TrackRecord]:
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT {TRACK_COLUMNS_T}
                FROM favorites f
                JOIN tracks t ON t.id = f.track_id
                ORDER BY datetime(f.date_added) DESC, t.title COLLATE NOCASE ASC
                """
            ).fetchall()
        return [_row_to_track(r) for r in rows]

    def get_favorite_count(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM favorites").fetchone()
        return int(row["c"] if row else 0)

    def is_favorite_path(self, file_path: str | Path) -> bool:
        path = str(Path(file_path))
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM favorites f
                JOIN tracks t ON t.id = f.track_id
                WHERE t.file_path = ?
                LIMIT 1
                """,
                (path,),
            ).fetchone()
        return row is not None

    def toggle_favorite(self, track_id: int) -> bool:
        """Toggle favorite state; returns True if now favorite."""
        if self.is_favorite(track_id):
            self.remove_favorite(track_id)
            return False
        self.add_favorite(track_id)
        return True

    # ------------------------------------------------------------------- queue

    def save_queue_state(
        self,
        items: list[dict],
        current_queue_index: int,
        current_position_ms: int,
        shuffle_enabled: bool,
        repeat_mode: str,
        current_file_path: str | None = None,
    ) -> None:
        """Persist queue state atomically. items are dicts with queue_order, track_id, file_path, title, artist, album, duration, artwork_path."""
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute("DELETE FROM queue_items")
            if items:
                # Normalize track_id: keep only ids that exist.
                raw_ids = [it.get("track_id") for it in items if it.get("track_id") is not None]
                valid_ids = set()
                if raw_ids:
                    placeholders = ",".join("?" for _ in raw_ids)
                    rows = conn.execute(
                        f"SELECT id FROM tracks WHERE id IN ({placeholders})",
                        [int(x) for x in raw_ids],
                    ).fetchall()
                    valid_ids = {int(r["id"]) for r in rows}
                conn.executemany(
                    """
                    INSERT INTO queue_items
                        (queue_order, track_id, file_path, title, artist, album, duration, artwork_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            int(it.get("queue_order", i)),
                            int(it["track_id"]) if it.get("track_id") is not None and int(it["track_id"]) in valid_ids else None,
                            str(it.get("file_path", "")),
                            str(it.get("title", "") or ""),
                            str(it.get("artist", "") or ""),
                            str(it.get("album", "") or ""),
                            int(it.get("duration", 0) or 0),
                            it.get("artwork_path"),
                        )
                        for i, it in enumerate(items)
                    ],
                )
            conn.execute(
                """
                INSERT INTO queue_state (id, current_queue_index, current_position_ms, shuffle_enabled, repeat_mode, updated_at, current_file_path)
                VALUES (1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    current_queue_index=excluded.current_queue_index,
                    current_position_ms=excluded.current_position_ms,
                    shuffle_enabled=excluded.shuffle_enabled,
                    repeat_mode=excluded.repeat_mode,
                    updated_at=excluded.updated_at,
                    current_file_path=excluded.current_file_path
                """,
                (
                    int(current_queue_index),
                    max(0, int(current_position_ms)),
                    1 if shuffle_enabled else 0,
                    str(repeat_mode or "off"),
                    now,
                    str(current_file_path) if current_file_path else None,
                ),
            )

    def load_queue_state(self) -> dict | None:
        with self.connect() as conn:
            state = conn.execute(
                "SELECT current_queue_index, current_position_ms, shuffle_enabled, repeat_mode, current_file_path FROM queue_state WHERE id = 1"
            ).fetchone()
            if state is None:
                return None
            rows = conn.execute(
                """
                SELECT queue_order, track_id, file_path, title, artist, album, duration, artwork_path
                FROM queue_items
                ORDER BY queue_order ASC, id ASC
                """
            ).fetchall()
        items = []
        for r in rows:
            file_path = str(r["file_path"] or "")
            if not file_path:
                continue
            if not Path(file_path).exists():
                continue
            items.append(
                {
                    "queue_order": int(r["queue_order"]),
                    "track_id": r["track_id"],
                    "file_path": file_path,
                    "title": str(r["title"] or ""),
                    "artist": str(r["artist"] or ""),
                    "album": str(r["album"] or ""),
                    "duration": int(r["duration"] or 0),
                    "artwork_path": r["artwork_path"],
                }
            )
        current_index = int(state["current_queue_index"])
        current_file_path = state["current_file_path"] if "current_file_path" in state.keys() else None
        if current_file_path:
            for i, it in enumerate(items):
                if it["file_path"] == str(current_file_path):
                    current_index = i
                    break
        if items:
            current_index = max(0, min(current_index, len(items) - 1))
        else:
            current_index = -1
        return {
            "current_queue_index": current_index,
            "current_position_ms": max(0, int(state["current_position_ms"])),
            "shuffle_enabled": bool(state["shuffle_enabled"]),
            "repeat_mode": str(state["repeat_mode"] or "off"),
            "current_file_path": str(current_file_path) if current_file_path else None,
            "items": items,
        }

    # --------------------------------------------------------- library folders

    def add_library_folder(self, path: str | Path) -> bool:
        folder = str(Path(path).expanduser())
        now = utc_now_iso()
        with self.connect() as conn:
            exists = conn.execute(
                "SELECT id FROM library_folders WHERE path = ? LIMIT 1", (folder,)
            ).fetchone()
            if exists is not None:
                return False
            conn.execute(
                "INSERT INTO library_folders(path, date_added, last_scanned) VALUES (?, ?, ?)",
                (folder, now, None),
            )
            return True

    def remove_library_folder(self, path: str | Path) -> bool:
        folder = str(Path(path).expanduser())
        with self.connect() as conn:
            cur = conn.execute("DELETE FROM library_folders WHERE path = ?", (folder,))
            return cur.rowcount > 0

    def get_library_folders(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT path FROM library_folders ORDER BY path COLLATE NOCASE ASC"
            ).fetchall()
        return [str(r["path"]) for r in rows]

    def mark_library_folder_scanned(self, path: str | Path, scanned_at: str | None = None) -> None:
        folder = str(Path(path).expanduser())
        ts = scanned_at or utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                "UPDATE library_folders SET last_scanned = ? WHERE path = ?",
                (ts, folder),
            )

    # ----------------------------------------------------------- library stats

    def get_library_stats(self) -> dict:
        with self.connect() as conn:
            tracks = conn.execute("SELECT COUNT(*) AS c FROM tracks").fetchone()
            albums = conn.execute(
                "SELECT COUNT(*) AS c FROM (SELECT 1 FROM tracks GROUP BY album COLLATE NOCASE, album_artist COLLATE NOCASE)"
            ).fetchone()
            artists = conn.execute(
                "SELECT COUNT(*) AS c FROM (SELECT 1 FROM tracks GROUP BY artist COLLATE NOCASE)"
            ).fetchone()
            playlists = conn.execute("SELECT COUNT(*) AS c FROM playlists").fetchone()
            favorites = conn.execute("SELECT COUNT(*) AS c FROM favorites").fetchone()
        return {
            "tracks": int(tracks["c"] if tracks else 0),
            "albums": int(albums["c"] if albums else 0),
            "artists": int(artists["c"] if artists else 0),
            "playlists": int(playlists["c"] if playlists else 0),
            "favorites": int(favorites["c"] if favorites else 0),
        }

    def database_file_size(self) -> int:
        try:
            return self.db_path.stat().st_size if self.db_path.exists() else 0
        except Exception:
            return 0
