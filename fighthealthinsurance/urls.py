"""fighthealthinsurance URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from typing import List, Union, Callable, Dict

from django.urls import URLPattern, URLResolver
from django.contrib import admin
from django.http import HttpRequest, HttpResponseBase, HttpResponse, HttpResponseForbidden
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path, re_path
from django.views.decorators.cache import cache_control, cache_page
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import RedirectView
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.exceptions import PermissionDenied
import re
import time

from fighthealthinsurance import views
from fighthealthinsurance import fax_views
from fighthealthinsurance import staff_views
from django.views.decorators.debug import sensitive_post_parameters
import os

def trigger_error(request: HttpRequest) -> HttpResponseBase:
    raise Exception("Test error")


# Add security middleware
class SecurityScanMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponseBase]):
        self.get_response = get_response
        # Add patterns for potentially malicious requests
        self.security_patterns = [
            r'(?i)(<|%3C)script',  # XSS attempts
            r'(?i)(union|select|insert|drop|delete)\s+',  # SQL injection attempts
            r'(?i)(/\.\./|\.\./)',  # Path traversal attempts
            # Add patterns for sensitive endpoints
            r'(?i)(rest_verify_email|password_reset|login|logout|device_add)',  # Sensitive routes
            r'(?i)(admin|webhook)',  # Administrative routes
        ]
        self.patterns = [re.compile(pattern) for pattern in self.security_patterns]
        # Initialize rate limiting with type annotation
        self.request_history: Dict[str, List[float]] = {}
        self.rate_limit = 30  # requests
        self.time_window = 300  # 5 minutes in seconds

    def __call__(self, request: HttpRequest) -> HttpResponseBase:
        # Check for security scan patterns
        path = request.path
        query = request.META.get('QUERY_STRING', '')
        content = path + query
        
        # Get client IP with a default value and type checking
        client_ip: str = request.META.get('REMOTE_ADDR', '')
        if not client_ip:
            return HttpResponseForbidden("Could not determine client IP")

        # Rate limiting for sensitive endpoints
        if any(pattern in path.lower() for pattern in ['login', 'logout', 'password_reset', 'rest_verify_email', 'admin', 'webhook']):
            current_time = time.time()
            
            # Clean up old entries
            self.request_history = {
                ip: times for ip, times in self.request_history.items()
                if times[-1] > current_time - self.time_window
            }
            
            # Check rate limit
            if client_ip in self.request_history:
                times = self.request_history[client_ip]
                if len(times) >= self.rate_limit:
                    return HttpResponseForbidden("Rate limit exceeded")
                times.append(current_time)
            else:
                self.request_history[client_ip] = [current_time]

        # Check for security violations
        for pattern in self.patterns:
            if pattern.search(content):
                return HttpResponseForbidden("Security violation detected")

        # Explicitly type the response
        response: HttpResponseBase = self.get_response(request)
        return response


urlpatterns: List[Union[URLPattern, URLResolver]] = [
    # Add security monitoring endpoint for authorized scanners
    path('security/', staff_member_required(views.SecurityScanView.as_view())),
    # Internal-ish-views
    path("ziggy/rest/", include("fighthealthinsurance.rest_urls")),
    path("timbit/sentry-debug/", trigger_error),
    # Add webhook handler
    path(
        "webhook/stripe/",
        csrf_exempt(views.StripeWebhookView.as_view()),
        name="stripe-webhook",
    ),
    re_path("timbit/sentry-debug/(?P<path>.+)", trigger_error, name="fake_fetch_url"),
    path("timbit/charts/", include(("charts.urls", "charts"), namespace="charts")),
    path("timbit/admin/", admin.site.urls),
    path("", include("django_prometheus.urls")),
    path(
        "timbit/help/followup_sched",
        staff_member_required(staff_views.ScheduleFollowUps.as_view()),
    ),
    path(
        "timbit/help/followup_sender_test",
        staff_member_required(staff_views.FollowUpEmailSenderView.as_view()),
    ),
    path(
        "timbit/help/thankyou_sender_test",
        staff_member_required(staff_views.ThankyouSenderView.as_view()),
    ),
    path(
        "timbit/help/followup_fax_test",
        staff_member_required(staff_views.FollowUpFaxSenderView.as_view()),
    ),
    path(
        "timbit/help/activate_pro",
        staff_member_required(staff_views.ActivateProUserView.as_view()),
        name="activate_pro",
    ),
    # Authentication
    path("v0/auth/", include("fhi_users.urls")),
    # stripe integration (TODO webhooks go here)
    # These are links we e-mail people so might have some extra junk.
    # So if there's an extra / or . at the end we ignore it.
    path(
        "v0/followup/<uuid:uuid>/<slug:hashed_email>/<slug:follow_up_semi_sekret>",
        views.FollowUpView.as_view(),
        name="followup",
    ),
    path(
        "v0/followup/<uuid:uuid>/<slug:hashed_email>/<slug:follow_up_semi_sekret>.",
        views.FollowUpView.as_view(),
        name="followup-with-a-period",
    ),
    path(
        "v0/followup/<uuid:uuid>/<slug:hashed_email>/<slug:followup_semi_sekret>/",
        views.FollowUpView.as_view(),
        name="followup-with-trailing-slash",
    ),
    # Fax follow up
    # So if there's an extra / or . at the end we ignore it.
    path(
        "v0/faxfollowup/<uuid:uuid>/<slug:hashed_email>",
        fax_views.FaxFollowUpView.as_view(),
        name="fax-followup",
    ),
    path(
        "v0/faxfollowup/<uuid:uuid>/<slug:hashed_email>.",
        fax_views.FaxFollowUpView.as_view(),
        name="fax-followup-with-a-period",
    ),
    path(
        "v0/faxfollowup/<uuid:uuid>/<slug:hashed_email>/",
        fax_views.FaxFollowUpView.as_view(),
        name="fax-followup-with-trailing-slash",
    ),
    # Back to normal stuff
    path(
        "v0/sendfax/<uuid:uuid>/<slug:hashed_email>/",
        fax_views.SendFaxView.as_view(),
        name="sendfaxview",
    ),
    path(
        "v0/stagefax",
        fax_views.StageFaxView.as_view(),
        name="stagefaxview",
    ),
    # View an appeal
    path(
        "v0/appeal/<uuid:appeal_uuid>/appeal.pdf",
        views.AppealFileView.as_view(),
        name="appeal_file_view",
    ),
    path(
        "process",
        sensitive_post_parameters("email")(views.InitialProcessView.as_view()),
        name="process",
    ),
    path(
        "v0/combined_collected_view",
        sensitive_post_parameters("email")(views.DenialCollectedView.as_view()),
        name="dvc",
    ),
    path("v0/plan_documents", views.PlanDocumentsView.as_view(), name="hh"),
    path("v0/categorize", views.EntityExtractView.as_view(), name="eev"),
    path(
        "server_side_ocr",
        sensitive_post_parameters("email")(views.OCRView.as_view()),
        name="server_side_ocr",
    ),
    path(
        "about-us",
        cache_control(public=True)(cache_page(60 * 60 * 2)(views.AboutView.as_view())),
        name="about",
    ),
    path(
        "other-resources",
        sensitive_post_parameters("email")(views.OtherResourcesView.as_view()),
        name="other-resources",
    ),
    path(
        "pro_version", csrf_exempt(views.ProVersionView.as_view()), name="pro_version"
    ),
    path(
        "pro_version_thankyou",
        csrf_exempt(views.ProVersionThankYouView.as_view()),
        name="pro_version_thankyou",
    ),
    path("privacy_policy", views.PrivacyPolicyView.as_view(), name="privacy_policy"),
    path("share_denial", views.ShareDenialView.as_view(), name="share_denial"),
    path("share_appeal", views.ShareAppealView.as_view(), name="share_appeal"),
    path("remove_data", views.RemoveDataView.as_view(), name="remove_data"),
    path(
        "tos",
        cache_control(public=True)(
            cache_page(60 * 60 * 2)(views.TermsOfServiceView.as_view())
        ),
        name="tos",
    ),
    path(
        "find_next_steps",
        sensitive_post_parameters("email")(views.FindNextSteps.as_view()),
        name="find_next_steps",
    ),
    path(
        "generate_appeal",
        sensitive_post_parameters("email")(views.GenerateAppeal.as_view()),
        name="generate_appeal",
    ),
    path(
        "choose_appeal",
        sensitive_post_parameters("email")(views.ChooseAppeal.as_view()),
        name="choose_appeal",
    ),
    path(
        "contact",
        cache_control(public=True)(
            cache_page(60 * 60 * 2)(views.ContactView.as_view())
        ),
        name="contact",
    ),
    path(
        "favicon.ico",
        RedirectView.as_view(url=staticfiles_storage.url("images/favicon.ico")),
    ),
]

# Don't break people already in the flow but "drain" the people by replacing scan & index w/ BRB view.
if os.getenv("BRB") == "BRB":
    urlpatterns += [
        path(r"", views.BRB.as_view(), name="brb"),
    ]
else:
    urlpatterns += [
        path(
            "",
            cache_control(public=True)(
                cache_page(60 * 60 * 2)(views.IndexView.as_view())
            ),
            name="root",
        ),
        path(
            "scan",
            sensitive_post_parameters("email")(views.InitialProcessView.as_view()),
            name="scan",
        ),
    ]


urlpatterns += staticfiles_urlpatterns()
