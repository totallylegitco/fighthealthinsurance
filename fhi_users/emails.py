from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import User

def send_email(subject, template_name, context, to_email):
    message = render_to_string(template_name, context)
    send_mail(subject, message, settings.EMAIL_HOST_USER, [to_email])

def send_provider_started_appeal_email(patient_email, context):
    send_email('Provider Started Appeal', 'emails/provider_started_appeal.html', context, patient_email)

def send_password_reset_email(user_email, context):
    send_email('Password Reset', 'emails/password_reset.html', context, user_email)

def send_email_confirmation(user_email, context):
    send_email('Email Confirmation', 'emails/email_confirmation.html', context, user_email)

def send_appeal_submitted_successfully_email(user_email, context):
    send_email('Appeal Submitted Successfully', 'emails/appeal_submitted_successfully.html', context, user_email)

def send_error_submitting_appeal_email(user_email, context):
    send_email('Error Submitting Appeal', 'emails/error_submitting_appeal.html', context, user_email)

def send_verification_email(request, user: 'User') -> None:
    current_site = get_current_site(request)
    mail_subject = 'Activate your account.'
    message = render_to_string('acc_active_email.html', {
        'user': user,
        'domain': current_site.domain,
        'uid': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': default_token_generator.make_token(user),
    })
    to_email = user.email
    send_mail(mail_subject, message, settings.EMAIL_HOST_USER, [to_email])
