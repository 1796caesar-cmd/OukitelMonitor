package com.oukitel.monitor

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews

class MonitorWidget : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        ids.forEach { update(context, manager, it) }
    }
    companion object {
        fun updateAll(context: Context) {
            val manager=AppWidgetManager.getInstance(context)
            val ids=manager.getAppWidgetIds(ComponentName(context,MonitorWidget::class.java))
            ids.forEach { update(context,manager,it) }
        }
        private fun update(context: Context, manager: AppWidgetManager, id: Int) {
            val p=context.getSharedPreferences("oukitel",Context.MODE_PRIVATE)
            val views=RemoteViews(context.packageName,R.layout.monitor_widget)
            val charge=p.getInt("charge",-1)
            views.setTextViewText(R.id.widget_charge,if(charge>=0) "$charge%" else "—%")
            views.setTextViewText(R.id.widget_input,"Вхід: ${p.getString("input","—")}")
            views.setTextViewText(R.id.widget_output,"Вихід: ${p.getString("output","—")}")
            views.setTextViewText(R.id.widget_temp,"Температура: ${p.getString("temp","—")}")
            views.setTextViewText(R.id.widget_time,"Час роботи: ${p.getString("remaining","—")}")
            views.setTextViewText(R.id.widget_updated,"Оновлено: ${p.getString("updated","—")}")
            val intent=Intent(context,MainActivity::class.java)
            views.setOnClickPendingIntent(R.id.widget_root,PendingIntent.getActivity(context,0,intent,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE))
            manager.updateAppWidget(id,views)
        }
    }
}
