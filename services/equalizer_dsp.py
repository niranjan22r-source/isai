"""ctypes wrapper for the small ISAI EQ DSP shared library."""

from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path

_LIB = None


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _bundle_base() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def _lib_path() -> Path:
    here = Path(__file__).resolve().parent
    suffix = ".dylib" if sys.platform == "darwin" else ".dll" if sys.platform == "win32" else ".so"
    name = f"_eq_dsp{suffix}"
    candidates = [
        here / name,
        _bundle_base() / "services" / name,
        _bundle_base() / name,
    ]
    for c in candidates:
        if c.exists():
            return c
    return here / name


def _compile() -> Path:
    src = Path(__file__).resolve().parent / "eq_dsp.c"
    out = _lib_path()
    if out.exists():
        if _is_frozen() or not src.exists() or out.stat().st_mtime >= src.stat().st_mtime:
            return out
    if _is_frozen():
        raise FileNotFoundError(f"EQ DSP library not found in packaged app: {out}")
    if not src.exists():
        raise FileNotFoundError(f"EQ DSP source not found: {src}")
    cmd = ["gcc", "-shared", "-fPIC", "-O2", "-o", str(out), str(src), "-lm"]
    subprocess.check_call(cmd, cwd=str(src.parent))
    return out


class EqState(ctypes.Structure):
    _fields_ = []  # opaque to Python; we only pass pointer


def get_lib():
    global _LIB
    if _LIB is not None:
        return _LIB
    path = _compile()
    lib = ctypes.CDLL(str(path))
    # void eq_init(EqState*)
    lib.eq_init.argtypes = [ctypes.c_void_p]
    lib.eq_init.restype = None
    lib.eq_set_enabled.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.eq_set_enabled.restype = None
    lib.eq_set_preamp.argtypes = [ctypes.c_void_p, ctypes.c_double]
    lib.eq_set_preamp.restype = None
    lib.eq_set_band.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_double, ctypes.c_double, ctypes.c_double]
    lib.eq_set_band.restype = None
    lib.eq_configure.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_double), ctypes.c_double]
    lib.eq_configure.restype = None
    lib.eq_reset.argtypes = [ctypes.c_void_p]
    lib.eq_reset.restype = None
    lib.eq_process_f32.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float), ctypes.c_int]
    lib.eq_process_f32.restype = None
    lib.eq_process_s16.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_short), ctypes.c_int]
    lib.eq_process_s16.restype = None
    # Allocate state size - must match C struct. We'll allocate generous buffer.
    lib.eq_state_size = ctypes.sizeof(ctypes.c_double) * 200  # generous
    _LIB = lib
    return lib


def create_state():
    lib = get_lib()
    # Allocate raw buffer large enough for EqState
    # EqState: int + pad + double preamp_db + preamp_gain + int band_count + pad + 10*double*3 + int sample_rate + pad + 10*Biquad
    # Biquad: 5 doubles + 4 doubles = 9 doubles = 72 bytes. 10 bands = 720. Header ~200. Safe: 4096 bytes.
    buf = ctypes.create_string_buffer(4096)
    lib.eq_init(ctypes.byref(buf))
    return buf
