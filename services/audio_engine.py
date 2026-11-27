"""Real audio playback service built on Qt Multimedia.

AudioEngine owns QMediaPlayer/QAudioOutput and is the only playback component.
It can operate with an internal simple queue or an external QueueManager.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import time

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import (
    QAudioOutput,
    QMediaDevices,
    QMediaMetaData,
    QMediaPlayer,
)

from services.equalizer import BAND_FREQUENCIES, EqualizerService
from services.eq_audio_pipeline import EqAudioPipeline

from services.queue_manager import QueueManager, REPEAT_ONE

STATE_STOPPED = "stopped"
STATE_PLAYING = "playing"
STATE_PAUSED = "paused"

SUPPORTED_EXTENSIONS = frozenset({".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"})
AUDIO_FILE_FILTER = (
    "Audio files (*.mp3 *.wav *.flac *.ogg *.m4a *.aac);;All files (*)"
)
DEFAULT_VOLUME = 70


@dataclass(frozen=True)
class TrackInfo:
    """Display information for a track, with a filename-based fallback."""

    path: Path
    title: str
    artist: str

    @classmethod
    def from_path(cls, path: Path) -> "TrackInfo":
        return cls(path=path, title=path.stem or path.name, artist="Unknown artist")


def _meta_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


class AudioEngine(QObject):
    """Playback facade around QMediaPlayer with queue support."""

    state_changed = Signal(str)
    position_changed = Signal(int)
    duration_changed = Signal(int)
    track_changed = Signal(object)  # TrackInfo | None
    queue_changed = Signal()
    volume_changed = Signal(int)
    muted_changed = Signal(bool)
    error_occurred = Signal(str)
    seeked = Signal(int)

    def __init__(self, parent: QObject | None = None, queue_manager: QueueManager | None = None, eq_service: EqualizerService | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._eq_service = eq_service
        self._eq_pipeline: EqAudioPipeline | None = None
        self._use_eq_pipeline = eq_service is not None

        self._queue = queue_manager or QueueManager(self)
        self._owns_queue = queue_manager is None
        self._current_track: TrackInfo | None = None
        self._state = STATE_STOPPED
        self._position = 0
        self._duration = 0
        self._volume = DEFAULT_VOLUME
        self._muted = False
        self._error_reported = False
        self._loading = False
        self._pending_autoplay: bool | None = None
        self._seek_offset_ms = 0
        # Transition controller
        self._transition_gain = 1.0
        self._transition_state = "idle"  # idle|fading_out|fading_in
        self._transition_target = None  # queue item
        self._transition_autoplay = True
        self._transition_step_ms = 20
        self._transition_timer = QTimer(self)
        self._transition_timer.setInterval(self._transition_step_ms)
        self._transition_timer.timeout.connect(self._on_transition_tick)
        self._transition_started = 0.0
        self._transition_duration = 200
        self._transition_from = 1.0
        self._transition_to = 1.0
        self._transition_request_id = 0
        self._transition_suppress_queue_load = False
        self._pending_load_id = 0

        if self._use_eq_pipeline:
            self._eq_pipeline = EqAudioPipeline(self)
            self._player.setAudioBufferOutput(self._eq_pipeline.buffer_output)
            # No direct QAudioOutput; sound goes through EQ pipeline -> QAudioSink
            self._eq_pipeline.set_decode_callbacks(self._pause_decode_for_backpressure, self._resume_decode_for_backpressure)
            self._eq_pipeline.set_volume(self._volume / 100.0)
            self._eq_pipeline.set_muted(self._muted)
            self._sync_eq_pipeline()
            if self._eq_service is not None:
                try:
                    self._eq_service.state_changed.connect(self._sync_eq_pipeline)
                except Exception:
                    pass
            self._pos_timer = QTimer(self)
            self._pos_timer.setInterval(100)
            self._pos_timer.timeout.connect(self._emit_pipeline_position)
            self._pos_timer.start()
        else:
            self._player.setAudioOutput(self._audio_output)
            self._audio_output.setVolume(self._volume / 100.0)

        self._player.playbackStateChanged.connect(self._on_playback_state_changed)
        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.metaDataChanged.connect(self._on_metadata_changed)
        self._player.mediaStatusChanged.connect(self._on_media_status_changed)
        self._player.errorOccurred.connect(self._on_player_error)

        self._queue.queue_changed.connect(self.queue_changed)
        self._queue.current_changed.connect(self._on_queue_current_changed)

    # ------------------------------------------------------------------ state

    @property
    def queue_manager(self) -> QueueManager:
        return self._queue

    @property
    def current_track(self) -> TrackInfo | None:
        return self._current_track

    @property
    def tracks(self) -> tuple[Path, ...]:
        return tuple(item.path for item in self._queue.items)

    @property
    def current_index(self) -> int:
        return self._queue.current_index

    @property
    def playback_state(self) -> str:
        return self._state

    @property
    def position(self) -> int:
        return self._position

    @property
    def duration(self) -> int:
        return self._duration

    @property
    def volume(self) -> int:
        return self._volume

    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def is_playing(self) -> bool:
        return self._state == STATE_PLAYING

    @property
    def audio_output_available(self) -> bool:
        return bool(QMediaDevices.audioOutputs())

    # --------------------------------------------------------------- equalizer

    def _sync_eq_pipeline(self) -> None:
        if self._eq_pipeline is None or self._eq_service is None:
            return
        st = self._eq_service.state
        self._eq_pipeline.set_enabled(bool(st.enabled))
        self._eq_pipeline.configure(list(st.bands), list(BAND_FREQUENCIES), float(st.preamp_db), [1.0] * 10, 44100)

    def _pause_decode_for_backpressure(self) -> None:
        if self._state == STATE_PLAYING:
            try:
                self._player.pause()
            except Exception:
                pass

    def _resume_decode_for_backpressure(self) -> None:
        if self._state == STATE_PLAYING:
            try:
                self._player.play()
            except Exception:
                pass

    def _emit_pipeline_position(self) -> None:
        if not self._use_eq_pipeline or self._eq_pipeline is None:
            return
        if self._state != STATE_PLAYING and self._state != STATE_PAUSED:
            return
        pos = self._seek_offset_ms + (self._eq_pipeline.processed_us() // 1000)
        if self._duration > 0:
            pos = min(pos, self._duration)
        if pos < 0:
            pos = 0
        if pos != self._position:
            self._position = int(pos)
            self.position_changed.emit(self._position)

    # --------------------------------------------------------------- transitions

    def _set_transition_gain(self, gain: float) -> None:
        self._transition_gain = max(0.0, min(1.0, float(gain)))
        if self._eq_pipeline is not None:
            self._eq_pipeline.set_transition_gain(self._transition_gain)
        else:
            # QAudioOutput path: apply master*transition
            vol = 0.0 if self._muted else (self._volume / 100.0) * self._transition_gain
            try:
                self._audio_output.setVolume(vol)
            except Exception:
                pass

    def _cancel_transition(self, restore_gain: bool = True) -> None:
        self._transition_timer.stop()
        self._transition_state = "idle"
        self._transition_target = None
        self._transition_request_id += 1
        self._pending_load_id += 1
        if restore_gain:
            self._set_transition_gain(1.0)

    def _begin_fade(self, to_gain: float, duration_ms: int, state: str) -> None:
        self._transition_state = state
        self._transition_from = self._transition_gain
        self._transition_to = max(0.0, min(1.0, float(to_gain)))
        self._transition_duration = max(1, int(duration_ms))
        self._transition_started = time.monotonic()
        if not self._transition_timer.isActive():
            self._transition_timer.start()

    def _on_transition_tick(self) -> None:
        elapsed_ms = (time.monotonic() - self._transition_started) * 1000.0
        t = min(1.0, elapsed_ms / float(self._transition_duration))
        # smoothstep
        t = t * t * (3.0 - 2.0 * t)
        gain = self._transition_from + (self._transition_to - self._transition_from) * t
        self._set_transition_gain(gain)
        if elapsed_ms >= self._transition_duration:
            self._transition_timer.stop()
            if self._transition_state == "fading_out":
                self._complete_fade_out()
            elif self._transition_state == "fading_in":
                self._transition_state = "idle"
                self._set_transition_gain(1.0)

    def _request_track_transition(self, item, autoplay: bool) -> bool:
        if item is None:
            return False
        # Paused/stopped: switch immediately, no fade-out needed.
        if self._state != STATE_PLAYING:
            self._cancel_transition(restore_gain=True)
            return self._load_item(item, autoplay=autoplay)
        # If already fading out, just replace target (latest wins).
        if self._transition_state == "fading_out":
            self._transition_target = item
            self._transition_autoplay = bool(autoplay)
            return True
        # If fading in or idle while playing, fade out from current gain.
        self._transition_target = item
        self._transition_autoplay = bool(autoplay)
        self._begin_fade(0.0, 200, "fading_out")
        return True

    def _complete_fade_out(self) -> None:
        item = self._transition_target
        autoplay = self._transition_autoplay
        self._transition_target = None
        self._transition_state = "idle"
        if item is None:
            self._set_transition_gain(1.0)
            return
        # Hold at silence, let UI paint, then load on next event-loop tick.
        self._set_transition_gain(0.0)
        self._pending_load_id += 1
        load_id = self._pending_load_id
        QTimer.singleShot(0, lambda it=item, ap=autoplay, lid=load_id: self._load_after_fade(it, ap, lid))

    def _load_after_fade(self, item, autoplay: bool, load_id: int) -> None:
        # If user started another transition/load meanwhile, skip stale load.
        if load_id != self._pending_load_id or self._transition_state == "fading_out":
            return
        self._set_transition_gain(0.0)
        # Update UI immediately, then defer heavy source load to keep UI responsive.
        try:
            path = Path(item.path)
            track = TrackInfo.from_path(path)
            title = str(getattr(item, "title", "") or "").strip()
            artist = str(getattr(item, "artist", "") or "").strip()
            duration = int(getattr(item, "duration", 0) or 0)
            if title:
                track.title = title
            if artist:
                track.artist = artist
            if duration > 0:
                track.duration = duration
            self._current_track = track
            self._duration = duration
            self._position = 0
            self.track_changed.emit(track)
            self.position_changed.emit(0)
            self.duration_changed.emit(self._duration)
        except Exception:
            pass
        QTimer.singleShot(30, lambda it=item, ap=autoplay, lid=load_id: self._load_source_after_fade(it, ap, lid))

    def _load_source_after_fade(self, item, autoplay: bool, load_id: int) -> None:
        if load_id != self._pending_load_id or self._transition_state == "fading_out":
            return
        self._set_transition_gain(0.0)
        ok = self._load_item(item, autoplay=autoplay, _skip_ui_update=True)
        if not ok:
            self._set_transition_gain(1.0)
            return
        if autoplay:
            self._set_transition_gain(0.0)
            self._begin_fade(1.0, 250, "fading_in")
        else:
            self._set_transition_gain(1.0)

    # --------------------------------------------------------------- playback

    def play(self) -> None:
        if self._current_track is None:
            self._emit_error("No track is loaded. Open an audio file first.")
            return
        if not self.audio_output_available:
            self._emit_error(
                "No audio output device is available. Connect or enable an "
                "output device and try again."
            )
            return
        # Resume any active transition timer when playback resumes.
        if self._transition_state in ("fading_out", "fading_in") and not self._transition_timer.isActive():
            self._transition_started = time.monotonic() - (
                (abs(self._transition_gain - self._transition_from) /
                 max(abs(self._transition_to - self._transition_from), 1e-6)) * self._transition_duration / 1000.0
            )
            self._transition_timer.start()
        if self._eq_pipeline is not None:
            self._eq_pipeline.set_playing(True)
        self._player.play()

    def pause(self) -> None:
        if self._transition_timer.isActive():
            self._transition_timer.stop()
        if self._eq_pipeline is not None:
            self._eq_pipeline.set_playing(False)
        self._player.pause()

    def toggle_play_pause(self) -> None:
        if self._state == STATE_PLAYING:
            self.pause()
        else:
            self.play()

    def stop(self) -> None:
        self._cancel_transition(restore_gain=True)
        self._player.stop()
        if self._eq_pipeline is not None:
            self._eq_pipeline.set_playing(False)
            self._eq_pipeline.stop()
        self._seek_offset_ms = 0
        self._position = 0
        self.position_changed.emit(0)
        self._set_state(STATE_STOPPED)

    def set_position(self, position_ms: int) -> None:
        if self._current_track is None:
            return
        target = max(0, int(position_ms))
        if self._duration > 0:
            target = min(target, self._duration)
        if self._eq_pipeline is not None:
            self._eq_pipeline.reset_output()
            self._seek_offset_ms = target
        self._player.setPosition(target)
        self._position = target
        self.position_changed.emit(target)
        self.seeked.emit(target)

    # ------------------------------------------------------------------ queue

    def open_files(self, tracks: Iterable, autoplay: bool = False, start_index: int = 0) -> bool:
        """Load files (or library track records) as a new playback sequence.

        Accepting TrackRecord-like objects keeps titles, artists, albums,
        durations and artwork in the queue, so the queue panel, MPRIS and
        notifications show the same metadata as the library.
        """
        accepted, skipped_message = self._validate_entries(tracks)
        if not accepted:
            if skipped_message:
                self._emit_error(skipped_message)
            return False
        self._queue.set_queue(accepted, start_index=start_index)
        item = self._queue.current_item
        loaded = self._load_item(item, autoplay=False)
        if skipped_message:
            self._emit_error(skipped_message)
        if loaded and autoplay:
            self.play()
        return loaded

    def enqueue_files(self, tracks: Iterable) -> int:
        """Append supported existing files to the queue without changing playback."""
        accepted, _skipped = self._validate_entries(tracks, emit_errors=False)
        if not accepted:
            return 0
        added = self._queue.add_many_to_queue(accepted)
        return len(added)

    def play_next_files(self, tracks: Iterable) -> int:
        accepted, _skipped = self._validate_entries(tracks, emit_errors=False)
        if not accepted:
            return 0
        if not self._queue.has_tracks() or self._queue.current_item is None:
            self.open_files(accepted, autoplay=False)
            return len(accepted)
        items = self._queue.play_next(accepted)
        return len(items)

    def load_track(self, path: str | Path, autoplay: bool = False) -> bool:
        return self.open_files([path], autoplay=autoplay)

    def next_track(self) -> bool:
        if not self._queue.has_tracks():
            self._emit_error("No tracks are loaded.")
            return False
        autoplay = self._state == STATE_PLAYING or self._transition_state in ("fading_out", "fading_in")
        self._transition_suppress_queue_load = True
        try:
            item = self._queue.advance_next(manual=True)
        finally:
            self._transition_suppress_queue_load = False
        if item is None:
            self._cancel_transition(restore_gain=True)
            self.stop()
            return False
        return self._request_track_transition(item, autoplay=autoplay)

    def previous_track(self) -> bool:
        if not self._queue.has_tracks():
            self._emit_error("No tracks are loaded.")
            return False
        # If we're > 3s into track, restart; else go previous
        if self._position > 3000 and self._queue.current_item is not None:
            self.set_position(0)
            return True
        autoplay = self._state == STATE_PLAYING or self._transition_state in ("fading_out", "fading_in")
        self._transition_suppress_queue_load = True
        try:
            item = self._queue.advance_previous()
        finally:
            self._transition_suppress_queue_load = False
        if item is None:
            self.set_position(0)
            return True
        return self._request_track_transition(item, autoplay=autoplay)

    def skip_to_queue_id(self, queue_id: int, autoplay: bool = True) -> bool:
        self._pending_autoplay = bool(autoplay)
        item = self._queue.skip_to_queue_item(queue_id)
        if item is None:
            self._pending_autoplay = None
            return False
        current_path = self._current_track.path.resolve() if self._current_track else None
        item_path = Path(item.path).resolve()
        if current_path == item_path:
            self._pending_autoplay = None
            if autoplay:
                self.play()
            return True
        # Load through transition controller; _on_queue_current_changed is guarded.
        self._transition_suppress_queue_load = True
        try:
            ok = self._request_track_transition(item, autoplay=bool(autoplay))
        finally:
            self._transition_suppress_queue_load = False
        self._pending_autoplay = None
        return ok

    # ----------------------------------------------------------------- volume

    def set_volume(self, volume: int) -> None:
        value = max(0, min(100, int(volume)))
        if value == self._volume:
            return
        self._volume = value
        if self._eq_pipeline is not None:
            self._eq_pipeline.set_volume(value / 100.0)
        else:
            vol = 0.0 if self._muted else (value / 100.0) * self._transition_gain
            self._audio_output.setVolume(vol)
        self.volume_changed.emit(value)

    def set_muted(self, muted: bool) -> None:
        muted = bool(muted)
        if muted == self._muted:
            return
        self._muted = muted
        if self._eq_pipeline is not None:
            self._eq_pipeline.set_muted(muted)
        else:
            vol = 0.0 if muted else (self._volume / 100.0) * self._transition_gain
            self._audio_output.setVolume(vol)
        self.muted_changed.emit(muted)

    def toggle_mute(self) -> None:
        self.set_muted(not self._muted)

    # --------------------------------------------------------------- helpers

    @staticmethod
    def _entry_path(entry) -> Path | None:
        """Extract a filesystem path from a path, dict, or track record."""
        raw = entry
        if isinstance(entry, dict):
            raw = entry.get("file_path") or entry.get("path")
        elif not isinstance(entry, (str, Path)):
            raw = getattr(entry, "file_path", None) or getattr(entry, "path", None)
        if raw is None or str(raw).strip() == "":
            return None
        return Path(raw).expanduser()

    def _validate_entries(self, entries: Iterable, emit_errors: bool = True) -> tuple[list, str]:
        missing: list[Path] = []
        unsupported: list[Path] = []
        accepted: list = []
        for entry in entries:
            path = self._entry_path(entry)
            if path is None:
                continue
            if not path.is_file():
                missing.append(path)
            elif path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                unsupported.append(path)
            else:
                accepted.append(path.resolve() if isinstance(entry, (str, Path)) else entry)
        skipped_message = ""
        if missing or unsupported:
            parts = []
            if missing:
                names = ", ".join(p.name for p in missing[:3])
                parts.append(f"file not found: {names}")
            if unsupported:
                names = ", ".join(p.name for p in unsupported[:3])
                parts.append(f"unsupported format: {names}")
            skipped_message = "Some files were skipped — " + "; ".join(parts)
        if not accepted and skipped_message and emit_errors:
            self._emit_error(skipped_message)
        return accepted, skipped_message

    def _validate_paths(self, paths: Iterable[str | Path], emit_errors: bool = True) -> tuple[list[Path], str]:
        accepted, skipped_message = self._validate_entries(paths, emit_errors=emit_errors)
        return [self._entry_path(entry) for entry in accepted], skipped_message

    def _load_item(self, item, autoplay: bool = False, _skip_ui_update: bool = False) -> bool:
        if item is None:
            return False
        path = Path(item.path)
        self._error_reported = False
        self._position = 0
        self._duration = 0
        self._seek_offset_ms = 0
        if self._eq_pipeline is not None:
            self._eq_pipeline.reset_output()
            self._eq_pipeline.set_playing(bool(autoplay))
        track = TrackInfo.from_path(path)
        # Prefer authoritative queue/library metadata so the UI, tray, MPRIS and
        # notifications can show the real track immediately, before Qt probes tags.
        try:
            title = str(getattr(item, "title", "") or "").strip()
            artist = str(getattr(item, "artist", "") or "").strip()
            duration = int(getattr(item, "duration", 0) or 0)
            if title:
                track.title = title
            if artist:
                track.artist = artist
            if duration > 0:
                track.duration = duration
                self._duration = duration
        except Exception:
            pass
        self._current_track = track
        if not _skip_ui_update:
            self.track_changed.emit(self._current_track)
            self.position_changed.emit(0)
            self.duration_changed.emit(self._duration)
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        if autoplay:
            self.play()
        return True

    def _on_queue_current_changed(self, item) -> None:
        if item is None:
            if not self._queue.has_tracks():
                self._cancel_transition(restore_gain=True)
                self.stop()
                self._current_track = None
                self.track_changed.emit(None)
            return
        current_path = self._current_track.path.resolve() if self._current_track else None
        item_path = Path(item.path).resolve()
        if current_path == item_path:
            return
        if self._transition_suppress_queue_load:
            return
        # If a fade-out is already targeting this item, let transition complete it.
        if self._transition_state == "fading_out" and self._transition_target is not None:
            try:
                if Path(self._transition_target.path).resolve() == item_path:
                    return
            except Exception:
                pass
        autoplay = self._pending_autoplay
        if autoplay is None:
            autoplay = (self._state == STATE_PLAYING)
        self._load_item(item, autoplay=autoplay)

    def _set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self.state_changed.emit(state)

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        mapping = {
            QMediaPlayer.PlaybackState.StoppedState: STATE_STOPPED,
            QMediaPlayer.PlaybackState.PlayingState: STATE_PLAYING,
            QMediaPlayer.PlaybackState.PausedState: STATE_PAUSED,
        }
        self._set_state(mapping.get(state, STATE_STOPPED))

    def _on_position_changed(self, position: int) -> None:
        if self._use_eq_pipeline:
            # Decode position races ahead; sink-timer emits real playback position.
            return
        self._position = max(0, int(position))
        self.position_changed.emit(self._position)

    def _on_duration_changed(self, duration: int) -> None:
        self._duration = max(0, int(duration))
        self.duration_changed.emit(self._duration)

    def _on_metadata_changed(self) -> None:
        if self._current_track is None:
            return
        metadata = self._player.metaData()
        title = _meta_text(metadata.value(QMediaMetaData.Key.Title))
        artist = (
            _meta_text(metadata.value(QMediaMetaData.Key.ContributingArtist))
            or _meta_text(metadata.value(QMediaMetaData.Key.LeadPerformer))
            or _meta_text(metadata.value(QMediaMetaData.Key.AlbumArtist))
        )
        updated = TrackInfo(
            path=self._current_track.path,
            title=title or self._current_track.path.stem,
            artist=artist or "Unknown artist",
        )
        if updated != self._current_track:
            self._current_track = updated
            self.track_changed.emit(updated)

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self._use_eq_pipeline and self._eq_pipeline is not None:
                # Decoder finished; let sink drain buffered audio before advancing.
                try:
                    if len(self._eq_pipeline._queue) > 0:
                        QTimer.singleShot(80, lambda: self._on_media_status_changed(status))
                        return
                except Exception:
                    pass
            if self._queue.repeat_mode == REPEAT_ONE and self._queue.current_item is not None:
                self.set_position(0)
                self._set_transition_gain(1.0)
                self.play()
                return
            self._transition_suppress_queue_load = True
            try:
                nxt = self._queue.advance_next()
            finally:
                self._transition_suppress_queue_load = False
            if nxt is not None:
                self._set_transition_gain(0.0)
                ok = self._load_item(nxt, autoplay=True)
                if ok:
                    self._begin_fade(1.0, 250, "fading_in")
                else:
                    self._set_transition_gain(1.0)
            else:
                self._cancel_transition(restore_gain=True)
                self._player.stop()
                if self._eq_pipeline is not None:
                    self._eq_pipeline.set_playing(False)
                    self._eq_pipeline.stop()
                self._position = 0
                self.position_changed.emit(0)
                self._set_state(STATE_STOPPED)
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            if not self._error_reported:
                self._emit_error(
                    "This audio file could not be opened. It may be damaged or "
                    "use a format the Qt Multimedia backend cannot decode."
                )
            self._set_state(STATE_STOPPED)

    def _on_player_error(self, error: QMediaPlayer.Error, error_string: str) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        messages = {
            QMediaPlayer.Error.ResourceError: (
                "The audio file could not be opened. Check that it exists and is readable."
            ),
            QMediaPlayer.Error.FormatError: (
                "The audio format is not supported by the installed Qt Multimedia backend."
            ),
            QMediaPlayer.Error.NetworkError: "A network error occurred while loading audio.",
            QMediaPlayer.Error.AccessDeniedError: "Access to the audio file was denied.",
        }
        message = messages.get(error, "An unexpected playback error occurred.")
        if error_string:
            message = f"{message} ({error_string})"
        self._emit_error(message)
        self._set_state(STATE_STOPPED)

    def _emit_error(self, message: str) -> None:
        self._error_reported = True
        self.error_occurred.emit(message)
