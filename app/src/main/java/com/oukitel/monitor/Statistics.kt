package com.oukitel.monitor

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.view.View
import org.json.JSONArray
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Local history only; samples are not fabricated when Android suspends the service. */
object StatisticsStore {
    data class Sample(val timestamp: Long, val battery: Int?, val input: Double?, val output: Double?)
    @Synchronized fun record(context: Context, battery: Int?, input: Double?, output: Double?) {
        if (battery == null && input == null && output == null) return
        val prefs = context.getSharedPreferences("oukitel", Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        if (now - prefs.getLong("statistics_last", 0L) < 900_000L) return
        try {
            val old = JSONArray(prefs.getString("statistics", "[]"))
            val recent = JSONArray()
            val cutoff = now - 31L * 24 * 60 * 60 * 1000
            for (i in 0 until old.length()) {
                val item = old.optJSONObject(i) ?: continue
                if (item.optLong("t") >= cutoff) recent.put(item)
            }
            val item = JSONObject().put("t", now)
            if (battery != null) item.put("b", battery)
            if (input != null) item.put("i", input)
            if (output != null) item.put("o", output)
            recent.put(item)
            prefs.edit().putString("statistics", recent.toString()).putLong("statistics_last", now).apply()
        } catch (_: Exception) { }
    }
    @Synchronized fun read(context: Context, hours: Int): List<Sample> {
        val result = mutableListOf<Sample>()
        val since = System.currentTimeMillis() - hours * 3_600_000L
        try {
            val items = JSONArray(context.getSharedPreferences("oukitel", Context.MODE_PRIVATE).getString("statistics", "[]"))
            for (i in 0 until items.length()) {
                val x = items.optJSONObject(i) ?: continue
                val t = x.optLong("t")
                if (t >= since) result.add(Sample(t, if(x.has("b")) x.optInt("b") else null, if(x.has("i")) x.optDouble("i") else null, if(x.has("o")) x.optDouble("o") else null))
            }
        } catch (_: Exception) { }
        return result
    }
}

class StatisticsChart(context: Context, private val power: Boolean, private val light: Boolean) : View(context) {
    private var entries: List<StatisticsStore.Sample> = emptyList()
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val density = resources.displayMetrics.density
    fun setEntries(data: List<StatisticsStore.Sample>) { entries = data; invalidate() }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val w = width.toFloat(); val h = height.toFloat()
        val left = 45f * density; val right = w - 12f*density
        val top = 16f*density; val bottom = h - 31f*density
        val ink = if (light) Color.rgb(63,93,75) else Color.rgb(185,218,202)
        paint.strokeWidth = density; paint.textSize = 11f*density
        val max = if (power) maxOf(100.0, (entries.mapNotNull { it.input } + entries.mapNotNull { it.output }).maxOrNull() ?: 100.0) else 100.0
        for (i in 0..4) {
            val y = bottom - (bottom-top)*i/4f
            paint.color = if (light) Color.rgb(205,224,213) else Color.rgb(48,79,66)
            canvas.drawLine(left,y,right,y,paint)
            paint.color=ink
            canvas.drawText("${(max*i/4).toInt()}",3f*density,y+4f*density,paint)
        }
        if (entries.isEmpty()) {
            paint.color=ink; paint.textSize=13f*density
            canvas.drawText("Поки немає записів",left+12f*density,(top+bottom)/2,paint)
            return
        }
        val start = entries.first().timestamp
        val end = maxOf(start+1L,entries.last().timestamp)
        val x: (Long)->Float = { left+(right-left)*(it-start).toFloat()/(end-start).toFloat() }
        fun drawSeries(color:Int, value:(StatisticsStore.Sample)->Double?) {
            paint.color=color; paint.style=Paint.Style.STROKE; paint.strokeWidth=2.5f*density
            val path=android.graphics.Path(); var lastT:Long?=null
            for (e in entries) {
                val v=value(e) ?: continue
                val xx=x(e.timestamp); val yy=bottom-(bottom-top)*(v/max).coerceIn(0.0,1.0).toFloat()
                if (lastT==null || e.timestamp-lastT>35*60*1000L) path.moveTo(xx,yy) else path.lineTo(xx,yy)
                lastT=e.timestamp
            }
            canvas.drawPath(path,paint); paint.style=Paint.Style.FILL
        }
        if (power) {
            drawSeries(Color.rgb(66,160,242)){it.input}
            drawSeries(Color.rgb(248,166,70)){it.output}
        } else drawSeries(Color.rgb(43,203,101)){it.battery?.toDouble()}
        val date=SimpleDateFormat("dd.MM HH:mm",Locale.getDefault())
        paint.color=ink; paint.textSize=10f*density
        canvas.drawText(date.format(Date(start)),left,bottom+19f*density,paint)
        val label=date.format(Date(end)); canvas.drawText(label,right-paint.measureText(label),bottom+19f*density,paint)
    }
}
