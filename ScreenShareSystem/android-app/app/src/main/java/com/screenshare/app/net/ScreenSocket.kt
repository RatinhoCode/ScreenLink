package com.screenshare.app.net

import android.os.CountDownTimer
import android.os.Handler
import android.os.Looper
import com.screenshare.app.model.MonitorInfo
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Uma conexão WebSocket com o servidor de compartilhamento de tela.
 * Todos os callbacks do [Listener] são entregues na thread principal.
 */
class ScreenSocket(private val listener: Listener) {

    interface Listener {
        fun onConnecting(secondsLeft: Int) {}
        fun onMonitors(monitors: List<MonitorInfo>) {}
        fun onStarted(monitor: Int, fps: Int) {}
        fun onFrame(jpeg: ByteArray) {}
        fun onTimeout() {}
        fun onError(message: String) {}
        fun onClosed() {}
    }

    companion object {
        private const val CONNECT_TIMEOUT_MS = 60_000L

        // bem menor que o IDLE_TIMEOUT_SECONDS (60s) do servidor: garante
        // que a conexão nunca pareça "inativa" para o servidor, mesmo fora
        // do streaming (ex: parado na tela de seleção de monitor)
        private const val APP_PING_INTERVAL_MS = 20_000L

        private val client = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(0, TimeUnit.MILLISECONDS) // stream contínuo
            .pingInterval(20, TimeUnit.SECONDS)
            .build()
    }

    private val mainHandler = Handler(Looper.getMainLooper())
    private var webSocket: WebSocket? = null
    private var countdownTimer: CountDownTimer? = null
    private var opened = false
    private var manuallyClosed = false

    private val pingRunnable = object : Runnable {
        override fun run() {
            send(JSONObject().put("type", "ping"))
            mainHandler.postDelayed(this, APP_PING_INTERVAL_MS)
        }
    }

    fun connect(ip: String, port: Int) {
        manuallyClosed = false
        opened = false
        val request = Request.Builder().url("ws://$ip:$port").build()
        startCountdown()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                opened = true
                cancelCountdown()
                webSocket.send(JSONObject().put("type", "hello").toString())
                mainHandler.postDelayed(pingRunnable, APP_PING_INTERVAL_MS)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleControlMessage(text)
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                val jpeg = bytes.toByteArray()
                post { listener.onFrame(jpeg) }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                cancelCountdown()
                mainHandler.removeCallbacks(pingRunnable)
                if (!manuallyClosed) {
                    post { listener.onError(t.message ?: "Falha na conexão") }
                }
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                cancelCountdown()
                mainHandler.removeCallbacks(pingRunnable)
                if (!manuallyClosed) {
                    post { listener.onClosed() }
                }
            }
        })
    }

    fun startStream(monitor: Int, fps: Int) {
        send(JSONObject().put("type", "start").put("monitor", monitor).put("fps", fps))
    }

    fun setFps(fps: Int) {
        send(JSONObject().put("type", "set_fps").put("fps", fps))
    }

    fun setMouseHighlight(
        enabled: Boolean,
        size: Int,
        opacity: Float,
        clickDurationMs: Int,
        clickEffects: Boolean,
    ) {
        send(
            JSONObject()
                .put("type", "mouse_highlight")
                .put("enabled", enabled)
                .put("size", size)
                .put("opacity", opacity.toDouble())
                .put("click_duration_ms", clickDurationMs)
                .put("click_effects", clickEffects)
        )
    }

    fun close() {
        manuallyClosed = true
        cancelCountdown()
        mainHandler.removeCallbacks(pingRunnable)
        webSocket?.close(1000, "encerrado pelo app")
        webSocket = null
    }

    private fun send(json: JSONObject) {
        webSocket?.send(json.toString())
    }

    private fun handleControlMessage(text: String) {
        val json = try {
            JSONObject(text)
        } catch (e: Exception) {
            return
        }
        when (json.optString("type")) {
            "monitors" -> {
                val array: JSONArray = json.optJSONArray("monitors") ?: JSONArray()
                val monitors = (0 until array.length()).map { i ->
                    val m = array.getJSONObject(i)
                    MonitorInfo(m.getInt("index"), m.getInt("width"), m.getInt("height"))
                }
                post { listener.onMonitors(monitors) }
            }
            "started" -> {
                val monitor = json.optInt("monitor")
                val fps = json.optInt("fps")
                post { listener.onStarted(monitor, fps) }
            }
        }
    }

    private fun startCountdown() {
        countdownTimer = object : CountDownTimer(CONNECT_TIMEOUT_MS, 1000) {
            override fun onTick(millisUntilFinished: Long) {
                if (!opened) {
                    listener.onConnecting((millisUntilFinished / 1000).toInt())
                }
            }

            override fun onFinish() {
                if (!opened) {
                    manuallyClosed = true
                    webSocket?.cancel()
                    listener.onTimeout()
                }
            }
        }.also { it.start() }
    }

    private fun cancelCountdown() {
        countdownTimer?.cancel()
        countdownTimer = null
    }

    private fun post(action: () -> Unit) {
        mainHandler.post(action)
    }
}
