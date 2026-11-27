"""Real-time EQ pipeline: QAudioBufferOutput -> C DSP -> QAudioSink.

QMediaPlayer decodes; this pipeline applies 10-band EQ + preamp and outputs to
QAudioSink. Decode is throttled to stay near real time so position/end-of-media
remain usable.
"""

from __future__ import annotations

import ctypes
import struct

from PySide6.QtCore import QObject, QTimer
from PySide6.QtMultimedia import QAudio, QAudioBufferOutput, QAudioFormat, QAudioSink, QMediaDevices

from services.equalizer_dsp import create_state, get_lib


class EqAudioPipeline(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._lib = get_lib()
        self._state = create_state()
        self._enabled = True
        self._volume = 0.7
        self._muted = False

        self._sink: QAudioSink | None = None
        self._io = None
        self._fmt: QAudioFormat | None = None
        self._queue = bytearray()
        self._max_queue_bytes = 44100 * 2 * 2 // 2  # ~0.5s stereo int16
        self._low_watermark = 44100 * 2 * 2 // 10  # ~0.1s
        self._playing = False
        self._decode_paused_by_us = False
        self._last_bands = [0.0] * 10
        self._last_freqs = [31,62,125,250,500,1000,2000,4000,8000,16000]
        self._last_preamp = 0.0
        self._last_qs = [1.0] * 10
        self._last_sample_rate = 44100
        self._transition_gain = 1.0

        self.buffer_output = QAudioBufferOutput(self)
        self.buffer_output.audioBufferReceived.connect(self._on_buffer)

        self._pause_decode_cb = None
        self._resume_decode_cb = None

        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._drain)
        self._timer.start()

    def set_decode_callbacks(self, pause_cb, resume_cb) -> None:
        self._pause_decode_cb = pause_cb
        self._resume_decode_cb = resume_cb

    # -------------------------------------------------------------- EQ config

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self._lib.eq_set_enabled(ctypes.byref(self._state), 1 if self._enabled else 0)

    def set_preamp(self, db: float) -> None:
        self._lib.eq_set_preamp(ctypes.byref(self._state), float(db))

    def set_band(self, index: int, gain_db: float, freq: float, q: float) -> None:
        self._lib.eq_set_band(ctypes.byref(self._state), int(index), float(gain_db), float(freq), float(q))

    def configure(self, bands: list[float], freqs: list[float], preamp_db: float, qs: list[float] | None = None, sample_rate: int = 44100) -> None:
        n = min(10, len(bands), len(freqs))
        qvals = qs if qs and len(qs) >= n else [1.0] * n
        self._last_bands = [float(bands[i]) for i in range(n)] + [0.0] * (10 - n)
        self._last_freqs = [float(freqs[i]) for i in range(n)] + self._last_freqs[n:]
        self._last_preamp = float(preamp_db)
        self._last_qs = [float(qvals[i]) for i in range(n)] + [1.0] * (10 - n)
        self._last_sample_rate = int(sample_rate)
        self._apply_config()

    def reset(self) -> None:
        self._lib.eq_reset(ctypes.byref(self._state))

    # -------------------------------------------------------------- output

    def _effective_volume(self) -> float:
        return 0.0 if self._muted else max(0.0, min(1.0, self._volume * self._transition_gain))

    def _apply_sink_volume(self) -> None:
        if self._sink is not None:
            try:
                self._sink.setVolume(self._effective_volume())
            except Exception:
                pass

    def set_transition_gain(self, gain: float) -> None:
        self._transition_gain = max(0.0, min(1.0, float(gain)))
        self._apply_sink_volume()

    def transition_gain(self) -> float:
        return self._transition_gain

    def set_volume(self, volume_0_1: float) -> None:
        self._volume = max(0.0, min(1.0, float(volume_0_1)))
        self._apply_sink_volume()

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        self._apply_sink_volume()

    def set_playing(self, playing: bool) -> None:
        self._playing = bool(playing)
        if self._sink is None:
            return
        try:
            if self._playing:
                self._sink.resume()
            else:
                self._sink.suspend()
        except Exception:
            pass
        self._maybe_resume_decode()

    def reset_output(self) -> None:
        self._queue.clear()
        self._decode_paused_by_us = False
        if self._sink is not None:
            try:
                self._sink.reset()
                self._io = self._sink.start()
            except Exception:
                try:
                    self._io = self._sink.start()
                except Exception:
                    self._io = None

    def stop(self) -> None:
        self._queue.clear()
        self._decode_paused_by_us = False
        if self._sink is not None:
            try:
                self._sink.stop()
            except Exception:
                pass
        self._io = None

    def processed_us(self) -> int:
        if self._sink is None:
            return 0
        try:
            return int(self._sink.processedUSecs())
        except Exception:
            return 0

    # -------------------------------------------------------------- internals

    def _apply_config(self) -> None:
        n = 10
        freq_arr = (ctypes.c_double * n)(*self._last_freqs[:n])
        gain_arr = (ctypes.c_double * n)(*self._last_bands[:n])
        q_arr = (ctypes.c_double * n)(*self._last_qs[:n])
        self._lib.eq_configure(ctypes.byref(self._state), int(self._last_sample_rate), n, freq_arr, gain_arr, q_arr, float(self._last_preamp))
        self._lib.eq_set_enabled(ctypes.byref(self._state), 1 if self._enabled else 0)

    def _ensure_sink(self, fmt: QAudioFormat) -> None:
        # We output int16 stereo at the buffer's sample rate for simplicity.
        out_fmt = QAudioFormat(fmt)
        if out_fmt.channelCount() != 2:
            out_fmt.setChannelCount(2)
        if out_fmt.sampleFormat() != QAudioFormat.SampleFormat.Int16:
            out_fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if self._fmt is not None and self._sink is not None and self._fmt == out_fmt:
            # still update sample rate for DSP if needed
            sr = int(out_fmt.sampleRate())
            if sr > 0 and sr != self._last_sample_rate:
                self._last_sample_rate = sr
                self._apply_config()
            return
        self.stop()
        self._fmt = QAudioFormat(out_fmt)
        sr = int(out_fmt.sampleRate())
        if sr > 0:
            self._last_sample_rate = sr
        self._apply_config()
        dev = QMediaDevices.defaultAudioOutput()
        try:
            self._sink = QAudioSink(dev, self._fmt, self)
        except Exception:
            self._sink = QAudioSink(self._fmt, self)
        self._sink.setVolume(self._effective_volume())
        try:
            self._io = self._sink.start()
        except Exception:
            self._io = None
        if not self._playing and self._sink is not None:
            try:
                self._sink.suspend()
            except Exception:
                pass

    def _on_buffer(self, buf) -> None:
        try:
            fmt = buf.format()
            self._ensure_sink(fmt)
            fmt = buf.format()
            sample_fmt = fmt.sampleFormat()
            channels = fmt.channelCount()
            data = buf.data()
            if data is None:
                return
            try:
                raw = bytes(data)
            except Exception:
                try:
                    raw = data.tobytes()
                except Exception:
                    return
            if not raw:
                return
            # Fast path: int16 stereo
            if sample_fmt == QAudioFormat.SampleFormat.Int16 and channels == 2:
                frames = len(raw) // 4
                if frames > 0:
                    buf_arr = (ctypes.c_short * (frames * 2)).from_buffer_copy(raw)
                    self._lib.eq_process_s16(ctypes.byref(self._state), buf_arr, frames)
                    raw = ctypes.string_at(buf_arr, len(raw))
            else:
                raw = self._buffer_to_int16_stereo_bytes(buf)
                if not raw:
                    return
                samples, frames = self._int16_bytes_to_float(raw)
                if frames > 0:
                    self._lib.eq_process_f32(ctypes.byref(self._state), samples, frames)
                    raw = self._float_to_int16_bytes(samples)
            if len(self._queue) + len(raw) <= self._max_queue_bytes:
                self._queue.extend(raw)
            else:
                overflow = len(self._queue) + len(raw) - self._max_queue_bytes
                if overflow > 0 and overflow < len(self._queue):
                    del self._queue[:overflow]
                if len(self._queue) + len(raw) <= self._max_queue_bytes:
                    self._queue.extend(raw)
            self._drain()
            self._maybe_pause_decode()
        except Exception:
            return

    def _maybe_pause_decode(self) -> None:
        if self._playing and len(self._queue) >= self._max_queue_bytes - 4096 and not self._decode_paused_by_us:
            if callable(self._pause_decode_cb):
                try:
                    self._pause_decode_cb()
                    self._decode_paused_by_us = True
                except Exception:
                    pass

    def _maybe_resume_decode(self) -> None:
        if self._decode_paused_by_us and len(self._queue) <= self._low_watermark:
            if callable(self._resume_decode_cb):
                try:
                    self._resume_decode_cb()
                    self._decode_paused_by_us = False
                except Exception:
                    self._decode_paused_by_us = False

    def _drain(self) -> None:
        if self._sink is None or self._io is None:
            return
        try:
            if self._sink.state() == QAudio.State.StoppedState:
                return
            free = self._sink.bytesFree()
        except Exception:
            return
        if free <= 0 or not self._queue:
            self._maybe_resume_decode()
            return
        chunk = bytes(self._queue[:free])
        del self._queue[:len(chunk)]
        try:
            self._io.write(chunk)
        except Exception:
            pass
        self._maybe_resume_decode()

    # -------------------------------------------------------------- conversions

    def _buffer_to_int16_stereo_bytes(self, buf) -> bytes:
        fmt = buf.format()
        data = buf.data()
        if data is None:
            return b""
        try:
            raw = bytes(data)
        except Exception:
            try:
                raw = data.tobytes()
            except Exception:
                return b""
        if not raw:
            return b""
        channels = fmt.channelCount()
        sample_fmt = fmt.sampleFormat()
        if sample_fmt == QAudioFormat.SampleFormat.Int16 and channels == 2:
            return raw
        # Convert to int16 stereo
        if sample_fmt == QAudioFormat.SampleFormat.Float and channels == 2:
            n = len(raw) // 4
            vals = struct.unpack('<' + 'f' * n, raw)
            out = bytearray(n * 2)
            for i, v in enumerate(vals):
                if v > 1.0: v = 1.0
                elif v < -1.0: v = -1.0
                struct.pack_into('<h', out, i * 2, int(v * 32767))
            return bytes(out)
        if sample_fmt == QAudioFormat.SampleFormat.Int16 and channels == 1:
            n = len(raw) // 2
            vals = struct.unpack('<' + 'h' * n, raw)
            out = bytearray(n * 4)
            for i, v in enumerate(vals):
                struct.pack_into('<hh', out, i * 4, v, v)
            return bytes(out)
        if sample_fmt == QAudioFormat.SampleFormat.Float and channels == 1:
            n = len(raw) // 4
            vals = struct.unpack('<' + 'f' * n, raw)
            out = bytearray(n * 4)
            for i, v in enumerate(vals):
                if v > 1.0: v = 1.0
                elif v < -1.0: v = -1.0
                iv = int(v * 32767)
                struct.pack_into('<hh', out, i * 4, iv, iv)
            return bytes(out)
        # Unsupported format - best effort: ignore
        return b""

    @staticmethod
    def _int16_bytes_to_float(raw: bytes) -> tuple[ctypes.Array, int]:
        n = len(raw) // 2
        frames = n // 2
        arr = (ctypes.c_float * (frames * 2))()
        if frames <= 0:
            return arr, 0
        vals = struct.unpack_from('<' + 'h' * (frames * 2), raw, 0)
        scale = 1.0 / 32768.0
        for i, v in enumerate(vals):
            arr[i] = v * scale
        return arr, frames

    @staticmethod
    def _float_to_int16_bytes(samples: ctypes.Array) -> bytes:
        n = len(samples)
        out = bytearray(n * 2)
        for i in range(n):
            v = samples[i]
            if v > 1.0:
                v = 1.0
            elif v < -1.0:
                v = -1.0
            struct.pack_into('<h', out, i * 2, int(v * 32767.0))
        return bytes(out)
