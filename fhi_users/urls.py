import typing
from django.urls import include, path
from django.conf import settings
import mfa
import mfa.TrustedDevice
from fhi_users.auth import rest_auth_views
from fhi_users.auth import auth_views
from fhi_users.auth.rest_auth_views import RestLoginView, CreatePatientUserView, VerifyEmailView
from .views import view_appeals, view_individual_appeal, about_us, subscribe_for_updates
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
router.register(r'api/login', RestLoginView, basename='rest_login')
router.register(r'api/create_user', CreatePatientUserView, basename='create_user')
router.register(r'verify-email', VerifyEmailView, basename='verify_email')

urlpatterns = [
    path("login", auth_views.LoginView.as_view(), name="login"),
    path("logout", auth_views.LogoutView.as_view(), name="logout"),
    path("rest/router/", include(router.urls)),
    path("mfa/", include("mfa.urls")),
    path("device_add", mfa.TrustedDevice.add, name="mfa_add_new_trusted_device"),
    path('api/appeals/', view_appeals, name='view_appeals'),
    path('api/appeals/<int:appeal_id>/', view_individual_appeal, name='view_individual_appeal'),
    path('api/about_us/', about_us, name='about_us'),
    path('api/subscribe/', subscribe_for_updates, name='subscribe_for_updates'),
]
