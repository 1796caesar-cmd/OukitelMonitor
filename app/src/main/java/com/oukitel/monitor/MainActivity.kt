package com.oukitel.monitor

import android.app.Activity
import android.os.Bundle
import android.graphics.Color
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.TextView

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(32, 32, 32, 32)
            setBackgroundColor(Color.rgb(16, 30, 28))
        }
        fun text(value: String, size: Float, color: Int): TextView =
            TextView(this).apply {
                text = value
                textSize = size
                setTextColor(color)
                gravity = Gravity.CENTER
                setPadding(0, 16, 0, 16)
            }
        root.addView(text("OukitelMonitor", 30f, Color.WHITE))
        root.addView(text("P1000E Plus", 20f, Color.rgb(170, 225, 190)))
        root.addView(text("Заряд: — %", 30f, Color.WHITE))
        root.addView(text("Вхід: — Вт     Вихід: — Вт", 18f, Color.WHITE))
        root.addView(text("Очікується підключення до Wonderfree. Показники поки недоступні.", 15f, Color.LTGRAY))
        setContentView(root)
    }
}
