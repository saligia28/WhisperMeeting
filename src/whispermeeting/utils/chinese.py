"""Chinese text utilities."""

from __future__ import annotations

from functools import lru_cache
from typing import Callable

try:  # pragma: no cover - optional dependency
    from opencc import OpenCC  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    OpenCC = None  # type: ignore

try:  # pragma: no cover - optional dependency
    import zhconv  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    zhconv = None  # type: ignore

_warned_missing_converter = False


def _log_missing_converter() -> None:
    global _warned_missing_converter
    if not _warned_missing_converter:
        print(
            "[ChineseText] opencc/zhconv not available; skipping 繁体->简体 conversion. "
            "Install `opencc-python-reimplemented` or `zhconv` for best results.",
            flush=True,
        )
        _warned_missing_converter = True


@lru_cache(maxsize=1)
def _resolve_converter() -> Callable[[str], str] | None:
    if OpenCC is not None:
        try:
            cc = OpenCC("t2s")
            return cc.convert
        except Exception:
            pass

    if "zhconv" in globals() and zhconv is not None:
        try:
            return lambda text: zhconv.convert(text, "zh-hans")
        except Exception:
            pass

    return None


def ensure_simplified(text: str) -> str:
    """Convert text to Simplified Chinese when possible."""
    if not text:
        return text

    converter = _resolve_converter()
    if converter is None:
        _log_missing_converter()
        return text

    try:
        return converter(text)
    except Exception:
        _log_missing_converter()
        return text
