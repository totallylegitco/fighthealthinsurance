import typing

from django.urls import include
from django.urls import path
from django.conf import settings

from fighthealthinsurance.views import api
from fighthealthinsurance.views.api import AppealViewSet, MailingListSubscriberViewSet

from rest_framework import routers

if settings.DEBUG:
    RouterClass: typing.Type[routers.BaseRouter] = routers.DefaultRouter
else:
    RouterClass = routers.SimpleRouter

router = RouterClass()

router.register(r"denials", api.DenialViewSet, basename="denials")
router.register(r"next_steps", api.NextStepsViewSet, basename="nextsteps")
router.register(r"follow_up", api.FollowUpViewSet, basename="followups")
router.register(r"qaresponse", api.QAResponseViewSet, basename="qacontext")
router.register(r"statistics", api.StatisticsAPIViewSet, basename="statistics")
router.register(r"search", api.SearchAPIViewSet, basename="search")


router.register(
    r"data_removal",
    api.DataRemovalViewSet,
    basename="dataremoval",
)

router.register(r"appeals", AppealViewSet, basename="appeals")
router.register(
    r"appeal_attachments",
    api.AppealAttachmentViewSet,
    basename="appeal_attachments",
)
router.register(
    r"mailinglist_subscribe", MailingListSubscriberViewSet, basename="subscribe"
)

urlpatterns = [
    # Non-viewset but still rest API endpoints.
    path("ping", api.Ping.as_view(), name="ping"),
    path("check_storage", api.CheckStorage.as_view(), name="check_storage"),
    path(
        "check_ml_backend", api.CheckMlBackend.as_view(), name="check_ml_backend"
    ),
    # Router
    path("", include(router.urls)),
]
