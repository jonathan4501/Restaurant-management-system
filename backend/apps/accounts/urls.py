"""Auth and device URL routes. Guest-token path lives under /sessions/ (floor's namespace)."""

from django.urls import path

from . import views

urlpatterns = [
    path("devices/enrol", views.EnrolDeviceView.as_view(), name="devices-enrol"),
    path("devices/me", views.DeviceMeView.as_view(), name="devices-me"),
    path("auth/pin", views.PinLoginView.as_view(), name="auth-pin"),
    path("auth/authorise", views.AuthoriseView.as_view(), name="auth-authorise"),
    path("auth/owner/login", views.OwnerLoginView.as_view(), name="auth-owner-login"),
    path("auth/owner/totp", views.OwnerTotpView.as_view(), name="auth-owner-totp"),
    path("auth/owner/me", views.OwnerMeView.as_view(), name="auth-owner-me"),
    path("auth/logout", views.LogoutView.as_view(), name="auth-logout"),
    path(
        "sessions/<uuid:session_id>/guest-token",
        views.GuestTokenView.as_view(),
        name="session-guest-token",
    ),
    # UUID first so guest session reads win over the QR token path.
    path(
        "guest/sessions/<uuid:session_id>",
        views.GuestSessionDetailView.as_view(),
        name="guest-session-detail",
    ),
    path(
        "guest/sessions/<str:qr_token>",
        views.QrGuestSessionView.as_view(),
        name="guest-qr-session",
    ),
]
