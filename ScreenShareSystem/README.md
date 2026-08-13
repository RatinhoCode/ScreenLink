# ScreenShareSystem

Compartilhamento de tela **PC -> Celular Android** em rede local.

- `server/` — servidor Python (captura a tela do PC e transmite via WebSocket).
- `android-app/` — app Android nativo em Kotlin (Android Studio) que recebe o stream e exibe.

## Como funciona

1. O PC roda `server/server.py`, que abre um servidor WebSocket na porta `8765`.
2. O celular (na mesma rede Wi-Fi/local) conecta em `ws://<IP-DO-PC>:8765`.
3. Ao conectar, o servidor envia a lista de monitores disponíveis.
4. O app escolhe um monitor e um FPS (30 ou 60) e o servidor passa a enviar frames JPEG binários naquele FPS.
5. O app pode abrir várias abas (botão **+**) para acompanhar mais de um monitor ao mesmo tempo — cada aba usa sua própria conexão WebSocket.
6. Se a conexão não for concluída em 60 segundos, o app cancela a tentativa (contagem regressiva visível na tela).
7. O botão **🖱️ Mostrar Mouse** liga/desliga um destaque visual em torno do cursor (desenhado no servidor, sobre o próprio frame capturado) — útil para gravações e tutoriais. Toque e segure o botão para ajustar tamanho, transparência, duração da animação de clique e ativar/desativar os efeitos de clique.

## Protocolo (JSON de controle + frames binários)

Cliente -> Servidor:
```json
{"type": "hello"}
{"type": "start", "monitor": 1, "fps": 30}
{"type": "set_fps", "fps": 60}
{"type": "stop"}
{"type": "mouse_highlight", "enabled": true, "size": 40, "opacity": 0.55, "click_duration_ms": 400, "click_effects": true}
{"type": "ping"}
```

Servidor -> Cliente:
```json
{"type": "monitors", "monitors": [{"index": 1, "width": 1920, "height": 1080}]}
{"type": "started", "monitor": 1, "fps": 30}
{"type": "mouse_highlight_ack", "enabled": true, "size": 40, "opacity": 0.55, "click_duration_ms": 400, "click_effects": true}
{"type": "pong"}
```
Frames de tela são enviados como mensagens **binárias** WebSocket (JPEG puro, já com o destaque do mouse desenhado quando o modo está ligado).

O destaque do mouse é por sessão/aba: cada conexão WebSocket liga/desliga e ajusta o seu próprio destaque independentemente, mesmo compartilhando o mesmo cursor físico do PC (a posição do cursor vem de um único listener global no servidor, via `pynput`).

## Rodando o servidor

```bash
cd server
pip install -r requirements.txt
python server.py
```

O servidor imprime o IP local e a porta para digitar no app.

## Abrindo o app Android

Abra a pasta `android-app/` no Android Studio (Open an existing project) e rode em um dispositivo/emulador na mesma rede do PC.
