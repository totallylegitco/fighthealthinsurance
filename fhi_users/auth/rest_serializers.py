from drf_braces.serializers.form_serializer import (
    FormSerializer,
)
from .auth_forms import DomainAuthenticationForm, TOTPForm, PasswordResetForm
from rest_framework import serializers
from django.contrib.auth import get_user_model
from fhi_users.models import *

User = get_user_model()


class DomainAuthenticationFormSerializer(FormSerializer):
    class Meta(object):
        form = DomainAuthenticationForm


class TOTPFormSerializer(FormSerializer):
    class Meta(object):
        form = TOTPForm


class PasswordResetFormSerializer(FormSerializer):
    class Meta(object):
        form = PasswordResetForm


class DomainAuthResponse(serializers.Serializer):
    success = serializers.BooleanField()
    error_description = serializers.CharField()
    totp_info = serializers.CharField()
    user_type = serializers.ChoiceField(choices=["provider", "admin", "patient"])


class TOTPResponse(serializers.Serializer):
    success = serializers.BooleanField()
    error_description = serializers.CharField()
    totp_info = serializers.CharField()


class UserSignupSerializer(serializers.ModelSerializer):
    domain_name = serializers.CharField()
    continue_url = serializers.CharField()  # URL to send user to post signup / payment

    class Meta(object):
        model = User
        fields = [
            # Ones from our model
            "username",
            "first_name",
            "last_name",
            "password",
            "email",
            "domain_name",
            # Our own internal fields
            "domain_name",
            "continue_url",
        ]


class UserDomainSerializer(serializers.ModelSerializer):
    class Meta(object):
        model = UserDomain
        exclude = ("id", "stripe_subscription_id", "active")


class ProfessionalSignupSerializer(serializers.ModelSerializer):
    user_signup_info = UserSignupSerializer()
    make_new_domain = serializers.BooleanField()
    # If they're joining an existing domain
    user_domain = UserDomainSerializer(required=False)

    class Meta(object):
        model = ProfessionalUser
        fields = ["npi_number", "make_new_domain", "user_signup_info", "user_domain"]


class ProfessionalSignupResponseSerializer(serializers.Serializer):
    next_url = serializers.URLField()


class AcceptProfessionalUserSerializer(serializers.Serializer):
    professional_user_id = serializers.IntegerField()
    domain_id = serializers.CharField()
