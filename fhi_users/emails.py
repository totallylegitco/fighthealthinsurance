from django.conf import settings
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from typing import TYPE_CHECKING
from fhi_users.models import VerificationToken
from fighthealthinsurance.utils import send_fallback_email
from django.utils.html import strip_tags
from loguru import logger
from smtplib import SMTPException
from django.core.exceptions import ImproperlyConfigured

if TYPE_CHECKING:
    from django.contrib.auth.models import User


def send_provider_started_appeal_email(patient_email, context):
    send_fallback_email(
        "Provider Started Appeal",
        "provider_started_appeal",
        context,
        patient_email,
    )


def send_password_reset_email(user_email: str, token: str) -> None:
    """
    Send password reset email with reset token.
    """
    subject = "Reset your password"
    send_fallback_email(
        subject,
        "password_reset",
        {
            "reset_url": f"https://www.fightpaperwork.com/reset-password/finish?token={token}"
        },
        user_email,
    )


def send_email_confirmation(user_email, context):
    send_fallback_email("Email Confirmation", "email_confirmation", context, user_email)


def send_appeal_submitted_successfully_email(user_email, context):
    send_fallback_email(
        "Appeal Submitted Successfully",
        "appeal_submitted_successfully",
        context,
        user_email,
    )


def send_error_submitting_appeal_email(user_email, context):
    send_fallback_email(
        "Error Submitting Appeal",
        "error_submitting_appeal",
        context,
        user_email,
    )


def send_verification_email(request, user: "User") -> None:
    current_site = get_current_site(request)
    mail_subject = "Activate your account."
    verification_token = default_token_generator.make_token(user)
    
    try:
        VerificationToken.objects.create(user=user, token=verification_token)
    except Exception as e:
        logger.error(f"Failed to create verification token for user {user.pk}: {e}")
        raise Exception(f"Could not create verification token for user {user.pk}") from e

    activation_link = (
        "https://www.fightpaperwork.com/activate-account/?token={}&uid={}".format(
            verification_token, user.pk
        )
    )

    try:
        send_fallback_email(
            mail_subject,
            "acc_active_email",
            {
                "user": user,
                "domain": current_site.domain,
                "activation_link": activation_link,
            },
            user.email,
        )
        logger.info(f"Verification email sent to {user.email}")
    except (SMTPException, ImproperlyConfigured) as e:
        logger.error(f"Failed to send verification email to {user.email}: {e}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred when sending email to {user.email}: {e}")
        raise