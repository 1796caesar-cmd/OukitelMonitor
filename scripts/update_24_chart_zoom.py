"""OukitelMonitor 2.4 — pinch-to-zoom and pan for the battery statistics chart.

Run AFTER update_23_power_alerts.py. The project currently displays only the
battery chart; no power-consumption chart is added or restored. Existing signed
release, in-app update, power alerts and user data stay unchanged.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAT = ROOT / 'app/src/main/java/com/oukitel/monitor/Statistics.kt'
MAIN = ROOT / 'app/src/main/java/com/oukitel/monitor/MainActivity.kt'
GRADLE = ROOT / 'app/build.gradle.kts'


def once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly 1 occurrence, found {count}')
    return source.replace(old, new, 1)


stats = STAT.read_text(encoding='utf-8')
main = MAIN.read_text(encoding='utf-8')
gradle = GRADLE.read_text(encoding='utf-8')

if 'private val scaleDetector = ScaleGestureDetector(' in stats:
    raise RuntimeError('Zoom code appears to be present already')

stats = once(stats, 'import android.view.MotionEvent\n',
    'import android.view.MotionEvent\nimport android.view.ScaleGestureDetector\nimport android.view.ViewConfiguration\nimport kotlin.math.abs\n',
    'add gesture imports')

begin = '    fun setEntries(data: List<StatisticsStore.Sample>) {'
end = '    override fun performClick(): Boolean {'
if stats.count(begin) != 1 or stats.count(end) != 1:
    raise RuntimeError('StatisticsChart structure not recognized')
a = stats.index(begin)
b = stats.index(end, a)

new_gestures = '''    // The currently visible TIME interval. Historical data is never modified.
    private var visibleStart = 0.0
    private var visibleEnd = 1.0
    private var downX = 0f
    private var downY = 0f
    private var lastX = 0f
    private var panning = false
    private var pinched = false
    private val touchSlop = ViewConfiguration.get(context).scaledTouchSlop.toFloat()

    private fun limits(): Pair<Double, Double> {
        if (entries.isEmpty()) return 0.0 to 1.0
        val first = entries.first().timestamp.toDouble()
        return first to maxOf(first + 1.0, entries.last().timestamp.toDouble())
    }

    private fun chartLeft() = 45f * density
    private fun chartRight() = width.toFloat() - 12f * density

    /** Resets to the selected 24h / 7d / 30d data period. */
    fun resetZoom() {
        val (first, last) = limits()
        visibleStart = first
        visibleEnd = last
        invalidate()
    }

    fun setEntries(data: List<StatisticsStore.Sample>) {
        entries = data.sortedBy { it.timestamp }
        selectedIndex = -1
        resetZoom()
    }

    private fun shiftByPixels(dx: Float) {
        val (first, last) = limits()
        val window = visibleEnd - visibleStart
        val full = last - first
        if (window >= full || width <= 0) return
        val chartWidth = (chartRight() - chartLeft()).coerceAtLeast(1f)
        val deltaTime = -dx.toDouble() * window / chartWidth.toDouble()
        val newStart = (visibleStart + deltaTime).coerceIn(first, last - window)
        visibleStart = newStart
        visibleEnd = newStart + window
        invalidate()
    }

    private val scaleDetector = ScaleGestureDetector(context,
        object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScaleBegin(detector: ScaleGestureDetector): Boolean {
                if (entries.size < 2) return false
                pinched = true
                parent?.requestDisallowInterceptTouchEvent(true)
                return true
            }

            override fun onScale(detector: ScaleGestureDetector): Boolean {
                if (entries.size < 2 || width <= 0) return false
                val (first, last) = limits()
                val full = last - first
                val oldWidth = visibleEnd - visibleStart
                // Zoom enough to inspect individual 15-minute measurements.
                val minimum = minOf(full, 15.0 * 60_000.0)
                val newWidth = (oldWidth / detector.scaleFactor.toDouble())
                    .coerceIn(minimum, full)
                val chartWidth = (chartRight() - chartLeft()).coerceAtLeast(1f)
                val focus = ((detector.focusX - chartLeft()) / chartWidth).coerceIn(0f, 1f).toDouble()
                val anchoredTime = visibleStart + focus * oldWidth
                val newStart = (anchoredTime - focus * newWidth).coerceIn(first, last - newWidth)
                visibleStart = newStart
                visibleEnd = newStart + newWidth
                invalidate()
                return true
            }
        })

    override fun onTouchEvent(event: MotionEvent): Boolean {
        scaleDetector.onTouchEvent(event)
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                downX = event.x
                downY = event.y
                lastX = event.x
                panning = false
                pinched = false
                return true
            }
            MotionEvent.ACTION_POINTER_DOWN -> {
                pinched = true
                parent?.requestDisallowInterceptTouchEvent(true)
                return true
            }
            MotionEvent.ACTION_MOVE -> {
                if (event.pointerCount == 1 && !pinched && !scaleDetector.isInProgress) {
                    val dx = event.x - lastX
                    val horizontal = abs(event.x - downX)
                    val vertical = abs(event.y - downY)
                    if (!panning && horizontal > touchSlop && horizontal > vertical) {
                        panning = true
                        parent?.requestDisallowInterceptTouchEvent(true)
                    }
                    if (panning) shiftByPixels(dx)
                    lastX = event.x
                }
                return true
            }
            MotionEvent.ACTION_POINTER_UP -> {
                pinched = true
                return true
            }
            MotionEvent.ACTION_UP -> {
                val tap = !panning && !pinched &&
                    abs(event.x - downX) <= touchSlop && abs(event.y - downY) <= touchSlop
                if (tap && entries.isNotEmpty()) {
                    val chartWidth = (chartRight() - chartLeft()).coerceAtLeast(1f)
                    val fraction = ((event.x - chartLeft()) / chartWidth).coerceIn(0f, 1f)
                    val wanted = visibleStart + fraction * (visibleEnd - visibleStart)
                    val visible = entries.indices.filter { i ->
                        entries[i].timestamp.toDouble() in visibleStart..visibleEnd
                    }
                    selectedIndex = visible.minByOrNull { i -> abs(entries[i].timestamp.toDouble() - wanted) } ?: -1
                    if (selectedIndex >= 0) onSampleSelected?.invoke(entries[selectedIndex])
                    performClick()
                    invalidate()
                }
                parent?.requestDisallowInterceptTouchEvent(false)
                return true
            }
            MotionEvent.ACTION_CANCEL -> {
                parent?.requestDisallowInterceptTouchEvent(false)
                panning = false
                pinched = false
                return true
            }
        }
        return true
    }
'''
stats = stats[:a] + new_gestures + stats[b:]

# Keep existing colors/axes/series drawing. Only map time to a zoomed viewport.
old_x = '''        val start = entries.first().timestamp
        val end = maxOf(start+1L,entries.last().timestamp)
        val x: (Long)->Float = { left+(right-left)*(it-start).toFloat()/(end-start).toFloat() }'''
new_x = '''        val start = visibleStart
        val end = maxOf(start + 1.0, visibleEnd)
        val x: (Long)->Float = { left + (right-left) * ((it.toDouble()-start) / (end-start)).toFloat() }'''
stats = once(stats, old_x, new_x, 'map visible time range')

stats = once(stats,
    '        if (power) {\n            drawSeries(Color.rgb(66,160,242)){it.input}',
    '        canvas.save()\n        canvas.clipRect(left, top, right, bottom)\n        if (power) {\n            drawSeries(Color.rgb(66,160,242)){it.input}',
    'clip graph lines to chart window')
stats = once(stats,
    '''        } else dots(Color.rgb(43,203,101)){it.battery?.toDouble()}
        val date=SimpleDateFormat''',
    '''        } else dots(Color.rgb(43,203,101)){it.battery?.toDouble()}
        canvas.restore()
        val date=SimpleDateFormat''',
    'restore canvas after drawing visible points')
stats = once(stats,
    'date.format(Date(start))', 'date.format(Date(start.toLong()))', 'visible first date')
stats = once(stats,
    'date.format(Date(end))', 'date.format(Date(end.toLong()))', 'visible last date')

# The actual application shows only the battery history chart after update_16.
if 'val powerChart = StatisticsChart' in main:
    raise RuntimeError('Expected battery-only Statistics screen after 1.6 patch')
main = once(main,
    '''        add(root,batteryChart,height=dp(230)); gap(root,24)''',
    '''        add(root,batteryChart,height=dp(250)); gap(root,12)
        add(root,text("Розведи два пальці для збільшення, проведи по графіку для переміщення.",13f,muted))
        gap(root,10)
        val resetScale = text("↺   Скинути масштаб",16f,green,true).apply {
            background=shape(panel,16,green)
            gravity=Gravity.CENTER
            setPadding(dp(15),dp(13),dp(15),dp(13))
            setOnClickListener { batteryChart.resetZoom() }
        }
        add(root,resetScale); gap(root,18)''',
    'add battery zoom instructions and reset button')

# Keep nearest recorded-point inspection after a tap.
main = main.replace('Натисни на точку графіка, щоб переглянути запис',
                    'Торкнись точки графіка, щоб переглянути запис')

gradle = once(gradle,
    'versionName = "2.3"', 'versionName = "2.4"', 'Android release version')

# Do not change versionCode generation, package ID, signing, or any notifications.
STAT.write_text(stats, encoding='utf-8')
MAIN.write_text(main, encoding='utf-8')
GRADLE.write_text(gradle, encoding='utf-8')
print('OukitelMonitor 2.4: battery statistics pinch zoom, pan and reset; no consumption chart')
