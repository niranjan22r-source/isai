"""Background music library scanner for ISAI.

The worker is designed to run on a QThread. It discovers supported audio
files, extracts metadata, caches artwork, and upserts tracks into SQLite.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QObject, Signal

from services.artwork_cache import ArtworkCache
from services.library_database import LibraryDatabase, SUPPORTED_EXTENSIONS
from services.metadata_reader import extract_metadata, is_supported_audio_file


class MusicScannerWorker(QObject):
    progress = Signal(int, int, int, int, str)  # discovered, imported, skipped, failed, current
    finished = Signal(int, int, int, int, bool)  # discovered, imported, skipped, failed, cancelled
    error = Signal(str)

    def __init__(
        self,
        db_path: str | Path | None = None,
        artwork_dir: str | Path | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._db_path = str(db_path) if db_path is not None else None
        self._artwork_dir = str(artwork_dir) if artwork_dir is not None else None
        self._cancelled = False
        self._paths: list[str | Path] = []

    def set_paths(self, paths: Iterable[str | Path]) -> None:
        self._paths = list(paths)

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        self.scan(self._paths)

    def scan(self, paths: Iterable[str | Path]) -> None:
        discovered = imported = skipped = failed = 0
        self._cancelled = False
        try:
            db = LibraryDatabase(self._db_path)
            artwork_cache = ArtworkCache(self._artwork_dir)
            existing = self._existing_index(db)

            files = self._collect_files(paths)
            for file_path in files:
                if self._cancelled:
                    break
                discovered += 1
                current = str(file_path)
                try:
                    result = self._import_file(file_path, db, artwork_cache, existing)
                    if result == "imported":
                        imported += 1
                    else:
                        skipped += 1
                except Exception as exc:
                    failed += 1
                    self.error.emit(f"Failed to import {file_path.name}: {exc}")
                self.progress.emit(discovered, imported, skipped, failed, current)

            if self._cancelled:
                self.progress.emit(discovered, imported, skipped, failed, "")
        except Exception as exc:
            self.error.emit(f"Scan failed: {exc}")
        finally:
            self.finished.emit(discovered, imported, skipped, failed, self._cancelled)

    # ----------------------------------------------------------------- internals

    def _existing_index(self, db: LibraryDatabase) -> dict[str, tuple[int | None, int | None, str | None, str | None]]:
        try:
            return db.get_scan_index()
        except Exception:
            # fallback
            index: dict[str, tuple[int | None, int | None, str | None, str | None]] = {}
            try:
                for track in db.get_all_tracks("title"):
                    index[track.file_path] = (track.file_size, track.file_mtime_ns, track.date_added, track.artwork_path)
            except Exception:
                pass
            return index

    def _collect_files(self, paths: Iterable[str | Path]) -> list[Path]:
        found: list[Path] = []
        seen: set[str] = set()
        for raw in paths:
            if self._cancelled:
                break
            if raw is None:
                continue
            try:
                path = Path(raw).expanduser()
            except Exception:
                continue
            if path.is_dir():
                self._walk_dir(path, found, seen)
            elif path.is_file():
                self._add_file(path, found, seen)
        found.sort(key=lambda p: str(p).lower())
        return found

    def _walk_dir(self, directory: Path, found: list[Path], seen: set[str]) -> None:
        try:
            with os.scandir(directory) as entries:
                dirs = []
                files = []
                for entry in entries:
                    if self._cancelled:
                        return
                    name = entry.name
                    if name.startswith("."):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            dirs.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            files.append(Path(entry.path))
                    except Exception:
                        continue
                for file_path in sorted(files, key=lambda p: str(p).lower()):
                    if self._cancelled:
                        return
                    self._add_file(file_path, found, seen)
                for subdir in sorted(dirs, key=lambda p: str(p).lower()):
                    if self._cancelled:
                        return
                    self._walk_dir(subdir, found, seen)
        except Exception as exc:
            self.error.emit(f"Cannot scan folder {directory}: {exc}")

    def _add_file(self, path: Path, found: list[Path], seen: set[str]) -> None:
        try:
            resolved = path.resolve()
        except Exception:
            return
        key = str(resolved)
        if key in seen:
            return
        if resolved.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        seen.add(key)
        found.append(resolved)

    def _import_file(
        self,
        file_path: Path,
        db: LibraryDatabase,
        artwork_cache: ArtworkCache,
        existing: dict[str, tuple[int | None, int | None]],
    ) -> str:
        if not file_path.exists() or not file_path.is_file():
            raise FileNotFoundError("file does not exist")

        try:
            stat = file_path.stat()
            size = int(stat.st_size)
            mtime_ns = int(stat.st_mtime_ns)
        except Exception:
            size = None
            mtime_ns = None

        key = str(file_path)
        previous = existing.get(key)
        if previous is not None and previous[:2] == (size, mtime_ns):
            return "skipped"

        metadata = extract_metadata(file_path)
        # Keep original date_added/artwork for existing tracks without extra DB query.
        existing_date_added = previous[2] if previous is not None else None
        existing_artwork_path = previous[3] if previous is not None else None
        if existing_date_added:
            metadata["date_added"] = existing_date_added

        artwork_data = metadata.pop("artwork_data", None)
        artwork_mime = metadata.pop("artwork_mime", "")
        if isinstance(artwork_data, (bytes, bytearray)) and artwork_data:
            stored = artwork_cache.store(bytes(artwork_data), str(artwork_mime))
            if stored:
                metadata["artwork_path"] = stored
        elif existing_artwork_path:
            metadata["artwork_path"] = existing_artwork_path

        # Ensure file_mtime_ns is present for change detection.
        if metadata.get("file_mtime_ns") is None and mtime_ns is not None:
            metadata["file_mtime_ns"] = mtime_ns

        db.upsert_track(metadata)
        existing[key] = (metadata.get("file_size"), metadata.get("file_mtime_ns"))
        return "imported"
