"""Audio metadata extraction using Mutagen.

This module is separate from UI and database layers. It returns plain dicts
and never raises for normal bad-file cases; callers get safe fallbacks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mutagen
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4

from services.library_database import SUPPORTED_EXTENSIONS

UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_ALBUM = "Unknown Album"


def is_supported_audio_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def _first_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _first_text(item)
            if text:
                return text
        return ""
    # Mutagen ID3 frames often have .text
    text_attr = getattr(value, "text", None)
    if text_attr is not None:
        return _first_text(text_attr)
    text = str(value).strip()
    # MP4/freeform bytes
    if isinstance(value, (bytes, bytearray)):
        try:
            text = bytes(value).decode("utf-8", errors="ignore").strip()
        except Exception:
            text = ""
    return "" if text in {"", "None"} else text


def _first_int(value: Any) -> int | None:
    text = _first_text(value)
    if not text:
        return None
    # Handle "1/12", "2024-01-01", etc.
    cleaned = ""
    for ch in text:
        if ch.isdigit() or (ch == "-" and not cleaned):
            cleaned += ch
        elif cleaned:
            break
    if not cleaned or cleaned == "-":
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _tag_get(tags: Any, *keys: str) -> str:
    if tags is None:
        return ""
    for key in keys:
        try:
            value = tags.get(key)
        except Exception:
            value = None
        if value is None:
            # ID3 uses frame objects; dict-like access may differ
            try:
                value = tags[key]
            except Exception:
                value = None
        text = _first_text(value)
        if text:
            return text
    return ""


def _parse_year(text: str) -> int | None:
    if not text:
        return None
    for token in (text[:4], text):
        num = _first_int(token)
        if num is not None and 1000 <= num <= 9999:
            return num
    return None


def _read_id3(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        tags = ID3(path)
    except Exception:
        return result
    result["title"] = _tag_get(tags, "TIT2")
    result["artist"] = _tag_get(tags, "TPE1")
    result["album"] = _tag_get(tags, "TALB")
    result["album_artist"] = _tag_get(tags, "TPE2")
    result["genre"] = _tag_get(tags, "TCON")
    result["track_number"] = _first_int(_tag_get(tags, "TRCK"))
    result["disc_number"] = _first_int(_tag_get(tags, "TPOS"))
    result["year"] = _parse_year(_tag_get(tags, "TDRC", "TYER", "TDAT"))
    # Artwork
    for key in tags.keys():
        if key.startswith("APIC"):
            try:
                frame = tags.get(key)
                if frame is not None and getattr(frame, "data", None):
                    result["artwork_data"] = bytes(frame.data)
                    result["artwork_mime"] = str(getattr(frame, "mime", "") or "")
                    break
            except Exception:
                continue
    return result


def _read_mp4(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        audio = MP4(path)
    except Exception:
        return result
    tags = audio.tags or {}
    result["title"] = _tag_get(tags, "\xa9nam")
    result["artist"] = _tag_get(tags, "\xa9ART")
    result["album"] = _tag_get(tags, "\xa9alb")
    result["album_artist"] = _tag_get(tags, "aART")
    result["genre"] = _tag_get(tags, "\xa9gen")
    trkn = tags.get("trkn")
    if trkn:
        try:
            result["track_number"] = int(trkn[0][0]) or None
        except Exception:
            pass
    disk = tags.get("disk")
    if disk:
        try:
            result["disc_number"] = int(disk[0][0]) or None
        except Exception:
            pass
    result["year"] = _parse_year(_tag_get(tags, "\xa9day"))
    covr = tags.get("covr")
    if covr:
        try:
            cover = covr[0]
            result["artwork_data"] = bytes(cover)
            # MP4Cover: 13=JPEG, 14=PNG
            fmt = getattr(cover, "imageformat", None)
            result["artwork_mime"] = "image/png" if fmt == 14 else "image/jpeg"
        except Exception:
            pass
    result["_audio"] = audio
    return result


def _read_vorbis_like(tags: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    result["title"] = _tag_get(tags, "title")
    result["artist"] = _tag_get(tags, "artist")
    result["album"] = _tag_get(tags, "album")
    result["album_artist"] = _tag_get(tags, "albumartist", "album artist")
    result["genre"] = _tag_get(tags, "genre")
    result["track_number"] = _first_int(_tag_get(tags, "tracknumber", "track"))
    result["disc_number"] = _first_int(_tag_get(tags, "discnumber", "disc"))
    result["year"] = _parse_year(_tag_get(tags, "date", "year"))
    return result


def _read_flac_artwork(audio: FLAC) -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        if audio.pictures:
            pic = audio.pictures[0]
            if pic.data:
                result["artwork_data"] = bytes(pic.data)
                result["artwork_mime"] = str(pic.mime or "")
    except Exception:
        pass
    return result


def _normalize_lyrics_text(text: str) -> str:
    if not text:
        return ""
    # Preserve line breaks and Tamil/Unicode; normalize newlines only.
    t = str(text).replace("\r\n", "\n").replace("\r", "\n")
    # Strip BOM and nulls
    t = t.replace("\ufeff", "").replace("\x00", "")
    # Trim outer whitespace but preserve internal blank lines.
    return t.strip("\n")


def _extract_id3_lyrics(tags) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    try:
        for key in tags.keys():
            try:
                frame = tags.get(key)
            except Exception:
                continue
            if frame is None:
                continue
            upper = str(key).upper()
            # Unsynchronized lyrics
            if upper.startswith("USLT"):
                text = _normalize_lyrics_text(_first_text(getattr(frame, "text", None) or getattr(frame, "lyrics", None) or frame))
                if text:
                    found.append({
                        "text": text,
                        "lang": str(getattr(frame, "lang", "") or ""),
                        "desc": str(getattr(frame, "desc", "") or ""),
                        "type": "uslt",
                        "key": str(key),
                    })
            # Synchronized lyrics
            elif upper.startswith("SYLT"):
                try:
                    # SYLT.text is list of (text, time_ms)
                    entries = getattr(frame, "text", []) or []
                    timed = []
                    for entry in entries:
                        if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                            txt = _normalize_lyrics_text(str(entry[0]))
                            try:
                                ms = int(entry[1])
                            except Exception:
                                ms = 0
                            if txt:
                                timed.append({"time_ms": max(0, ms), "text": txt})
                    if timed:
                        found.append({
                            "timed_lines": timed,
                            "lang": str(getattr(frame, "lang", "") or ""),
                            "desc": str(getattr(frame, "desc", "") or ""),
                            "type": "sylt",
                            "key": str(key),
                        })
                except Exception:
                    pass
            # TXXX frames may contain custom lyrics like lyrics-tam
            elif upper.startswith("TXXX"):
                desc = str(getattr(frame, "desc", "") or "")
                if "lyric" in desc.lower():
                    text = _normalize_lyrics_text(_first_text(getattr(frame, "text", None) or frame))
                    if text:
                        found.append({
                            "text": text,
                            "lang": "",
                            "desc": desc,
                            "type": "txxx",
                            "key": str(key),
                        })
    except Exception:
        pass
    return found


def extract_embedded_lyrics(path: str | Path) -> list[dict[str, Any]]:
    """Return embedded lyrics candidates from an audio file.

    Each candidate is a dict with either `text` (unsynchronized) or
    `timed_lines` (synchronized). Never raises on normal bad files.
    """
    file_path = Path(path)
    candidates: list[dict[str, Any]] = []
    try:
        suffix = file_path.suffix.lower()
        if suffix == ".mp3":
            try:
                tags = ID3(file_path)
            except Exception:
                tags = None
            if tags is not None:
                candidates.extend(_extract_id3_lyrics(tags))
                # Also look for freeform/non-standard fields exposed by mutagen mapping
                try:
                    for key in tags.keys():
                        k = str(key)
                        if k.upper().startswith(("USLT", "SYLT", "TXXX")):
                            continue
                        if "lyric" in k.lower():
                            text = _normalize_lyrics_text(_first_text(tags.get(key)))
                            if text:
                                candidates.append({"text": text, "lang": "", "desc": k, "type": "id3", "key": k})
                except Exception:
                    pass
        else:
            audio = None
            try:
                audio = mutagen.File(file_path)
            except Exception:
                audio = None
            if audio is not None:
                tags = getattr(audio, "tags", None)
                if tags is not None:
                    # Common tag names across Vorbis/FLAC/MP4/WAV/AIFF
                    keys_to_check = []
                    try:
                        if hasattr(tags, "keys"):
                            keys_to_check = list(tags.keys())
                    except Exception:
                        keys_to_check = []
                    # MP4 lyrics atom
                    try:
                        if isinstance(audio, MP4):
                            lyr = tags.get("©lyr")
                            text = _normalize_lyrics_text(_first_text(lyr))
                            if text:
                                candidates.append({"text": text, "lang": "", "desc": "©lyr", "type": "mp4", "key": "©lyr"})
                    except Exception:
                        pass
                    for key in keys_to_check:
                        try:
                            k = str(key)
                            kl = k.lower()
                            if "lyric" in kl or kl in {"uslt", "sylt", "lyrics-tam"}:
                                if isinstance(audio, MP4) and k == "©lyr":
                                    continue
                                text = _normalize_lyrics_text(_first_text(tags.get(key)))
                                if text:
                                    candidates.append({"text": text, "lang": "", "desc": k, "type": "tag", "key": k})
                        except Exception:
                            continue
    except Exception:
        return candidates
    # Deduplicate by normalized text/timed content
    seen = set()
    unique = []
    for c in candidates:
        if "timed_lines" in c:
            sig = ("timed", tuple((l.get("time_ms"), l.get("text")) for l in c.get("timed_lines", [])))
        else:
            sig = ("text", c.get("text", ""))
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(c)
    return unique


def extract_metadata(path: str | Path) -> dict[str, Any]:
    """Extract normalized metadata for a local audio file.

    Returns a dict ready for LibraryDatabase (plus optional artwork_data/mime
    for cache handling by caller). Never raises on malformed files.
    """
    file_path = Path(path)
    now = datetime.now(timezone.utc).isoformat()
    data: dict[str, Any] = {
        "file_path": str(file_path),
        "title": file_path.stem or file_path.name,
        "artist": UNKNOWN_ARTIST,
        "album": UNKNOWN_ALBUM,
        "album_artist": "",
        "track_number": None,
        "disc_number": None,
        "genre": "",
        "year": None,
        "duration": 0,
        "format": file_path.suffix.lower().lstrip("."),
        "bitrate": None,
        "file_size": 0,
        "file_mtime_ns": None,
        "date_added": now,
        "artwork_path": None,
    }

    try:
        stat = file_path.stat()
        data["file_size"] = int(stat.st_size)
        data["file_mtime_ns"] = int(stat.st_mtime_ns)
    except Exception:
        data["file_mtime_ns"] = None

    audio = None
    try:
        audio = mutagen.File(file_path)
    except Exception:
        audio = None

    if audio is None:
        # Still return fallback metadata for supported extension.
        data["album_artist"] = data["artist"]
        return data

    try:
        info = getattr(audio, "info", None)
        if info is not None:
            length = getattr(info, "length", None)
            if length is not None:
                data["duration"] = max(0, int(float(length) * 1000))
            bitrate = getattr(info, "bitrate", None)
            if bitrate:
                data["bitrate"] = int(bitrate)
    except Exception:
        pass

    tags: dict[str, Any] = {}
    try:
        suffix = file_path.suffix.lower()
        if suffix == ".mp3":
            tags = _read_id3(file_path)
        elif suffix in {".m4a", ".aac", ".mp4"}:
            tags = _read_mp4(file_path)
        elif suffix == ".flac":
            try:
                flac = audio if isinstance(audio, FLAC) else FLAC(file_path)
                tags = _read_vorbis_like(flac.tags)
                tags.update(_read_flac_artwork(flac))
            except Exception:
                tags = _read_vorbis_like(getattr(audio, "tags", None))
        else:
            # OGG, WAV (rare tags), etc.
            tags = _read_vorbis_like(getattr(audio, "tags", None))
            if hasattr(audio, "pictures") and audio.pictures:
                try:
                    pic = audio.pictures[0]
                    tags["artwork_data"] = bytes(pic.data)
                    tags["artwork_mime"] = str(getattr(pic, "mime", ""))
                except Exception:
                    pass
    except Exception:
        tags = {}

    for key in ("title", "artist", "album", "album_artist", "genre"):
        value = str(tags.get(key) or "").strip()
        if value:
            data[key] = value
    for key in ("track_number", "disc_number", "year"):
        value = tags.get(key)
        if value is not None:
            data[key] = value

    if not data.get("album_artist"):
        data["album_artist"] = data["artist"]
    if not data.get("artist"):
        data["artist"] = UNKNOWN_ARTIST
    if not data.get("album"):
        data["album"] = UNKNOWN_ALBUM

    artwork_data = tags.get("artwork_data")
    artwork_mime = tags.get("artwork_mime")
    if isinstance(artwork_data, (bytes, bytearray)) and artwork_data:
        data["artwork_data"] = bytes(artwork_data)
        data["artwork_mime"] = str(artwork_mime or "")

    return data
