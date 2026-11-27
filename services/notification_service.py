"""Linux desktop notifications for ISAI track changes (D-Bus)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage


class NotificationService(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._enabled = True
        self._last_notified: str | None = None
        self._iface = QDBusInterface(
            "org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications",
            QDBusConnection.sessionBus(),
        )

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def available(self) -> bool:
        try:
            return QDBusConnection.sessionBus().isConnected() and self._iface.isValid()
        except Exception:
            return False

    def notify_track(self, title: str, artist: str = "", album: str = "", artwork_path: str | None = None) -> bool:
        if not self._enabled:
            return False
        key = f"{title}\u0000{artist}\u0000{album}"
        if key == self._last_notified:
            return False
        if not self.available():
            return False
        try:
            body = artist
            if album:
                body = f"{artist} — {album}" if artist else album
            icon = ""
            if artwork_path:
                p = Path(artwork_path)
                if p.is_file():
                    icon = str(p.resolve())
            # Notify(app_name, replaces_id, app_icon, summary, body, actions, hints, expire_timeout)
            msg = self._iface.call(
                "Notify",
                "ISAI",
                0,
                icon or "audio-x-generic",
                title or "Unknown track",
                body,
                [],
                {},
                3000,
            )
            if msg.type() != QDBusMessage.MessageType.ErrorMessage:
                self._last_notified = key
                return True
        except Exception:
            pass
        return False

    def reset(self) -> None:
        self._last_notified = None
