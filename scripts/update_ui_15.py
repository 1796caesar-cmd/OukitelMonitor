from pathlib import Path
p = Path('app/src/main/java/com/oukitel/monitor/MainActivity.kt')
s = p.read_text(encoding='utf-8')

def change(old, new):
    global s
    if old not in s:
        raise SystemExit('Cannot apply 1.5 patch: missing source pattern: ' + old[:90])
    s = s.replace(old, new)

change('shape(if (lightTheme) panel else Color.rgb(9, 71, 40), 25, green)', 'shape(palette.tile, 25, green)')
change('shape(if (lightTheme) panel else Color.rgb(22, 59, 38), 20, green)', 'shape(panel, 20, green)')
change('shape(panel,20,Color.rgb(108,220,168))', 'shape(panel,20,green)')
change('statusText.text = state.second', 'statusText.text = if (state.first == "mains") "Режим очікування\\n(робота від мережі)" else state.second')
change('val number = EditText(this).apply { hint="Відсоток (1–100)"; inputType=InputType.TYPE_CLASS_NUMBER; setTextColor(white); setHintTextColor(muted); background=shape(panel); setPadding(dp(15),dp(14),dp(15),dp(14)) }\n        add(root,number); gap(root,12)', '''val thresholdLabel = text("Поріг: 5%", 19f, green, true).apply { gravity = Gravity.CENTER }
        add(root, thresholdLabel); gap(root, 5)
        val thresholdSlider = SeekBar(this).apply {
            max = 99
            progress = 4
            progressTintList = android.content.res.ColorStateList.valueOf(green)
            thumbTintList = android.content.res.ColorStateList.valueOf(green)
        }
        add(root, thresholdSlider); gap(root, 12)
        thresholdSlider.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                thresholdLabel.text = "Поріг: ${progress + 1}%"
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })''')
change('val threshold=number.text.toString().toIntOrNull()\n            if(threshold==null || threshold !in 1..100) { Toast.makeText(this,"Вкажи число від 1 до 100",Toast.LENGTH_SHORT).show(); return@setOnClickListener }', 'val threshold = thresholdSlider.progress + 1')
change('number.text.clear(); render()', 'render()')
p.write_text(s, encoding='utf-8')
print('OukitelMonitor 1.5 UI patch applied successfully')
