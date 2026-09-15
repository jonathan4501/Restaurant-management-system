from django.urls import path

from apps.floor.views import (
    CloseSessionView,
    OpenSessionView,
    SessionBillView,
    SessionDetailView,
    TablesView,
)

urlpatterns = [
    path("tables", TablesView.as_view(), name="tables"),
    path("sessions", OpenSessionView.as_view(), name="sessions-open"),
    path("sessions/<uuid:session_id>", SessionDetailView.as_view(), name="sessions-detail"),
    path("sessions/<uuid:session_id>/bill", SessionBillView.as_view(), name="sessions-bill"),
    path("sessions/<uuid:session_id>/close", CloseSessionView.as_view(), name="sessions-close"),
]
