from django.urls import path

from .views import EventsView, stream

urlpatterns = [
    path("stream", stream, name="stream"),
    path("events", EventsView.as_view(), name="events"),
]
