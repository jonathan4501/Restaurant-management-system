from django.urls import path

from apps.printing.views import (
    RequestReceiptView,
    printer_stations,
    printer_stream,
    receipt_bytes,
    ticket_bytes,
)

urlpatterns = [
    path("print/receipt", RequestReceiptView.as_view(), name="print-receipt"),
    path("print/stream", printer_stream, name="print-stream"),
    path("print/tickets/<uuid:order_id>", ticket_bytes, name="print-ticket"),
    path("print/tickets/<uuid:order_id>/stations", printer_stations, name="print-ticket-stations"),
    path("print/receipts/<uuid:session_id>", receipt_bytes, name="print-receipt-bytes"),
]
