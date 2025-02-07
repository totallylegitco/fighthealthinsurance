import typing

from django.urls import include
from django.urls import path
from django.conf import settings
import mfa
import mfa.TrustedDevice

from fhi_users.auth import rest_auth_views
from fhi_users.auth import auth_views

from rest_framework import routers

if settings.DEBUG:
    RouterClass: typing.Type[routers.BaseRouter] = routers.DefaultRouter
else:
    RouterClass = routers.SimpleRouter

router = RouterClass()
router.register(
    r"create_professional_user",
    rest_auth_views.CreateProfessionalUser,
    basename="create_pro_user",
)
router.register(
    r"admin_professional_user",
    rest_auth_views.AdminProfessionalUser,
    basename="admin_pro_user",
)

urlpatterns = [
    # Auth related views
    path("login", auth_views.LoginView.as_view(), name="login"),  # Login
    path("logout", auth_views.LogoutView.as_view(), name="logout"),  # Logout
    path("rest/router/", include(router.urls)),
    path("mfa/", include("mfa.urls")),  # Include MFA URLs for handling MFA processes.
    path(
        "device_add", mfa.TrustedDevice.add, name="mfa_add_new_trusted_device"
    ),  # Add device
]
