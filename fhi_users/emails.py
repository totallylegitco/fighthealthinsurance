import logging

from django.conf import settings
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from typing import TYPE_CHECKING
from fhi_users.models import VerificationToken
from fighthealthinsurance.utils import send_fallback_email
from django.utils.html import strip_tags

if TYPE_CHECKING:
    from django.contrib.auth.models import User

# Initialize a logger for this module
logger = logging.getLogger(__name__)

def safe_send_email(subject: str, template: str, context: dict, recipient: str) -> None:
    """
    Sends an email using send_fallback_email with added error handling.
    Logs any exception encountered during the email sending process.
    """
    try:
        send_fallback_email(subject, template, context, recipient)
    except Exception as e:
        logger.exception("Failed to send email '%s' to %s: %s", subject, recipient, e)

def send_provider_started_appeal_email(patient_email: str, context: dict) -> None:
    safe_send_email("Provider Started Appeal", "provider_started_appeal", context, patient_email)

def send_password_reset_email(user_email: str, token: str) -> None:
    """
    Send password reset email with a reset token.
    """
    subject = "Reset your password"
    context = {
        "reset_url": f"https://www.fightpaperwork.com/reset-password/finish?token={token}"
    }
    safe_send_email(subject, "password_reset", context, user_email)

def send_email_confirmation(user_email: str, context: dict) -> None:
    safe_send_email("Email Confirmation", "email_confirmation", context, user_email)

def send_appeal_submitted_successfully_email(user_email: str, context: dict) -> None:
    safe_send_email("Appeal Submitted Successfully", "appeal_submitted_successfully", context, user_email)

def send_error_submitting_appeal_email(user_email: str, context: dict) -> None:
    safe_send_email("Error Submitting Appeal", "error_submitting_appeal", context, user_email)

def send_verification_email(request, user: "User") -> None:
    current_site = get_current_site(request)
    mail_subject = "Activate your account."
    verification_token = default_token_generator.make_token(user)
    # Record the token for later verification
    VerificationToken.objects.create(user=user, token=verification_token)
    activation_link = (
        f"https://www.fightpaperwork.com/activate-account/?token={verification_token}&uid={user.pk}"
    )
    context = {
        "user": user,
        "domain": current_site.domain,
        "activation_link": activation_link,
    }
    safe_send_email(mail_subject, "acc_active_email", context, user.email)
