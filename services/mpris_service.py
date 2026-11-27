"""MPRIS2 D-Bus integration for ISAI.

Exposes org.mpris.MediaPlayer2 and org.mpris.MediaPlayer2.Player on the
session bus. All playback actions delegate to the existing AudioEngine/QueueManager.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, ClassInfo, QMetaType, QObject, Property, Slot, Signal as QtSignal, QUrl
from PySide6.QtDBus import (
    QDBusAbstractAdaptor,
    QDBusArgument,
    QDBusConnection,
    QDBusMessage,
    QDBusObjectPath,
)

from services.audio_engine import STATE_PLAYING, STATE_PAUSED

MPRIS_OBJECT_PATH = "/org/mpris/MediaPlayer2"
MPRIS_ROOT_IFACE = "org.mpris.MediaPlayer2"
MPRIS_PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"


def _us_from_ms(ms: int) -> int:
    return max(0, int(ms)) * 1000


def _ms_from_us(us: int) -> int:
    return max(0, int(us) // 1000)


def _track_id(queue_id: int | None) -> QDBusObjectPath:
    n = int(queue_id) if queue_id is not None else 0
    return QDBusObjectPath(f"/org/mpris/MediaPlayer2/Track/{n}")


@ClassInfo({"D-Bus Interface": MPRIS_ROOT_IFACE, "D-Bus Introspection": """
    <interface name="org.mpris.MediaPlayer2">
      <method name="Raise"/>
      <method name="Quit"/>
      <property name="CanQuit" type="b" access="read"/>
      <property name="CanRaise" type="b" access="read"/>
      <property name="HasTrackList" type="b" access="read"/>
      <property name="Identity" type="s" access="read"/>
      <property name="DesktopEntry" type="s" access="read"/>
      <property name="SupportedUriSchemes" type="as" access="read"/>
      <property name="SupportedMimeTypes" type="as" access="read"/>
    </interface>
    """})
class _MprisRootAdaptor(QDBusAbstractAdaptor):
    def __init__(self, service: "MprisService"):
        super().__init__(service)
        self._service = service

    @Slot()
    def Raise(self):
        self._service.raise_requested()

    @Slot()
    def Quit(self):
        self._service.quit_requested()

    @Property(bool)
    def CanQuit(self):
        return True

    @Property(bool)
    def CanRaise(self):
        return True

    @Property(bool)
    def HasTrackList(self):
        return False

    @Property(str)
    def Identity(self):
        return "ISAI"

    @Property(str)
    def DesktopEntry(self):
        return "isai"

    @Property("QStringList")
    def SupportedUriSchemes(self):
        return ["file"]

    @Property("QStringList")
    def SupportedMimeTypes(self):
        return ["audio/mpeg", "audio/flac", "audio/ogg", "audio/wav", "audio/mp4", "audio/aac"]


@ClassInfo({"D-Bus Interface": MPRIS_PLAYER_IFACE, "D-Bus Introspection": """
    <interface name="org.mpris.MediaPlayer2.Player">
      <method name="Next"/>
      <method name="Previous"/>
      <method name="Pause"/>
      <method name="PlayPause"/>
      <method name="Stop"/>
      <method name="Play"/>
      <method name="Seek"><arg direction="in" name="Offset" type="x"/></method>
      <method name="SetPosition"><arg direction="in" name="TrackId" type="o"/><arg direction="in" name="Position" type="x"/></method>
      <method name="OpenUri"><arg direction="in" name="Uri" type="s"/></method>
      <property name="PlaybackStatus" type="s" access="read"/>
      <property name="Metadata" type="a{sv}" access="read"/>
      <property name="Position" type="x" access="read"/>
      <property name="Rate" type="d" access="read"/>
      <property name="MinimumRate" type="d" access="read"/>
      <property name="MaximumRate" type="d" access="read"/>
      <property name="Volume" type="d" access="readwrite"/>
      <property name="CanGoNext" type="b" access="read"/>
      <property name="CanGoPrevious" type="b" access="read"/>
      <property name="CanPlay" type="b" access="read"/>
      <property name="CanPause" type="b" access="read"/>
      <property name="CanSeek" type="b" access="read"/>
      <property name="CanControl" type="b" access="read"/>
    </interface>
    """})
class _MprisPlayerAdaptor(QDBusAbstractAdaptor):
    def __init__(self, service: "MprisService"):
        super().__init__(service)
        self._service = service

    @Slot()
    def Next(self):
        self._service.next()

    @Slot()
    def Previous(self):
        self._service.previous()

    @Slot()
    def Pause(self):
        self._service.pause()

    @Slot()
    def PlayPause(self):
        self._service.play_pause()

    @Slot()
    def Stop(self):
        self._service.stop()

    @Slot()
    def Play(self):
        self._service.play()

    @Slot("qlonglong")
    def Seek(self, offset):
        self._service.seek_relative(int(offset))

    @Slot(QDBusObjectPath, "qlonglong")
    def SetPosition(self, track_id, position):
        self._service.set_position(str(track_id.path()), int(position))

    @Slot(str)
    def OpenUri(self, uri):
        self._service.open_uri(uri)

    @Property(str)
    def PlaybackStatus(self):
        return self._service.playback_status()

    @Property("QVariantMap")
    def Metadata(self):
        return self._service.metadata()

    @Property("qlonglong")
    def Position(self):
        return self._service.position_us()

    @Property(float)
    def Rate(self):
        return 1.0

    @Property(float)
    def MinimumRate(self):
        return 1.0

    @Property(float)
    def MaximumRate(self):
        return 1.0

    @Property(float)
    def Volume(self):
        return self._service.volume()

    @Volume.setter
    def Volume(self, value):
        self._service.set_volume(float(value))

    @Property(bool)
    def CanGoNext(self):
        return self._service.can_go_next()

    @Property(bool)
    def CanGoPrevious(self):
        return self._service.can_go_previous()

    @Property(bool)
    def CanPlay(self):
        return self._service.can_play()

    @Property(bool)
    def CanPause(self):
        return self._service.can_pause()

    @Property(bool)
    def CanSeek(self):
        return self._service.can_seek()

    @Property(bool)
    def CanControl(self):
        return True


class MprisService(QObject):
    """Registers ISAI as an MPRIS2 media player on the session bus."""

    def __init__(self, audio_engine, library_db=None, parent=None):
        super().__init__(parent)
        self._engine = audio_engine
        self._db = library_db
        self._bus = QDBusConnection.sessionBus()
        self._registered = False
        self._name = "org.mpris.MediaPlayer2.isai"
        self._raise_cb = None
        self._quit_cb = None
        self._root = _MprisRootAdaptor(self)
        self._player = _MprisPlayerAdaptor(self)

    @property
    def service_name(self) -> str:
        return self._name

    @property
    def is_registered(self) -> bool:
        return self._registered

    def set_callbacks(self, raise_cb=None, quit_cb=None):
        self._raise_cb = raise_cb
        self._quit_cb = quit_cb

    def start(self) -> bool:
        if self._registered:
            return True
        try:
            if not self._bus.isConnected():
                return False
            # Avoid duplicate: if name already taken, try a unique suffix.
            if not self._bus.registerService(self._name):
                # try instance-specific
                import os
                alt = f"{self._name}.instance{os.getpid()}"
                if not self._bus.registerService(alt):
                    return False
                self._name = alt
            ok = self._bus.registerObject(
                MPRIS_OBJECT_PATH,
                self,
                QDBusConnection.ExportAdaptors,
            )
            if not ok:
                self._bus.unregisterService(self._name)
                return False
            self._registered = True
            self._connect_signals()
            return True
        except Exception:
            self._registered = False
            return False

    def shutdown(self) -> None:
        if not self._registered:
            return
        try:
            self._bus.unregisterObject(MPRIS_OBJECT_PATH)
        except Exception:
            pass
        try:
            self._bus.unregisterService(self._name)
        except Exception:
            pass
        self._registered = False

    def _connect_signals(self):
        e = self._engine
        e.state_changed.connect(lambda _s: self._emit_props(MPRIS_PLAYER_IFACE, ["PlaybackStatus", "CanPlay", "CanPause"]))
        e.track_changed.connect(lambda _t: self._emit_props(MPRIS_PLAYER_IFACE, ["Metadata", "PlaybackStatus", "CanPlay", "CanPause", "CanSeek", "CanGoNext", "CanGoPrevious"]))
        e.duration_changed.connect(lambda _d: self._emit_props(MPRIS_PLAYER_IFACE, ["Metadata"]))
        e.volume_changed.connect(lambda _v: self._emit_props(MPRIS_PLAYER_IFACE, ["Volume"]))
        e.queue_changed.connect(lambda: self._emit_props(MPRIS_PLAYER_IFACE, ["CanGoNext", "CanGoPrevious"]))
        try:
            e.seeked.connect(self.emit_seeked)
        except Exception:
            pass

    def _emit_props(self, iface: str, props: list[str]):
        if not self._registered:
            return
        try:
            # The signal signature must be exactly sa{sv}as.
            #
            # PySide6 infers the third argument as av when given a plain
            # empty list, producing sa{sv}av.  GDBusProxy clients (GNOME
            # Shell, gsd-media-keys, ...) reject that signature outright, so
            # the system media control never refreshes and keeps showing
            # "Unknown title/artist".  Build an explicitly typed empty "as"
            # array instead; with that hint QtDBus also infers the plain
            # value dict as a{sv} and wraps each value exactly once.
            changed = {}
            for p in props:
                changed[p] = self._get_prop(iface, p)
            invalidated = QDBusArgument()
            invalidated.beginArray(QMetaType.Type.QString)
            invalidated.endArray()
            msg = QDBusMessage.createSignal(MPRIS_OBJECT_PATH, PROPERTIES_IFACE, "PropertiesChanged")
            msg.setArguments([iface, changed, invalidated])
            self._bus.send(msg)
        except Exception:
            pass

    def _get_prop(self, iface: str, prop: str):
        if iface == MPRIS_PLAYER_IFACE:
            return getattr(self, {
                "PlaybackStatus": "playback_status",
                "Metadata": "metadata",
                "Position": "position_us",
                "Volume": "volume",
                "CanGoNext": "can_go_next",
                "CanGoPrevious": "can_go_previous",
                "CanPlay": "can_play",
                "CanPause": "can_pause",
                "CanSeek": "can_seek",
            }[prop])()
        return None

    def _maybe_emit_seeked(self, pos_ms: int):
        # Avoid excessive signals; Position is polled by clients, Seeked only on real seeks.
        # We emit Seeked from explicit seek operations.
        return

    def emit_seeked(self, pos_ms: int):
        if not self._registered:
            return
        try:
            msg = QDBusMessage.createSignal(MPRIS_OBJECT_PATH, MPRIS_PLAYER_IFACE, "Seeked")
            msg.setArguments([_us_from_ms(pos_ms)])
            self._bus.send(msg)
        except Exception:
            pass

    # ----------------------------------------------------------------- actions

    def raise_requested(self):
        if callable(self._raise_cb):
            try: self._raise_cb()
            except Exception: pass

    def quit_requested(self):
        if callable(self._quit_cb):
            try: self._quit_cb()
            except Exception: pass

    def play(self):
        self._engine.play()

    def pause(self):
        self._engine.pause()

    def play_pause(self):
        self._engine.toggle_play_pause()

    def stop(self):
        self._engine.stop()

    def next(self):
        self._engine.next_track()

    def previous(self):
        self._engine.previous_track()

    def seek_relative(self, offset_us: int):
        target = self._engine.position + _ms_from_us(offset_us)
        self._engine.set_position(target)

    def set_position(self, track_path: str, pos_us: int):
        cur = self._engine.queue_manager.current_item
        if cur is None:
            return
        expected = str(_track_id(cur.queue_id).path())
        if track_path != expected:
            return
        pos_ms = _ms_from_us(pos_us)
        if 0 <= pos_ms <= max(0, self._engine.duration):
            self._engine.set_position(pos_ms)

    def open_uri(self, uri: str):
        try:
            q = QUrl(uri)
            if q.isLocalFile():
                self._engine.open_files([q.toLocalFile()], autoplay=True)
        except Exception:
            pass

    # ------------------------------------------------------------------- state

    def playback_status(self) -> str:
        s = self._engine.playback_state
        if s == STATE_PLAYING:
            return "Playing"
        if s == STATE_PAUSED:
            return "Paused"
        return "Stopped"

    def position_us(self) -> int:
        return _us_from_ms(self._engine.position)

    def volume(self) -> float:
        return max(0.0, min(1.0, self._engine.volume / 100.0))

    def set_volume(self, v: float):
        self._engine.set_volume(int(max(0.0, min(1.0, v)) * 100))

    def can_play(self) -> bool:
        return self._engine.current_track is not None or self._engine.queue_manager.has_tracks()

    def can_pause(self) -> bool:
        return self.can_play()

    def can_seek(self) -> bool:
        return self._engine.current_track is not None and self._engine.duration > 0

    def can_go_next(self) -> bool:
        return self._engine.queue_manager.next_index(manual=True) is not None

    def can_go_previous(self) -> bool:
        return self._engine.queue_manager.has_tracks()

    def metadata(self) -> dict:
        """Return MPRIS metadata using plain D-Bus-marshallable values.

        Plain values are important: QtDBus already wraps each value of a
        QVariantMap / a{sv} in a single variant.  Wrapping them in
        QDBusVariant here produces a double variant (v v ...), which clients
        such as GNOME Shell cannot read and report as "Unknown title/artist".
        """
        cur = self._engine.queue_manager.current_item
        track = self._engine.current_track
        if track is None and cur is None:
            return {"mpris:trackid": _track_id(None)}
        queue_id = cur.queue_id if cur else 0
        title = (cur.title if cur and cur.title else (track.title if track else "Unknown"))
        artist = (cur.artist if cur and cur.artist else (track.artist if track else ""))
        album = (cur.album if cur and cur.album else getattr(track, "album", "") if track else "")
        duration_ms = int(self._engine.duration or (cur.duration if cur else 0) or 0)
        length = _us_from_ms(duration_ms)
        art = ""
        try:
            art_path = cur.artwork_path if cur else None
            if not art_path and self._db and track is not None:
                rec = self._db.get_track_by_path(str(track.path))
                art_path = rec.artwork_path if rec else None
            if art_path and Path(art_path).is_file():
                art = QUrl.fromLocalFile(str(Path(art_path).resolve())).toString()
        except Exception:
            art = ""
        md = {
            "mpris:trackid": _track_id(queue_id),
            "xesam:title": title or "Unknown title",
        }
        if artist:
            md["xesam:artist"] = [artist]
        if album:
            md["xesam:album"] = album
        if length > 0:
            md["mpris:length"] = int(length)
        if art:
            md["mpris:artUrl"] = art
        if track is not None:
            md["xesam:url"] = QUrl.fromLocalFile(str(track.path)).toString()
        return md
