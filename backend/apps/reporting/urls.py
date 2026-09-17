from django.urls import path

from apps.reporting.views import EventLogView, PatternsView, TodayView, VarianceView

urlpatterns = [
    path("reports/variance", VarianceView.as_view(), name="reports-variance"),
    path("reports/today", TodayView.as_view(), name="reports-today"),
    path("reports/patterns", PatternsView.as_view(), name="reports-patterns"),
    path("events/log", EventLogView.as_view(), name="events-log"),
]
