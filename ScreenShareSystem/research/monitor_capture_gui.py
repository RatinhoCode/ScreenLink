"""App desktop nativo para captura de monitor físico — sem navegador.

100% local: tkinter (biblioteca padrão do Python) para a interface e mss
(MIT, já usado em server/screen_capture.py) para detectar e capturar os
monitores reais conectados ao Windows via GDI (EnumDisplayMonitors).

Não usa browser, não usa nenhuma Web API, não sobe servidor.

Uso:
    python monitor_capture_gui.py
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import mss
from PIL import Image, ImageTk

OUTPUT_DIR = Path(__file__).parent / "preview_output"

BG = "#101318"
SURFACE = "#1b1f27"
ACCENT = "#4c8dff"
TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#9aa4b2"
ERROR = "#ff6b6b"


class MonitorCaptureApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Tela para captura")
        self.configure(bg=BG)
        self.resizable(False, False)

        self.preview_photo: ImageTk.PhotoImage | None = None  # evita coleta pelo GC

        try:
            self.monitors = self._detect_monitors()
        except Exception as exc:
            self.monitors = []
            self._detect_error = str(exc)
        else:
            self._detect_error = None

        self.selected = tk.IntVar(value=1 if self.monitors else 0)
        self._build_ui()

    def _detect_monitors(self) -> list[dict]:
        with mss.mss() as sct:
            # índice 0 é o monitor "virtual" (todos combinados); os físicos
            # começam em 1, mesma convenção usada no servidor do projeto
            return sct.monitors[1:]

    def _build_ui(self) -> None:
        tk.Label(
            self,
            text="🖥️  Tela para captura",
            font=("Segoe UI", 13, "bold"),
            bg=BG,
            fg=TEXT_PRIMARY,
        ).pack(padx=20, pady=(16, 8), anchor="w")

        if self._detect_error:
            tk.Label(
                self,
                text=f"Erro ao detectar monitores:\n{self._detect_error}",
                bg=BG,
                fg=ERROR,
                justify="left",
            ).pack(padx=20, pady=8)
            return

        if not self.monitors:
            tk.Label(
                self,
                text="Nenhum monitor físico foi detectado.",
                bg=BG,
                fg=ERROR,
            ).pack(padx=20, pady=8)
            return

        options = tk.Frame(self, bg=SURFACE)
        options.pack(padx=20, pady=4, fill="x")

        for i, m in enumerate(self.monitors, start=1):
            label = f"Monitor {i}  —  {m['width']}x{m['height']}"
            tk.Radiobutton(
                options,
                text=label,
                variable=self.selected,
                value=i,
                bg=SURFACE,
                fg=TEXT_PRIMARY,
                selectcolor=BG,
                activebackground=SURFACE,
                activeforeground=TEXT_PRIMARY,
                font=("Segoe UI", 10),
                anchor="w",
                padx=10,
                pady=6,
            ).pack(fill="x")

        tk.Button(
            self,
            text="Capturar Monitor",
            command=self.on_capture,
            bg=ACCENT,
            fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            activebackground="#3a73d8",
            activeforeground="white",
            cursor="hand2",
            padx=14,
            pady=10,
        ).pack(padx=20, pady=14, fill="x")

        self.status_label = tk.Label(self, text="", bg=BG, fg=TEXT_SECONDARY, wraplength=360, justify="left")
        self.status_label.pack(padx=20, pady=(0, 8), anchor="w")

        self.preview_label = tk.Label(self, bg="black")
        self.preview_label.pack(padx=20, pady=(0, 20))

    def on_capture(self) -> None:
        index = self.selected.get()
        try:
            with mss.mss() as sct:
                monitors = sct.monitors
                if index < 1 or index >= len(monitors):
                    raise ValueError(f"Monitor {index} não existe (detectados: 1..{len(monitors) - 1}).")
                raw = sct.grab(monitors[index])
                image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        except Exception as exc:
            messagebox.showerror("Erro ao capturar", f"Não foi possível capturar o Monitor {index}:\n{exc}")
            return

        OUTPUT_DIR.mkdir(exist_ok=True)
        out_path = OUTPUT_DIR / f"preview_monitor_{index}.png"
        image.save(out_path)

        thumb = image.copy()
        thumb.thumbnail((420, 240))
        self.preview_photo = ImageTk.PhotoImage(thumb)
        self.preview_label.configure(image=self.preview_photo)

        self.status_label.configure(
            text=f"Capturado: Monitor {index} ({image.width}x{image.height}) → {out_path}"
        )


if __name__ == "__main__":
    app = MonitorCaptureApp()
    app.mainloop()
