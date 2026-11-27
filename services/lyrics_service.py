"""Local/embedded lyrics parsing and lookup for ISAI.

Priority (documented, consistent):
1. Explicit user-selected .lrc file for the current track
2. Embedded synchronized lyrics (SYLT) from audio metadata
3. Local .lrc file next to the audio file
4. Embedded unsynchronized lyrics (USLT, lyrics-tam, LYRICS, ©lyr, etc.)
5. None -> empty state

This preserves existing .lrc support while preferring embedded lyrics when
available, especially when no synced .lrc exists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from services.metadata_reader import extract_embedded_lyrics

_TIMESTAMP_RE = re.compile(r"\[(\d{1,2}):(\d{2})(?:[\.:](\d{1,3}))?\]")
_META_RE = re.compile(r"^\[(ar|ti|al|by|offset):(.+)\]$", re.IGNORECASE)


@dataclass
class LyricLine:
    time_ms: int
    text: str


@dataclass
class LyricsData:
    lines: list[LyricLine] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)
    source_path: str | None = None
    source_type: str = "lrc"  # lrc | embedded-synced | embedded-text

    @property
    def has_timed_lines(self) -> bool:
        return any(l.time_ms >= 0 for l in self.lines)

    @property
    def is_synced(self) -> bool:
        return self.has_timed_lines


class LyricsService:
    """Parse and locate local .lrc files and embedded audio lyrics."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int, int, str | None], LyricsData | None] = {}
        self._cache_order: list[tuple[str, int, int, str | None]] = []
        self._cache_max = 128

    def _cache_key(self, audio_path: str | Path, explicit_lrc: str | Path | None) -> tuple[str, int, int, str | None] | None:
        try:
            p = Path(audio_path)
            st = p.stat()
            exp = str(Path(explicit_lrc).resolve()) if explicit_lrc else None
            return (str(p.resolve()), int(st.st_mtime_ns), int(st.st_size), exp)
        except Exception:
            return None

    def _cache_get(self, key):
        if key in self._cache:
            try:
                self._cache_order.remove(key)
            except ValueError:
                pass
            self._cache_order.append(key)
            return self._cache[key], True
        return None, False

    def _cache_set(self, key, value):
        self._cache[key] = value
        try:
            self._cache_order.remove(key)
        except ValueError:
            pass
        self._cache_order.append(key)
        while len(self._cache_order) > self._cache_max:
            old = self._cache_order.pop(0)
            self._cache.pop(old, None)

    def find_lyrics(self, audio_path: str | Path, explicit_lrc: str | Path | None = None) -> Path | None:
        if explicit_lrc:
            p = Path(explicit_lrc)
            if p.is_file() and p.suffix.lower() == ".lrc":
                return p
        audio = Path(audio_path)
        if not audio.name:
            return None
        candidate = audio.with_suffix(".lrc")
        if candidate.is_file():
            return candidate
        # Case-insensitive match in same directory
        try:
            parent = audio.parent
            if parent.is_dir():
                target = audio.stem.lower()
                for child in parent.iterdir():
                    if child.is_file() and child.suffix.lower() == ".lrc" and child.stem.lower() == target:
                        return child
        except Exception:
            pass
        return None

    def load_for_track(self, audio_path: str | Path, explicit_lrc: str | Path | None = None) -> LyricsData | None:
        key = self._cache_key(audio_path, explicit_lrc)
        if key is not None:
            cached, hit = self._cache_get(key)
            if hit:
                return cached

        result = self._load_for_track_uncached(audio_path, explicit_lrc=explicit_lrc)
        if key is not None:
            self._cache_set(key, result)
        return result

    def _load_for_track_uncached(self, audio_path: str | Path, explicit_lrc: str | Path | None = None) -> LyricsData | None:
        # 1) Explicit LRC selected by user
        if explicit_lrc:
            path = self.find_lyrics(audio_path, explicit_lrc=explicit_lrc)
            if path is not None:
                data = self.parse_file(path)
                if data and data.lines:
                    data.source_type = "lrc"
                    return data

        # 2) Embedded synchronized lyrics
        embedded = []
        try:
            embedded = extract_embedded_lyrics(audio_path)
        except Exception:
            embedded = []
        for cand in embedded:
            timed = cand.get("timed_lines")
            if timed:
                lines = [LyricLine(time_ms=max(0, int(t.get("time_ms", 0))), text=str(t.get("text", ""))) for t in timed]
                lines = [l for l in lines if l.text.strip()]
                lines.sort(key=lambda x: (x.time_ms, x.text))
                if lines:
                    return LyricsData(lines=lines, metadata={"source": str(cand.get("key", "embedded"))}, source_path=str(audio_path), source_type="embedded-synced")

        # 3) Local .lrc file
        path = self.find_lyrics(audio_path, explicit_lrc=None)
        if path is not None:
            data = self.parse_file(path)
            if data and data.lines:
                data.source_type = "lrc"
                return data

        # 4) Embedded unsynchronized lyrics
        for cand in embedded:
            text = str(cand.get("text", "") or "")
            if not text.strip():
                continue
            data = self.parse_plain_text(text, source_path=str(audio_path))
            if data and data.lines:
                data.source_type = "embedded-text"
                data.metadata = {"source": str(cand.get("key", "embedded"))}
                return data
        return None

    def parse_plain_text(self, text: str, source_path: str | None = None) -> LyricsData:
        lines: list[LyricLine] = []
        for raw in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            # preserve blank lines as spacing, but avoid leading/trailing noise
            line_text = raw.rstrip()
            lines.append(LyricLine(time_ms=-1, text=line_text))
        # trim leading/trailing fully empty lines
        while lines and not lines[0].text.strip():
            lines.pop(0)
        while lines and not lines[-1].text.strip():
            lines.pop()
        return LyricsData(lines=lines, metadata={}, source_path=source_path, source_type="embedded-text")

    def parse_file(self, path: str | Path) -> LyricsData | None:
        p = Path(path)
        try:
            raw = p.read_bytes()
        except Exception:
            return None
        # UTF-8 BOM / UTF-8 / fallback
        text = None
        for enc in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except Exception:
                continue
        if text is None:
            return None
        return self.parse_text(text, source_path=str(p))

    def parse_text(self, text: str, source_path: str | None = None) -> LyricsData:
        lines: list[LyricLine] = []
        metadata: dict[str, str] = {}
        for raw_line in text.splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            meta = _META_RE.match(raw_line)
            if meta:
                metadata[meta.group(1).lower()] = meta.group(2).strip()
                continue
            stamps = list(_TIMESTAMP_RE.finditer(raw_line))
            if not stamps:
                continue
            lyric_text = _TIMESTAMP_RE.sub("", raw_line).strip()
            for m in stamps:
                mm = int(m.group(1))
                ss = int(m.group(2))
                frac = m.group(3) or "0"
                if len(frac) == 1:
                    ms_frac = int(frac) * 100
                elif len(frac) == 2:
                    ms_frac = int(frac) * 10
                else:
                    ms_frac = int(frac[:3])
                total_ms = mm * 60_000 + ss * 1000 + ms_frac
                lines.append(LyricLine(time_ms=max(0, total_ms), text=lyric_text))
        lines.sort(key=lambda x: (x.time_ms, x.text))
        return LyricsData(lines=lines, metadata=metadata, source_path=source_path)

    @staticmethod
    def active_line_index(lines: list[LyricLine], position_ms: int) -> int:
        """Return index of active lyric line for position, or -1.

        Returns -1 for unsynchronized lyrics (all lines have time_ms < 0).
        """
        if not lines:
            return -1
        # Unsynchronized lyrics: no active timed line
        if all(line.time_ms < 0 for line in lines):
            return -1
        pos = max(0, int(position_ms))
        idx = -1
        for i, line in enumerate(lines):
            if line.time_ms < 0:
                continue
            if line.time_ms <= pos:
                idx = i
            else:
                break
        return idx
