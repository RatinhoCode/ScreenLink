package com.screenshare.app.ui

import android.annotation.SuppressLint
import android.app.AlertDialog
import android.content.ContentValues
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.view.View
import android.view.WindowInsets
import android.view.WindowInsetsController
import android.view.WindowManager
import android.widget.RadioButton
import android.widget.SeekBar
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.screenshare.app.R
import com.screenshare.app.databinding.ActivityMainBinding
import com.screenshare.app.databinding.DialogAddConnectionBinding
import com.screenshare.app.databinding.DialogMouseSettingsBinding
import com.screenshare.app.databinding.ItemAddTabBinding
import com.screenshare.app.databinding.ItemTabBinding
import com.screenshare.app.model.MonitorInfo
import java.io.OutputStream

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding

    private data class Tab(val screenView: ScreenView, val tabBinding: ItemTabBinding)

    private val tabs = mutableListOf<Tab>()
    private var activeIndex = -1
    private var isFullscreen = false
    private var pendingScreenshot: Bitmap? = null

    private var lastIp = ""
    private var lastPort = "8765"

    private val requestStoragePermission =
        registerForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) {
                pendingScreenshot?.let { saveBitmapToGallery(it) }
            } else {
                toast(getString(R.string.screenshot_failed))
            }
            pendingScreenshot = null
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // mantém a tela acesa enquanto o app está em primeiro plano assistindo ao stream
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val addTabBinding = ItemAddTabBinding.inflate(layoutInflater, binding.tabContainer, true)
        addTabBinding.btnAddTab.setOnClickListener { showAddConnectionDialog() }

        binding.btnFps.setOnClickListener { activeTab()?.screenView?.toggleFps() }
        binding.btnScreenshot.setOnClickListener { onScreenshotClicked() }
        binding.btnRotate.setOnClickListener { activeTab()?.screenView?.rotateView() }
        binding.btnMouse.setOnClickListener { activeTab()?.screenView?.toggleMouseHighlight() }
        binding.btnMouse.setOnLongClickListener {
            activeTab()?.screenView?.let { showMouseSettingsDialog(it) }
            true
        }
        binding.btnFullscreen.setOnClickListener { toggleFullscreen() }
        binding.screenContainer.setOnClickListener { if (isFullscreen) toggleFullscreen() }

        showAddConnectionDialog()
    }

    // ---------------------------------------------------------------------
    // Diálogo de nova conexão (IP/porta -> lista de monitores -> adicionar)
    // ---------------------------------------------------------------------

    private fun showAddConnectionDialog() {
        val dialogBinding = DialogAddConnectionBinding.inflate(layoutInflater)
        dialogBinding.editIp.setText(lastIp)
        dialogBinding.editPort.setText(lastPort)

        var tempScreenView: ScreenView? = null
        var awaitingMonitorSelection = false

        val dialog = AlertDialog.Builder(this, R.style.ThemeOverlay_ScreenShare_Dialog)
            .setTitle(R.string.dialog_add_title)
            .setView(dialogBinding.root)
            .setPositiveButton(R.string.btn_connect, null)
            .setNegativeButton(R.string.dialog_cancel) { d, _ ->
                tempScreenView?.disconnect()
                d.dismiss()
            }
            .create()

        // força fundo escuro do próprio window do diálogo, sem depender de
        // atributos de tema que podem resolver para o esquema claro
        dialog.window?.setBackgroundDrawableResource(R.drawable.bg_dialog)

        dialog.setOnShowListener {
            val positiveButton = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
            positiveButton.setTextColor(ContextCompat.getColor(this, R.color.accent))
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE)
                .setTextColor(ContextCompat.getColor(this, R.color.accent))
            positiveButton.setOnClickListener {
                if (!awaitingMonitorSelection) {
                    val ip = dialogBinding.editIp.text.toString().trim()
                    val portText = dialogBinding.editPort.text.toString().trim()
                    val port = portText.toIntOrNull()
                    if (ip.isEmpty() || port == null) {
                        dialogBinding.dialogStatus.text = getString(R.string.hint_ip)
                        return@setOnClickListener
                    }
                    lastIp = ip
                    lastPort = portText

                    tempScreenView?.disconnect()
                    positiveButton.isEnabled = false
                    dialogBinding.dialogStatus.text = getString(R.string.connecting_countdown, 60)
                    val screenView = ScreenView(this)
                    tempScreenView = screenView
                    screenView.onConnectionProgress = { text -> dialogBinding.dialogStatus.text = text }
                    screenView.onConnectionFailed = { text ->
                        dialogBinding.dialogStatus.text = text
                        positiveButton.isEnabled = true
                    }
                    screenView.connect(ip, port) { monitors ->
                        populateMonitorChoices(dialogBinding, monitors)
                        awaitingMonitorSelection = true
                        positiveButton.isEnabled = true
                        positiveButton.text = getString(R.string.btn_add_screen)
                        dialogBinding.dialogStatus.text = getString(R.string.select_monitor_title)
                    }
                } else {
                    val screenView = tempScreenView ?: return@setOnClickListener
                    val selectedId = dialogBinding.monitorGroup.checkedRadioButtonId
                    val monitorIndex = if (selectedId != View.NO_ID) {
                        dialogBinding.monitorGroup.findViewById<RadioButton>(selectedId).tag as Int
                    } else {
                        1
                    }
                    screenView.startStreaming(monitorIndex, 30)
                    addTab(screenView)
                    dialog.dismiss()
                }
            }
        }

        dialog.show()
    }

    private fun populateMonitorChoices(
        dialogBinding: DialogAddConnectionBinding,
        monitors: List<MonitorInfo>,
    ) {
        dialogBinding.monitorGroup.removeAllViews()
        monitors.forEachIndexed { i, monitor ->
            val radio = RadioButton(this).apply {
                text = "${getString(R.string.tab_screen_format).format(monitor.index)} (${monitor.width}x${monitor.height})"
                tag = monitor.index
                id = View.generateViewId()
                setTextColor(ContextCompat.getColor(context, R.color.text_primary))
            }
            dialogBinding.monitorGroup.addView(radio)
            if (i == 0) dialogBinding.monitorGroup.check(radio.id)
        }
    }

    // ---------------------------------------------------------------------
    // Destaque do mouse (desenhado pelo servidor sobre o frame)
    // ---------------------------------------------------------------------

    private fun showMouseSettingsDialog(screenView: ScreenView) {
        val dialogBinding = DialogMouseSettingsBinding.inflate(layoutInflater)
        val current = screenView.mouseHighlight

        // faixas de valores aceitas pelo servidor (ver _apply_mouse_highlight em server.py)
        fun sizeToProgress(size: Int) = (size - 10).coerceIn(0, 110) * 100 / 110
        fun progressToSize(progress: Int) = 10 + progress * 110 / 100

        fun opacityToProgress(opacity: Float) = (opacity * 100).toInt().coerceIn(5, 100)
        fun progressToOpacity(progress: Int) = progress.coerceAtLeast(5) / 100f

        fun durationToProgress(ms: Int) = (ms - 100).coerceIn(0, 1100) * 100 / 1100
        fun progressToDuration(progress: Int) = 100 + progress * 1100 / 100

        dialogBinding.seekSize.progress = sizeToProgress(current.size)
        dialogBinding.seekOpacity.progress = opacityToProgress(current.opacity)
        dialogBinding.seekClickDuration.progress = durationToProgress(current.clickDurationMs)
        dialogBinding.switchClickEffects.isChecked = current.clickEffects

        fun applyFromSliders() {
            val updated = screenView.mouseHighlight.copy(
                size = progressToSize(dialogBinding.seekSize.progress),
                opacity = progressToOpacity(dialogBinding.seekOpacity.progress),
                clickDurationMs = progressToDuration(dialogBinding.seekClickDuration.progress),
                clickEffects = dialogBinding.switchClickEffects.isChecked,
            )
            screenView.applyMouseHighlight(updated)
            updateBottomBarForActiveTab()
        }

        val seekListener = object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                if (fromUser) applyFromSliders()
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        }
        dialogBinding.seekSize.setOnSeekBarChangeListener(seekListener)
        dialogBinding.seekOpacity.setOnSeekBarChangeListener(seekListener)
        dialogBinding.seekClickDuration.setOnSeekBarChangeListener(seekListener)
        dialogBinding.switchClickEffects.setOnCheckedChangeListener { _, _ -> applyFromSliders() }

        val dialog = AlertDialog.Builder(this, R.style.ThemeOverlay_ScreenShare_Dialog)
            .setTitle(R.string.mouse_settings_title)
            .setView(dialogBinding.root)
            .setPositiveButton(R.string.btn_close, null)
            .create()

        dialog.window?.setBackgroundDrawableResource(R.drawable.bg_dialog)
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE)
                .setTextColor(ContextCompat.getColor(this, R.color.accent))
        }
        dialog.show()
    }

    // ---------------------------------------------------------------------
    // Gestão de abas
    // ---------------------------------------------------------------------

    private fun addTab(screenView: ScreenView) {
        val index = tabs.size
        val tabBinding = ItemTabBinding.inflate(layoutInflater, binding.tabContainer, false)
        tabBinding.tabLabel.text = getString(R.string.tab_screen_format, index + 1)
        tabBinding.root.setOnClickListener { selectTab(index) }
        tabBinding.tabClose.setOnClickListener { removeTab(index) }

        // insere antes do botão "+", que é sempre o último filho
        binding.tabContainer.addView(tabBinding.root, binding.tabContainer.childCount - 1)

        screenView.visibility = View.GONE
        screenView.onStateChanged = { updateBottomBarForActiveTab() }
        binding.screenContainer.addView(screenView)

        tabs.add(Tab(screenView, tabBinding))
        binding.emptyStateText.visibility = View.GONE
        selectTab(index)
    }

    private fun selectTab(index: Int) {
        if (index !in tabs.indices) return
        tabs.forEachIndexed { i, tab ->
            tab.screenView.visibility = if (i == index) View.VISIBLE else View.GONE
            tab.tabBinding.tabLabel.setTextColor(
                ContextCompat.getColor(this, if (i == index) R.color.accent else R.color.text_secondary)
            )
        }
        activeIndex = index
        updateBottomBarForActiveTab()
    }

    private fun removeTab(index: Int) {
        if (index !in tabs.indices) return
        val tab = tabs.removeAt(index)
        tab.screenView.disconnect()
        binding.screenContainer.removeView(tab.screenView)
        binding.tabContainer.removeView(tab.tabBinding.root)

        tabs.forEachIndexed { i, t -> t.tabBinding.tabLabel.text = getString(R.string.tab_screen_format, i + 1) }

        if (tabs.isEmpty()) {
            activeIndex = -1
            binding.emptyStateText.visibility = View.VISIBLE
        } else {
            selectTab(index.coerceAtMost(tabs.size - 1))
        }
    }

    private fun activeTab(): Tab? = tabs.getOrNull(activeIndex)

    private fun updateBottomBarForActiveTab() {
        val screenView = activeTab()?.screenView
        val fps = screenView?.fps ?: 30
        binding.btnFps.text = if (fps >= 60) getString(R.string.fps_60) else getString(R.string.fps_30)

        val mouseEnabled = screenView?.mouseHighlight?.enabled ?: false
        binding.btnMouse.text = getString(if (mouseEnabled) R.string.btn_mouse_on else R.string.btn_mouse_off)
        binding.btnMouse.setTextColor(
            ContextCompat.getColor(this, if (mouseEnabled) R.color.accent else R.color.text_primary)
        )
    }

    // ---------------------------------------------------------------------
    // Print de tela
    // ---------------------------------------------------------------------

    private fun onScreenshotClicked() {
        val bitmap = activeTab()?.screenView?.lastBitmap
        if (bitmap == null) {
            toast(getString(R.string.no_frame_yet))
            return
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q &&
            ContextCompat.checkSelfPermission(this, android.Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED
        ) {
            pendingScreenshot = bitmap
            requestStoragePermission.launch(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
            return
        }
        saveBitmapToGallery(bitmap)
    }

    @SuppressLint("InlinedApi")
    private fun saveBitmapToGallery(bitmap: Bitmap) {
        val fileName = "screenshare_${System.currentTimeMillis()}.jpg"
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, fileName)
            put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg")
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/ScreenShare")
            }
        }
        val resolver = contentResolver
        val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
        if (uri == null) {
            toast(getString(R.string.screenshot_failed))
            return
        }
        var out: OutputStream? = null
        try {
            out = resolver.openOutputStream(uri)
            if (out == null) throw IllegalStateException("sem output stream")
            bitmap.compress(Bitmap.CompressFormat.JPEG, 95, out)
            toast(getString(R.string.screenshot_saved))
        } catch (e: Exception) {
            toast(getString(R.string.screenshot_failed))
        } finally {
            out?.close()
        }
    }

    // ---------------------------------------------------------------------
    // Tela cheia
    // ---------------------------------------------------------------------

    private fun toggleFullscreen() {
        isFullscreen = !isFullscreen
        binding.tabStrip.visibility = if (isFullscreen) View.GONE else View.VISIBLE
        binding.bottomBarScroll.visibility = if (isFullscreen) View.GONE else View.VISIBLE
        setSystemBarsVisible(!isFullscreen)
    }

    private fun setSystemBarsVisible(visible: Boolean) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val controller = window.insetsController
            if (visible) {
                controller?.show(WindowInsets.Type.systemBars())
            } else {
                controller?.hide(WindowInsets.Type.systemBars())
                controller?.systemBarsBehavior =
                    WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
        } else {
            @Suppress("DEPRECATION")
            window.decorView.systemUiVisibility = if (visible) {
                View.SYSTEM_UI_FLAG_VISIBLE
            } else {
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or
                    View.SYSTEM_UI_FLAG_FULLSCREEN or
                    View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                    View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or
                    View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            }
        }
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_SHORT).show()

    override fun onDestroy() {
        super.onDestroy()
        tabs.forEach { it.screenView.disconnect() }
    }
}
