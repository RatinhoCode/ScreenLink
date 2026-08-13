"""Seletor nativo de monitor, mostrado uma vez ao iniciar o servidor.

Sem navegador, sem Web API — só tkinter (biblioteca padrão do Python) e a
lista de monitores já detectada via mss. Mesma técnica validada em
research/monitor_capture_gui.py.

O operador do PC escolhe qual monitor físico fica disponível para o app
Android, e se o PC UI Mode (painel flutuante, ver pc_ui.py) deve subir
junto. Essa escolha é feita uma vez, localmente, antes de o servidor
aceitar qualquer conexão de rede.
"""
from __future__ import annotations

import tkinter as tk

from screen_capture import MonitorInfo

BG = "#101318"
SURFACE = "#1b1f27"
ACCENT = "#4c8dff"
TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#9aa4b2"


def pick_monitor(monitors: list[MonitorInfo]) -> tuple[int | None, bool]:
    """Mostra a janela de seleção e bloqueia até o operador escolher.

    Retorna (índice do monitor escolhido, se o PC UI Mode deve ligar).
    O índice vem None se a janela foi fechada sem confirmar (cancelado).
    Se só existir um monitor, retorna esse índice direto com PC UI Mode
    ligado por padrão, sem abrir janela nenhuma.
    """
    if not monitors:
        return None, False
    if len(monitors) == 1:
        return monitors[0].index, True

    result: dict[str, object] = {"choice": None, "ui_mode": True}

    root = tk.Tk()
    root.title("Tela para captura")
    root.configure(bg=BG)
    root.resizable(False, False)

    tk.Label(
        root,
        text="🖥️  Escolha a tela para compartilhar",
        font=("Segoe UI", 12, "bold"),
        bg=BG,
        fg=TEXT_PRIMARY,
    ).pack(padx=20, pady=(18, 4), anchor="w")

    tk.Label(
        root,
        text="Só esta tela ficará disponível para o app Android.",
        font=("Segoe UI", 9),
        bg=BG,
        fg=TEXT_SECONDARY,
    ).pack(padx=20, pady=(0, 10), anchor="w")

    selected = tk.IntVar(value=monitors[0].index)
    options = tk.Frame(root, bg=SURFACE)
    options.pack(padx=20, pady=4, fill="x")

    for m in monitors:
        tk.Radiobutton(
            options,
            text=f"Monitor {m.index}  —  {m.width}x{m.height}",
            variable=selected,
            value=m.index,
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

    ui_mode = tk.BooleanVar(value=True)
    ui_mode_row = tk.Frame(root, bg=BG)
    ui_mode_row.pack(padx=20, pady=(12, 0), fill="x")
    tk.Checkbutton(
        ui_mode_row,
        text="Ativar PC UI Mode (painel flutuante no desktop)",
        variable=ui_mode,
        bg=BG,
        activebackground=BG,
        selectcolor=SURFACE,
        fg=TEXT_PRIMARY,
        font=("Segoe UI", 9),
        bd=0,
        highlightthickness=0,
        cursor="hand2",
    ).pack(anchor="w")

    def confirm() -> None:
        result["choice"] = selected.get()
        result["ui_mode"] = ui_mode.get()
        root.destroy()

    def cancel() -> None:
        result["choice"] = None
        root.destroy()

    buttons = tk.Frame(root, bg=BG)
    buttons.pack(padx=20, pady=16, fill="x")

    tk.Button(
        buttons,
        text="Cancelar",
        command=cancel,
        bg=SURFACE,
        fg=TEXT_PRIMARY,
        relief="flat",
        padx=12,
        pady=8,
        cursor="hand2",
    ).pack(side="left", expand=True, fill="x", padx=(0, 6))

    tk.Button(
        buttons,
        text="Compartilhar este monitor",
        command=confirm,
        bg=ACCENT,
        fg="white",
        font=("Segoe UI", 10, "bold"),
        relief="flat",
        padx=12,
        pady=8,
        cursor="hand2",
    ).pack(side="left", expand=True, fill="x", padx=(6, 0))

    root.protocol("WM_DELETE_WINDOW", cancel)
    root.eval("tk::PlaceWindow . center")
    root.attributes("-topmost", True)
    root.after(200, lambda: root.attributes("-topmost", False))
    root.mainloop()

    return result["choice"], bool(result["ui_mode"])
