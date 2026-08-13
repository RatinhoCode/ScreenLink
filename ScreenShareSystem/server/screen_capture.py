"""Captura de tela usando mss, com encode para JPEG."""
from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import mss
from PIL import Image

from mouse_overlay import MouseHighlightSettings, MouseTracker, draw_mouse_highlight


@dataclass(frozen=True)
class MonitorInfo:
    index: int
    width: int
    height: int


class ScreenCapture:
    """Encapsula uma instância de mss.mss() para capturar e codificar frames.

    Uma instância de mss.mss() não é thread-safe entre threads diferentes,
    então cada conexão de cliente cria a sua própria ScreenCapture.
    """

    def __init__(self) -> None:
        self._sct = mss.mss()

    def list_monitors(self) -> list[MonitorInfo]:
        # índice 0 é o "monitor virtual" (todos combinados); ignoramos ele
        # e expomos apenas os monitores físicos, a partir do índice 1.
        monitors = self._sct.monitors[1:]
        return [
            MonitorInfo(index=i + 1, width=m["width"], height=m["height"])
            for i, m in enumerate(monitors)
        ]

    def grab_jpeg(
        self,
        monitor_index: int,
        quality: int = 70,
        mouse_tracker: MouseTracker | None = None,
        highlight_settings: MouseHighlightSettings | None = None,
    ) -> bytes:
        monitors = self._sct.monitors
        if monitor_index < 1 or monitor_index >= len(monitors):
            raise ValueError(f"Monitor inválido: {monitor_index}")

        monitor = monitors[monitor_index]
        raw = self._sct.grab(monitor)
        image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        if mouse_tracker is not None and highlight_settings is not None:
            image = draw_mouse_highlight(
                image, monitor["left"], monitor["top"], mouse_tracker, highlight_settings,
            )

        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=quality)
        return buffer.getvalue()

    def close(self) -> None:
        self._sct.close()
