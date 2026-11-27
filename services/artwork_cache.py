"""Artwork extraction cache for ISAI.

Stores embedded artwork as files in the user data directory. SQLite stores
only the resulting file path.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from services.library_database import default_artwork_dir


def _ext_for_mime(mime: str, data: bytes) -> str:
    mime = (mime or "").lower().strip()
    if "png" in mime:
        return ".png"
    if "jpeg" in mime or "jpg" in mime:
        return ".jpg"
    if "gif" in mime:
        return ".gif"
    if "bmp" in mime:
        return ".bmp"
    if "webp" in mime:
        return ".webp"
    # Sniff magic
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return ".gif"
    if data.startswith(b"BM"):
        return ".bmp"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return ".webp"
    return ".img"


class ArtworkCache:
    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir is not None else default_artwork_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def store(self, data: bytes, mime: str = "") -> str | None:
        """Store artwork bytes and return the cache file path, or None on failure."""
        if not isinstance(data, (bytes, bytearray)) or not data:
            return None
        try:
            payload = bytes(data)
            digest = hashlib.sha1(payload).hexdigest()
            ext = _ext_for_mime(mime, payload)
            path = self.cache_dir / f"{digest}{ext}"
            if not path.exists():
                tmp = path.with_suffix(path.suffix + ".tmp")
                tmp.write_bytes(payload)
                tmp.replace(path)
            return str(path)
        except Exception:
            return None

    def resolve(self, artwork_path: str | None) -> str | None:
        if not artwork_path:
            return None
        path = Path(artwork_path)
        try:
            if path.is_file():
                return str(path)
        except Exception:
            return None
        return None

    def cache_size_bytes(self) -> int:
        total = 0
        try:
            for p in self.cache_dir.iterdir():
                try:
                    if p.is_file():
                        total += p.stat().st_size
                except Exception:
                    continue
        except Exception:
            return 0
        return total

    def clear(self) -> tuple[int, int]:
        """Delete cached artwork files. Returns (files_deleted, bytes_freed)."""
        files = 0
        freed = 0
        try:
            for p in list(self.cache_dir.iterdir()):
                try:
                    if not p.is_file():
                        continue
                    size = p.stat().st_size
                    p.unlink()
                    files += 1
                    freed += size
                except Exception:
                    continue
        except Exception:
            pass
        return files, freed
