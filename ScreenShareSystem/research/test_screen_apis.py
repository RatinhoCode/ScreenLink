"""Teste prático e isolado das opções gratuitas de captura/deteccao de tela.

Não importa nem altera nada do server/ existente — é só um comparativo
executável para decidir qual biblioteca usar. Compara:

  1. mss          -> já usado no projeto (server/screen_capture.py)
  2. screeninfo    -> alternativa mais leve, só detecção (sem captura)
  3. dxcam         -> captura via DirectX Desktop Duplication (Windows), mais rápida

Uso:
    python test_screen_apis.py                 # lista monitores com as 3 libs
    python test_screen_apis.py --capture 1      # captura o monitor 1 com mss e salva preview
    python test_screen_apis.py --mouse          # mostra a posição atual do cursor (pynput)
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "preview_output"


def test_mss() -> None:
    print("\n=== 1) mss (já usado no projeto) ===")
    try:
        import mss
    except ImportError as exc:
        print(f"  [ERRO] mss não está instalado: {exc}")
        return

    with mss.mss() as sct:
        monitors = sct.monitors[1:]  # índice 0 = todos combinados
        if not monitors:
            print("  [ERRO] Nenhum monitor detectado pelo mss.")
            return
        for i, m in enumerate(monitors, start=1):
            print(f"  Monitor {i} — {m['width']}x{m['height']}  (posição: {m['left']},{m['top']})")


def test_screeninfo() -> None:
    print("\n=== 2) screeninfo (alternativa leve, só detecção) ===")
    try:
        import screeninfo
    except ImportError as exc:
        print(f"  [ERRO] screeninfo não está instalado: {exc}")
        return

    try:
        monitors = screeninfo.get_monitors()
    except screeninfo.common.ScreenInfoError as exc:
        print(f"  [ERRO] screeninfo não conseguiu enumerar monitores: {exc}")
        return

    if not monitors:
        print("  [ERRO] Nenhum monitor detectado pelo screeninfo.")
        return
    for i, m in enumerate(monitors, start=1):
        primary = " (primário)" if getattr(m, "is_primary", False) else ""
        print(f"  Monitor {i} — {m.width}x{m.height}  (posição: {m.x},{m.y}){primary}")


def test_dxcam() -> None:
    print("\n=== 3) dxcam (captura via DirectX Desktop Duplication) ===")
    try:
        import dxcam
    except ImportError as exc:
        print(f"  [ERRO] dxcam não está instalado: {exc}")
        return

    try:
        devices = dxcam.output_info()
    except Exception as exc:  # dxcam levanta exceções genéricas em GPUs/drivers sem suporte
        print(f"  [ERRO] dxcam não conseguiu consultar os monitores: {exc}")
        print("  (Isso é uma limitação conhecida em algumas GPUs/drivers — ver análise.)")
        return

    print(devices.strip() if isinstance(devices, str) else devices)


def capture_with_mss(monitor_index: int) -> None:
    print(f"\n=== Capturando o Monitor {monitor_index} com mss ===")
    try:
        import mss
        from PIL import Image
    except ImportError as exc:
        print(f"  [ERRO] Dependência faltando: {exc}")
        return

    with mss.mss() as sct:
        monitors = sct.monitors
        if monitor_index < 1 or monitor_index >= len(monitors):
            print(f"  [ERRO] Monitor {monitor_index} não existe. "
                  f"Monitores disponíveis: 1..{len(monitors) - 1}")
            return

        raw = sct.grab(monitors[monitor_index])
        image = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        OUTPUT_DIR.mkdir(exist_ok=True)
        out_path = OUTPUT_DIR / f"preview_monitor_{monitor_index}.png"
        image.save(out_path)
        print(f"  OK: preview salvo em {out_path} ({image.width}x{image.height})")


def test_mouse() -> None:
    print("\n=== Detecção do mouse (pynput, já usado no projeto) ===")
    try:
        from pynput import mouse
    except ImportError as exc:
        print(f"  [ERRO] pynput não está instalado: {exc}")
        return

    controller = mouse.Controller()
    print("  Posição atual do cursor:", controller.position)
    print("  Movendo o mouse nos próximos 3s para observar variação...")
    for _ in range(3):
        time.sleep(1)
        print("  Posição:", controller.position)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=int, metavar="N", help="Captura o monitor N com mss")
    parser.add_argument("--mouse", action="store_true", help="Testa detecção da posição do mouse")
    args = parser.parse_args()

    if args.capture is not None:
        capture_with_mss(args.capture)
        return
    if args.mouse:
        test_mouse()
        return

    print("Comparativo de detecção de monitores (Windows)")
    print("=" * 50)
    test_mss()
    test_screeninfo()
    test_dxcam()


if __name__ == "__main__":
    sys.exit(main() or 0)
