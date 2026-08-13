package com.screenshare.app.model

/** Espelha os valores padrão de MouseHighlightSettings no servidor Python. */
data class MouseHighlightSettings(
    val enabled: Boolean = false,
    val size: Int = 40,
    val opacity: Float = 0.55f,
    val clickDurationMs: Int = 400,
    val clickEffects: Boolean = true,
)
