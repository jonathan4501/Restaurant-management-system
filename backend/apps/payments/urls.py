from django.urls import path

from apps.payments.views import (
    CloseShiftView,
    CurrentShiftView,
    DrawerMovementView,
    OpenBillsView,
    OpenShiftView,
    RecordPaymentView,
    ReopenSessionView,
    VoidPaymentView,
    ZReportView,
)

urlpatterns = [
    path("shifts/current", CurrentShiftView.as_view(), name="shifts-current"),
    path("shifts", OpenShiftView.as_view(), name="shifts-open"),
    path("shifts/<uuid:shift_id>/movements", DrawerMovementView.as_view(), name="shifts-movement"),
    path("shifts/<uuid:shift_id>/close", CloseShiftView.as_view(), name="shifts-close"),
    path("shifts/<uuid:shift_id>/z-report", ZReportView.as_view(), name="shifts-z-report"),
    path("bills/open", OpenBillsView.as_view(), name="bills-open"),
    path(
        "sessions/<uuid:session_id>/payments",
        RecordPaymentView.as_view(),
        name="sessions-payments",
    ),
    path("payments/<uuid:payment_id>/void", VoidPaymentView.as_view(), name="payments-void"),
    path("sessions/<uuid:session_id>/reopen", ReopenSessionView.as_view(), name="sessions-reopen"),
]
