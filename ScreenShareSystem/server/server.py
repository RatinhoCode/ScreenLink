"""Servidor de compartilhamento de tela via WebSocket.

Ao iniciar, o operador do PC escolhe (numa janela nativa, sem navegador)
qual monitor físico fica disponível para o app Android — ver
monitor_picker.py. Só esse monitor é exposto na rede.

Cada cliente conectado tem sua própria sessão de FPS (30 ou 60) e passa a
receber frames JPEG binários naquela taxa. Múltiplos clientes (ou várias
abas do mesmo app) podem conectar ao mesmo tempo, todos assistindo ao
mesmo monitor escolhido na inicialização.

Se o cliente não estiver recebendo stream (streaming=False) e nenhuma
mensagem chegar dele por IDLE_TIMEOUT_SECONDS, a conexão é encerrada por
inatividade. Enquanto o stream está ativo, receber frames continuamente já
conta como atividade — a conexão não cai só porque o app não manda nada de
volta enquanto o usuário está apenas assistindo.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import socket

import websockets
from websockets.asyncio.server import ServerConnection

from monitor_picker import pick_monitor
from mouse_overlay import MouseHighlightSettings, MouseTracker
from pc_ui import PCUIOverlay, ServerStatus
from screen_capture import ScreenCapture

HOST = "0.0.0.0"
PORT = 8765
IDLE_TIMEOUT_SECONDS = 60
DEFAULT_FPS = 30
MIN_FPS = 1
MAX_FPS = 60
UI_STATUS_INTERVAL_SECONDS = 1

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("screenshare")

# Definidos em __main__, antes do servidor subir (ver resolve_selected_monitor).
SELECTED_MONITOR: int | None = None
ui_overlay: PCUIOverlay | None = None

# Sessões atualmente conectadas, só para alimentar o status do PC UI Mode.
active_sessions: set[ClientSession] = set()

# Há apenas um cursor físico no PC, então um único MouseTracker (um só
# listener pynput) é compartilhado por todas as sessões/clientes.
mouse_tracker = MouseTracker()


class ClientSession:
    def __init__(self, ws: ServerConnection):
        self.ws = ws
        self.capture = ScreenCapture()
        self.monitor_index: int | None = None
        self.fps = DEFAULT_FPS
        self.streaming = False
        self.mouse_highlight = MouseHighlightSettings()
        self.last_activity = asyncio.get_event_loop().time()

    def touch(self) -> None:
        self.last_activity = asyncio.get_event_loop().time()

    def close(self) -> None:
        self.capture.close()


async def send_monitor_list(session: ClientSession) -> None:
    # só o monitor escolhido pelo operador do PC na inicialização é exposto
    monitors = [
        {"index": m.index, "width": m.width, "height": m.height}
        for m in session.capture.list_monitors()
        if m.index == SELECTED_MONITOR
    ]
    await session.ws.send(json.dumps({"type": "monitors", "monitors": monitors}))


async def handle_message(session: ClientSession, raw: str) -> None:
    try:
        message = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("Mensagem de controle inválida ignorada: %r", raw)
        return

    msg_type = message.get("type")

    if msg_type == "hello":
        await send_monitor_list(session)

    elif msg_type == "start":
        # ignora qualquer monitor pedido pelo cliente: só o monitor
        # escolhido pelo operador do PC pode ser compartilhado
        session.monitor_index = SELECTED_MONITOR
        session.fps = _clamp_fps(message.get("fps", DEFAULT_FPS))
        session.streaming = True
        await session.ws.send(json.dumps({
            "type": "started", "monitor": session.monitor_index, "fps": session.fps,
        }))

    elif msg_type == "set_fps":
        session.fps = _clamp_fps(message.get("fps", session.fps))

    elif msg_type == "stop":
        session.streaming = False

    elif msg_type == "mouse_highlight":
        _apply_mouse_highlight(session.mouse_highlight, message)
        await session.ws.send(json.dumps({
            "type": "mouse_highlight_ack", **session.mouse_highlight.as_dict(),
        }))

    elif msg_type == "ping":
        await session.ws.send(json.dumps({"type": "pong"}))

    else:
        log.warning("Tipo de mensagem desconhecido: %s", msg_type)


def _clamp_fps(value) -> int:
    try:
        fps = int(value)
    except (TypeError, ValueError):
        return DEFAULT_FPS
    return max(MIN_FPS, min(MAX_FPS, fps))


def _apply_mouse_highlight(settings: MouseHighlightSettings, message: dict) -> None:
    if "enabled" in message:
        settings.enabled = bool(message["enabled"])
    if "size" in message:
        try:
            settings.size = max(8, min(200, int(message["size"])))
        except (TypeError, ValueError):
            pass
    if "opacity" in message:
        try:
            settings.opacity = max(0.05, min(1.0, float(message["opacity"])))
        except (TypeError, ValueError):
            pass
    if "click_duration_ms" in message:
        try:
            settings.click_duration_ms = max(100, min(3000, int(message["click_duration_ms"])))
        except (TypeError, ValueError):
            pass
    if "click_effects" in message:
        settings.click_effects = bool(message["click_effects"])


async def stream_loop(session: ClientSession) -> None:
    while True:
        if session.streaming and session.monitor_index is not None:
            try:
                frame = session.capture.grab_jpeg(
                    session.monitor_index,
                    mouse_tracker=mouse_tracker,
                    highlight_settings=session.mouse_highlight,
                )
                await session.ws.send(frame)
            except ValueError as exc:
                log.warning("Erro ao capturar monitor: %s", exc)
                session.streaming = False
            except websockets.ConnectionClosed:
                return
        await asyncio.sleep(1 / session.fps)


async def idle_watchdog(session: ClientSession) -> None:
    while True:
        await asyncio.sleep(1)
        if session.streaming:
            # recebendo frames continuamente é atividade real, mesmo que o
            # cliente não mande nenhuma mensagem de controle enquanto só
            # assiste ao stream — não derruba por "inatividade" nesse caso
            session.touch()
            continue
        idle_for = asyncio.get_event_loop().time() - session.last_activity
        if idle_for >= IDLE_TIMEOUT_SECONDS:
            log.info("Cliente inativo por %.0fs, encerrando conexão.", idle_for)
            await session.ws.close(code=1000, reason="idle timeout")
            return


async def receive_loop(session: ClientSession) -> None:
    async for raw in session.ws:
        session.touch()
        if isinstance(raw, (bytes, bytearray)):
            continue  # o servidor não espera binário do cliente
        await handle_message(session, raw)


async def handler(ws: ServerConnection) -> None:
    peer = ws.remote_address
    log.info("Cliente conectado: %s", peer)
    session = ClientSession(ws)
    active_sessions.add(session)

    tasks = [
        asyncio.create_task(receive_loop(session)),
        asyncio.create_task(stream_loop(session)),
        asyncio.create_task(idle_watchdog(session)),
    ]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        active_sessions.discard(session)
        session.close()
        log.info("Cliente desconectado: %s", peer)


async def ui_status_loop() -> None:
    """Mantém o painel do PC UI Mode com o status ao vivo do servidor."""
    if ui_overlay is None:
        return
    monitor_label = f"Monitor {SELECTED_MONITOR}" if SELECTED_MONITOR is not None else "—"
    while True:
        streaming = [s for s in active_sessions if s.streaming]
        ui_overlay.push_status(ServerStatus(
            monitor_label=monitor_label,
            clients=len(active_sessions),
            streaming_clients=len(streaming),
            fps=max((s.fps for s in streaming), default=0),
        ))
        await asyncio.sleep(UI_STATUS_INTERVAL_SECONDS)


def resolve_selected_monitor(cli_monitor: int | None) -> tuple[int, bool]:
    """Decide qual monitor será compartilhado e se o PC UI Mode liga junto.

    Usa --monitor se informado (PC UI Mode ligado por padrão nesse caso),
    detecta automático se só existir um monitor, ou pergunta ao operador
    via monitor_picker (janela nativa, sem navegador)."""
    capture = ScreenCapture()
    try:
        monitors = capture.list_monitors()
    finally:
        capture.close()

    if not monitors:
        log.error("Nenhum monitor foi detectado neste PC.")
        raise SystemExit(1)

    if cli_monitor is not None:
        if not any(m.index == cli_monitor for m in monitors):
            disponiveis = ", ".join(str(m.index) for m in monitors)
            log.error("Monitor %d não existe. Disponíveis: %s", cli_monitor, disponiveis)
            raise SystemExit(1)
        return cli_monitor, True

    chosen, enable_ui_mode = pick_monitor(monitors)
    if chosen is None:
        log.info("Nenhum monitor selecionado, encerrando.")
        raise SystemExit(0)
    return chosen, enable_ui_mode


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


async def main() -> None:
    tasks = []
    if ui_overlay is not None:
        tasks.append(asyncio.create_task(ui_status_loop()))
    try:
        async with websockets.serve(handler, HOST, PORT, max_size=None):
            log.info("Servidor de compartilhamento de tela rodando.")
            log.info("Monitor compartilhado: %d", SELECTED_MONITOR)
            log.info("Conecte o app Android em: ws://%s:%d", local_ip(), PORT)
            await asyncio.Future()  # roda para sempre
    finally:
        for task in tasks:
            task.cancel()
        if ui_overlay is not None:
            ui_overlay.stop()
        mouse_tracker.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor de compartilhamento de tela")
    parser.add_argument(
        "--monitor", type=int, default=None,
        help="Pula a janela de seleção e usa direto este índice de monitor",
    )
    parser.add_argument(
        "--no-ui", action="store_true",
        help="Não sobe o painel PC UI Mode, mesmo que a caixinha estivesse marcada",
    )
    args = parser.parse_args()

    SELECTED_MONITOR, enable_ui_mode = resolve_selected_monitor(args.monitor)
    log.info("Monitor selecionado para compartilhamento: %d", SELECTED_MONITOR)

    if enable_ui_mode and not args.no_ui:
        ui_overlay = PCUIOverlay()
        ui_overlay.start()
        log.info("PC UI Mode ativo (Ctrl+Alt+U mostra/esconde o painel).")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Servidor encerrado.")
