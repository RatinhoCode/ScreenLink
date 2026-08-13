"""Rastreamento do cursor do PC e desenho do destaque visual do mouse.

Usa pynput para ler a posição global do cursor e capturar cliques, e Pillow
para desenhar o círculo de destaque e o efeito de "ripple" no clique sobre o
frame já capturado, antes de codificar em JPEG.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock

from PIL import Image, ImageDraw

try:
    from pynput import mouse
except Exception:  # pragma: no cover - ambiente sem suporte a input global
    mouse = None


@dataclass
class ClickEvent:
    x: int
    y: int
    started_at: float


@dataclass
class MouseHighlightSettings:
    enabled: bool = False
    size: int = 40              # diâmetro do círculo, em pixels de tela
    opacity: float = 0.55       # 0.0 (invisível) .. 1.0 (opaco)
    click_duration_ms: int = 400
    click_effects: bool = True

    def as_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "size": self.size,
            "opacity": self.opacity,
            "click_duration_ms": self.click_duration_ms,
            "click_effects": self.click_effects,
        }


class MouseTracker:
    """Instância única e compartilhada entre todas as sessões: há apenas um
    cursor físico no PC, então um único listener pynput basta para todos os
    clientes conectados."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._clicks: list[ClickEvent] = []
        self._controller = mouse.Controller() if mouse else None
        self._listener = mouse.Listener(on_click=self._on_click) if mouse else None
        if self._listener:
            self._listener.start()

    def _on_click(self, x, y, button, pressed) -> None:
        if not pressed:
            return
        with self._lock:
            self._clicks.append(ClickEvent(x=x, y=y, started_at=time.monotonic()))
            self._clicks = self._clicks[-20:]

    def position(self) -> tuple[int, int] | None:
        if not self._controller:
            return None
        pos = self._controller.position
        return (int(pos[0]), int(pos[1]))

    def recent_clicks(self, max_age_seconds: float) -> list[ClickEvent]:
        now = time.monotonic()
        with self._lock:
            self._clicks = [c for c in self._clicks if now - c.started_at <= max_age_seconds]
            return list(self._clicks)

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()


def draw_mouse_highlight(
    image: Image.Image,
    monitor_left: int,
    monitor_top: int,
    tracker: MouseTracker,
    settings: MouseHighlightSettings,
) -> Image.Image:
    """Retorna uma nova imagem com o destaque do cursor desenhado, ou a
    imagem original sem alterações se o modo estiver desligado ou a posição
    do cursor não puder ser lida."""
    if not settings.enabled:
        return image

    position = tracker.position()
    if position is None:
        return image

    local_x = position[0] - monitor_left
    local_y = position[1] - monitor_top
    cursor_visible = 0 <= local_x < image.width and 0 <= local_y < image.height

    duration = max(0.05, settings.click_duration_ms / 1000.0)
    clicks = tracker.recent_clicks(duration) if settings.click_effects else []
    if not cursor_visible and not clicks:
        return image

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    radius = max(4, settings.size // 2)
    alpha = int(max(0.0, min(1.0, settings.opacity)) * 255)

    if cursor_visible:
        draw.ellipse(
            [local_x - radius, local_y - radius, local_x + radius, local_y + radius],
            fill=(255, 210, 0, alpha),
            outline=(255, 255, 255, min(255, alpha + 60)),
            width=2,
        )

    for click in clicks:
        progress = min(1.0, (time.monotonic() - click.started_at) / duration)
        ring_alpha = int((1.0 - progress) * 220)
        if ring_alpha <= 0:
            continue
        ring_radius = int(radius + progress * radius * 3)
        click_x = click.x - monitor_left
        click_y = click.y - monitor_top
        draw.ellipse(
            [click_x - ring_radius, click_y - ring_radius, click_x + ring_radius, click_y + ring_radius],
            outline=(255, 90, 90, ring_alpha),
            width=3,
        )

    base = image.convert("RGBA")
    combined = Image.alpha_composite(base, overlay)
    return combined.convert("RGB")
