"""PC UI Mode — painel flutuante nativo sobre a área de trabalho do Windows.

Sem navegador, sem Web API, sem webcam, sem segunda tela virtual: é uma
janela Tkinter comum (biblioteca padrão do Python), a mesma técnica já
usada em monitor_picker.py. O atalho de teclado global reaproveita pynput
(já é dependência do projeto, usado em mouse_overlay.py).

A janela roda na sua própria thread com sua própria mainloop do Tk, porque
o resto do servidor usa asyncio. A comunicação entre as duas threads é só
por uma queue.Queue (thread-safe): o servidor empurra snapshots de status,
e o atalho global empurra um pedido de "mostrar/esconder" — tudo é
processado dentro da thread da UI, nunca mexendo em widgets Tk de fora.
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from dataclasses import dataclass

from pynput import keyboard

BG = "#101318"
SURFACE = "#1b1f27"
SURFACE_2 = "#232833"
ACCENT = "#4c8dff"
TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#9aa4b2"

DEFAULT_HOTKEY = "<ctrl>+<alt>+u"
MIN_WIDTH, MIN_HEIGHT = 230, 150
DEFAULT_WIDTH, DEFAULT_HEIGHT = 260, 200


@dataclass
class ServerStatus:
    monitor_label: str = "—"
    clients: int = 0
    streaming_clients: int = 0
    fps: int = 0


class PCUIOverlay:
    """Painel flutuante do PC UI Mode. Chame start() para abrir."""

    def __init__(self, hotkey: str = DEFAULT_HOTKEY) -> None:
        self._hotkey = hotkey
        self._queue: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name="PCUIOverlay")
        self._hotkey_listener: keyboard.GlobalHotKeys | None = None

    def start(self) -> None:
        """Inicia a thread da UI e espera a janela ficar pronta."""
        self._thread.start()
        self._ready.wait(timeout=5)

    def push_status(self, status: ServerStatus) -> None:
        self._queue.put(("status", status))

    def stop(self) -> None:
        self._queue.put(("quit", None))

    # -- roda inteiramente na thread da UI ------------------------------

    def _run(self) -> None:
        self.root = tk.Tk()
        self.root.title("PC UI Mode")
        self.root.overrideredirect(True)  # sem moldura do SO -> visual próprio, moderno
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.94)
        self.root.configure(bg=SURFACE)
        self.root.geometry(f"{DEFAULT_WIDTH}x{DEFAULT_HEIGHT}+40+40")

        self._always_on_top = tk.BooleanVar(value=True)
        self._opacity_pct = tk.IntVar(value=94)
        self._minimized = False
        self._visible = True
        self._expanded_height = DEFAULT_HEIGHT

        self._build_ui()
        self._register_hotkey()

        self.root.after(200, self._poll_queue)
        self._ready.set()
        self.root.mainloop()

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, bg=SURFACE_2, height=32, cursor="fleur")
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        title = tk.Label(
            header, text="🖥️  PC UI Mode", bg=SURFACE_2, fg=TEXT_PRIMARY,
            font=("Segoe UI", 9, "bold"),
        )
        title.pack(side="left", padx=10)

        btn_close = tk.Label(
            header, text="✕", bg=SURFACE_2, fg=TEXT_SECONDARY,
            font=("Segoe UI", 10, "bold"), cursor="hand2",
        )
        btn_close.pack(side="right", padx=(0, 8))
        btn_close.bind("<Button-1>", lambda _e: self.hide())

        self._min_button = tk.Label(
            header, text="—", bg=SURFACE_2, fg=TEXT_SECONDARY,
            font=("Segoe UI", 11, "bold"), cursor="hand2",
        )
        self._min_button.pack(side="right", padx=(0, 4))
        self._min_button.bind("<Button-1>", lambda _e: self.toggle_minimize())

        for widget in (header, title):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._on_drag)

        self.body = tk.Frame(self.root, bg=SURFACE)
        self.body.pack(fill="both", expand=True, padx=12, pady=10)

        self.status_label = tk.Label(
            self.body, text="Monitor: —", bg=SURFACE, fg=TEXT_PRIMARY,
            font=("Segoe UI", 9), justify="left", anchor="w",
        )
        self.status_label.pack(fill="x")

        self.clients_label = tk.Label(
            self.body, text="Sem clientes conectados", bg=SURFACE, fg=TEXT_SECONDARY,
            font=("Segoe UI", 9), anchor="w",
        )
        self.clients_label.pack(fill="x", pady=(2, 10))

        top_row = tk.Frame(self.body, bg=SURFACE)
        top_row.pack(fill="x", pady=2)
        tk.Label(
            top_row, text="Sempre visível", bg=SURFACE, fg=TEXT_PRIMARY, font=("Segoe UI", 9),
        ).pack(side="left")
        tk.Checkbutton(
            top_row, variable=self._always_on_top, command=self._apply_topmost,
            bg=SURFACE, activebackground=SURFACE, selectcolor=SURFACE_2,
            fg=ACCENT, bd=0, highlightthickness=0, cursor="hand2",
        ).pack(side="right")

        tk.Label(
            self.body, text="Transparência", bg=SURFACE, fg=TEXT_PRIMARY, font=("Segoe UI", 9),
        ).pack(fill="x", pady=(8, 0), anchor="w")
        tk.Scale(
            self.body, from_=40, to=100, orient="horizontal", variable=self._opacity_pct,
            bg=SURFACE, fg=TEXT_SECONDARY, troughcolor=SURFACE_2, highlightthickness=0,
            bd=0, showvalue=False, command=self._apply_opacity, length=200,
        ).pack(fill="x")

        hint = tk.Label(
            self.root, text=f"{self._hotkey.replace('<', '').replace('>', '').upper()} mostra/esconde",
            bg=SURFACE, fg=TEXT_SECONDARY, font=("Segoe UI", 7),
        )
        hint.pack(side="bottom", pady=(0, 4))

        grip = tk.Label(self.root, text="◢", bg=SURFACE, fg=TEXT_SECONDARY, cursor="size_nw_se")
        grip.place(relx=1.0, rely=1.0, anchor="se")
        grip.bind("<ButtonPress-1>", self._start_resize)
        grip.bind("<B1-Motion>", self._on_resize)

    # -- arrastar / redimensionar ---------------------------------------

    def _start_drag(self, event: tk.Event) -> None:
        self._drag_origin = (event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y())

    def _on_drag(self, event: tk.Event) -> None:
        x0, y0, wx, wy = self._drag_origin
        dx, dy = event.x_root - x0, event.y_root - y0
        self.root.geometry(f"+{wx + dx}+{wy + dy}")

    def _start_resize(self, event: tk.Event) -> None:
        self._resize_origin = (event.x_root, event.y_root, self.root.winfo_width(), self.root.winfo_height())

    def _on_resize(self, event: tk.Event) -> None:
        x0, y0, w0, h0 = self._resize_origin
        dx, dy = event.x_root - x0, event.y_root - y0
        new_w = max(MIN_WIDTH, w0 + dx)
        new_h = max(MIN_HEIGHT, h0 + dy)
        self.root.geometry(f"{new_w}x{new_h}")
        if not self._minimized:
            self._expanded_height = new_h

    # -- minimizar / mostrar / esconder ----------------------------------

    def toggle_minimize(self) -> None:
        self._minimized = not self._minimized
        width = self.root.winfo_width()
        if self._minimized:
            self.body.pack_forget()
            self._min_button.configure(text="▢")
            self.root.geometry(f"{width}x32")
        else:
            self.body.pack(fill="both", expand=True, padx=12, pady=10)
            self._min_button.configure(text="—")
            self.root.geometry(f"{width}x{self._expanded_height}")

    def show(self) -> None:
        self._visible = True
        self.root.deiconify()
        self.root.lift()
        # troca o atributo -topmost num tick separado do deiconify: fazer
        # os dois juntos às vezes falha silenciosamente logo após withdraw()
        self.root.after(10, lambda: self.root.attributes("-topmost", self._always_on_top.get()))

    def hide(self) -> None:
        self._visible = False
        self.root.withdraw()

    def toggle_visibility(self) -> None:
        # não usa root.state(): janelas overrideredirect não reportam
        # "withdrawn" de forma confiável, então guardamos o estado à parte
        if self._visible:
            self.hide()
        else:
            self.show()

    # -- controles ---------------------------------------------------------

    def _apply_topmost(self) -> None:
        self.root.attributes("-topmost", self._always_on_top.get())

    def _apply_opacity(self, value: str) -> None:
        self.root.attributes("-alpha", int(value) / 100)

    def _register_hotkey(self) -> None:
        def on_hotkey() -> None:
            self._queue.put(("toggle_visibility", None))

        try:
            self._hotkey_listener = keyboard.GlobalHotKeys({self._hotkey: on_hotkey})
            self._hotkey_listener.start()
        except Exception:
            # atalho global pode falhar em ambientes restritos; o painel
            # continua funcionando normalmente, só sem o atalho
            self._hotkey_listener = None

    # -- fila de eventos vindos de outras threads ------------------------

    def _poll_queue(self) -> None:
        quitting = False
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "status":
                    self._render_status(payload)
                elif kind == "toggle_visibility":
                    self.toggle_visibility()
                elif kind == "quit":
                    quitting = True
                    self._shutdown()
                    break
        except queue.Empty:
            pass
        except Exception as exc:
            # nunca deixa uma falha ao processar um evento matar o loop de
            # eventos por completo (senão o painel para de responder pra
            # sempre a partir daí, inclusive ao atalho de teclado)
            print(f"[pc_ui] erro ao processar evento: {exc}")
        if not quitting:
            self.root.after(200, self._poll_queue)

    def _render_status(self, status: ServerStatus) -> None:
        self.status_label.configure(text=f"Monitor: {status.monitor_label}")
        if status.clients == 0:
            self.clients_label.configure(text="Sem clientes conectados")
        else:
            self.clients_label.configure(
                text=f"{status.clients} cliente(s)  •  {status.streaming_clients} assistindo  •  {status.fps} FPS"
            )

    def _shutdown(self) -> None:
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
        self.root.destroy()


def main() -> None:
    """Teste standalone: sobe só o painel, sem o servidor de verdade."""
    import time

    overlay = PCUIOverlay()
    overlay.start()
    overlay.push_status(ServerStatus(monitor_label="Monitor 1 (teste)", clients=2, streaming_clients=1, fps=30))
    try:
        while overlay._thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        overlay.stop()


if __name__ == "__main__":
    main()
