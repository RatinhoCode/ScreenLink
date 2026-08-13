package com.screenshare.app.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import android.util.AttributeSet
import android.view.LayoutInflater
import android.widget.FrameLayout
import com.screenshare.app.R
import com.screenshare.app.databinding.ViewScreenBinding
import com.screenshare.app.model.MonitorInfo
import com.screenshare.app.model.MouseHighlightSettings
import com.screenshare.app.net.ScreenSocket

/**
 * Uma "aba" de compartilhamento: mantém sua própria conexão WebSocket,
 * exibe o frame mais recente e guarda o estado de FPS/monitor selecionado.
 */
class ScreenView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : FrameLayout(context, attrs) {

    private val binding = ViewScreenBinding.inflate(LayoutInflater.from(context), this, true)

    var label: String = ""
    var ip: String = ""
    var port: Int = 8765
    var monitorIndex: Int = 1
    var fps: Int = 30
        private set

    var onMonitorsReceived: ((List<MonitorInfo>) -> Unit)? = null
    var onConnectionProgress: ((String) -> Unit)? = null
    var onConnectionFailed: ((String) -> Unit)? = null
    var onStateChanged: (() -> Unit)? = null

    private var socket: ScreenSocket? = null
    private var lastRawBitmap: Bitmap? = null
    var lastBitmap: Bitmap? = null
        private set

    /** 0, 90, 180 ou 270 graus, aplicados ao frame antes de exibir. */
    var rotationDegrees: Int = 0
        private set

    /** Estado do destaque do mouse (desenhado no servidor, sobre o frame). */
    var mouseHighlight: MouseHighlightSettings = MouseHighlightSettings()
        private set

    private val listener = object : ScreenSocket.Listener {
        override fun onConnecting(secondsLeft: Int) {
            val text = context.getString(R.string.connecting_countdown, secondsLeft)
            binding.statusText.visibility = VISIBLE
            binding.statusText.text = text
            onConnectionProgress?.invoke(text)
        }

        override fun onMonitors(monitors: List<MonitorInfo>) {
            onMonitorsReceived?.invoke(monitors)
        }

        override fun onStarted(monitor: Int, fps: Int) {
            monitorIndex = monitor
            this@ScreenView.fps = fps
            onStateChanged?.invoke()
        }

        override fun onFrame(jpeg: ByteArray) {
            val bitmap = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size) ?: return
            binding.statusText.visibility = GONE
            lastRawBitmap = bitmap
            showBitmap(bitmap)
        }

        override fun onTimeout() {
            val text = context.getString(R.string.connection_timeout)
            binding.statusText.visibility = VISIBLE
            binding.statusText.text = text
            onConnectionFailed?.invoke(text)
        }

        override fun onError(message: String) {
            val text = context.getString(R.string.connection_failed)
            binding.statusText.visibility = VISIBLE
            binding.statusText.text = text
            onConnectionFailed?.invoke(text)
        }

        override fun onClosed() {
            binding.statusText.visibility = VISIBLE
            binding.statusText.text = context.getString(R.string.connection_closed)
        }
    }

    /** Conecta e, assim que o servidor responder com a lista de monitores, chama [onReady]. */
    fun connect(ip: String, port: Int, onReady: (List<MonitorInfo>) -> Unit) {
        this.ip = ip
        this.port = port
        onMonitorsReceived = onReady
        socket?.close()
        socket = ScreenSocket(listener).also { it.connect(ip, port) }
    }

    fun startStreaming(monitor: Int, fps: Int) {
        monitorIndex = monitor
        this.fps = fps
        socket?.startStream(monitor, fps)
    }

    fun toggleFps() {
        val newFps = if (fps >= 60) 30 else 60
        fps = newFps
        socket?.setFps(newFps)
        onStateChanged?.invoke()
    }

    fun disconnect() {
        socket?.close()
        socket = null
    }

    /** Gira a exibição em +90° a cada chamada (0 -> 90 -> 180 -> 270 -> 0). */
    fun rotateView() {
        rotationDegrees = (rotationDegrees + 90) % 360
        lastRawBitmap?.let { showBitmap(it) }
    }

    fun toggleMouseHighlight() {
        applyMouseHighlight(mouseHighlight.copy(enabled = !mouseHighlight.enabled))
    }

    fun applyMouseHighlight(settings: MouseHighlightSettings) {
        mouseHighlight = settings
        socket?.setMouseHighlight(
            enabled = settings.enabled,
            size = settings.size,
            opacity = settings.opacity,
            clickDurationMs = settings.clickDurationMs,
            clickEffects = settings.clickEffects,
        )
        onStateChanged?.invoke()
    }

    private fun showBitmap(bitmap: Bitmap) {
        val rotated = if (rotationDegrees == 0) {
            bitmap
        } else {
            val matrix = Matrix().apply { postRotate(rotationDegrees.toFloat()) }
            Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, matrix, true)
        }
        binding.imageView.setImageBitmap(rotated)
        lastBitmap = rotated
    }
}
