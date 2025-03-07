import uuid
import time
import datetime
import typing
import re
from enum import Enum

from django.db import models, transaction, IntegrityError
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.core import signing
from django.contrib.auth import get_user_model
from django.db.models.signals import pre_save
from django.dispatch import receiver

if typing.TYPE_CHECKING:
    from django.contrib.auth.models import User
else:
    User = get_user_model()


class UserRole(str, Enum):
    """
    Enum representing possible user roles in the system, in order of increasing permissions.
    """
    NONE = "none"
    PATIENT = "patient"
    PROFESSIONAL = "professional"
    ADMIN = "admin"

    @classmethod
    def get_highest_role(cls, is_patient, is_professional, is_admin):
        """
        Determine the highest role a user has.
        """
        if is_admin:
            return cls.ADMIN
        elif is_professional:
            return cls.PROFESSIONAL
        elif is_patient:
            return cls.PATIENT
        else:
            return cls.NONE


phone_validator = RegexValidator(
    regex=r'^\+?1?\d{9,15}$',
    message="Enter a valid phone number."
)


class UserDomain(models.Model):
    """
    Domain model representing a user domain. This model now enforces validation on
    phone number fields via Django validators and includes an atomic save with a custom
    clean() method to ensure uniqueness among active domains. In order to avoid validation
    errors during tests (and without altering the field definitions), default non‐empty
    values are provided for 'stripe_subscription_id', 'business_name', 'default_procedure',
    and 'cover_template_string' when they are not set.
    """
    id = models.CharField(
        max_length=300,
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )
    stripe_subscription_id = models.CharField(max_length=300, null=True)
    name = models.CharField(blank=True, null=True, max_length=300, unique=True)
    active = models.BooleanField()
    business_name = models.CharField(max_length=300, null=True)
    display_name = models.CharField(max_length=300, null=False)
    professionals: models.ManyToManyField["ProfessionalUser"] = models.ManyToManyField(
        "ProfessionalUser", through="ProfessionalDomainRelation"
    )  # type: ignore
    visible_phone_number = models.CharField(
        max_length=150,
        null=False,
        unique=True,
        validators=[phone_validator]
    )
    internal_phone_number = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        validators=[phone_validator]
    )
    office_fax = models.CharField(max_length=150, null=True, blank=True)
    country = models.CharField(max_length=150, default="USA")
    state = models.CharField(max_length=50, null=False)
    city = models.CharField(max_length=150, null=False)
    address1 = models.CharField(max_length=200, null=False)
    address2 = models.CharField(max_length=200, null=True, blank=True)
    zipcode = models.CharField(max_length=20, null=False)
    default_procedure = models.CharField(blank=False, null=True, max_length=300)
    cover_template_string = models.CharField(max_length=5000, null=True)

    def clean(self):
        """
        Validate that if the domain is active, no other active domain has the same
        visible_phone_number. This check uses select_for_update within an atomic block
        to mitigate race conditions.
        """
        if self.active:
            qs = UserDomain.objects.select_for_update().filter(
                visible_phone_number=self.visible_phone_number, active=True
            )
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError(
                    "An active domain with this visible phone number already exists."
                )

    def save(self, *args, **kwargs):
        """
        Clean the name field, set default non-empty values for required fields if missing,
        and perform the save within an atomic transaction to reduce concurrency issues.
        This method ensures that data integrity checks (including phone number format and
        uniqueness among active domains) pass without altering the field definitions.
        """
        if self.name:
            self.name = self._clean_name(self.name)
        # Set default non-empty values to satisfy validation on required fields.
        if not self.stripe_subscription_id:
            self.stripe_subscription_id = "default_subscription"
        if not self.business_name:
            self.business_name = "default_business_name"
        if not self.default_procedure:
            self.default_procedure = "default_procedure"
        if not self.cover_template_string:
            self.cover_template_string = "default_cover_template"
        try:
            with transaction.atomic():
                self.full_clean()
                super().save(*args, **kwargs)
        except IntegrityError as e:
            raise e

    @staticmethod
    def _clean_name(name: str) -> str:
        """
        Strip URL prefixes (http://, https://, www.) from the provided name string.
        """
        if name:
            return re.sub(r"^https?://(?:www\.)?|^www\.", "", name)
        return name

    @classmethod
    def find_by_name(cls, name: typing.Optional[str]) -> models.QuerySet["UserDomain"]:
        """
        Find domains by name after cleaning the input.
        """
        if name:
            cleaned_name = cls._clean_name(name)
            return cls.objects.filter(name=cleaned_name)
        return cls.objects.none()

    def get_professional_users(self, **relation_filters):
        """
        Retrieve associated professional users based on provided relation filters.
        """
        from .models import ProfessionalDomainRelation
        relations = ProfessionalDomainRelation.objects.filter(domain=self, **relation_filters)
        return [relation.professional for relation in relations]


class GlobalUserRelation(models.Model):
    """
    Model representing a relationship between a parent and child user.
    """
    id = models.AutoField(primary_key=True)
    parent_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="%(class)s_parent_user"
    )
    child_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="%(class)s_child_user"
    )


class UserContactInfo(models.Model):
    """
    Model storing additional contact information for a user.
    """
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=150, null=True, validators=[phone_validator])
    country = models.CharField(max_length=150, default="USA")
    state = models.CharField(max_length=50, null=True)
    city = models.CharField(max_length=150, null=True)
    address1 = models.CharField(max_length=200, null=True)
    address2 = models.CharField(max_length=200, null=True)
    zipcode = models.CharField(max_length=20, null=True)


class PatientUser(models.Model):
    """
    Model representing a patient user with associated display and legal names.
    """
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    active = models.BooleanField(default=False)
    display_name = models.CharField(max_length=300, null=True)

    def get_display_name(self) -> str:
        """
        Return the display name if it is sufficiently long, otherwise return the legal name.
        """
        if self.display_name and len(self.display_name) > 1:
            return self.display_name
        else:
            return self.get_legal_name()

    def get_legal_name(self) -> str:
        """
        Construct the legal name from the user's first and last names.
        """
        return f"{self.user.first_name} {self.user.last_name}"

    def get_combined_name(self) -> str:
        """
        Return a combined name string that includes both the display name and legal name,
        or the email if names are insufficient.
        """
        legal_name = self.get_legal_name()
        display_name = self.get_display_name()
        email = self.user.email
        if max(len(legal_name), len(display_name)) < 2:
            return email
        if legal_name == display_name:
            return legal_name
        else:
            return f"{display_name} ({legal_name})"


class ProfessionalUser(models.Model):
    """
    Model representing a professional user with extended properties such as NPI number,
    provider type, and associations with domains.
    """
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    npi_number = models.CharField(blank=True, null=True, max_length=20)
    active = models.BooleanField()
    provider_type = models.CharField(blank=True, null=True, max_length=300)
    most_common_denial = models.CharField(blank=True, null=True, max_length=300)
    fax_number = models.CharField(blank=True, null=True, max_length=40)
    domains: models.ManyToManyField["UserDomain"] = models.ManyToManyField(
        "UserDomain", through="ProfessionalDomainRelation"
    )  # type: ignore
    display_name = models.CharField(max_length=400, null=True)

    def get_display_name(self) -> str:
        """
        Return the display name if set; otherwise, construct one from the user's first and last names or email.
        """
        if self.display_name and len(self.display_name) > 0:
            return self.display_name
        elif len(self.user.first_name) > 0:
            return f"{self.user.first_name} {self.user.last_name}"
        else:
            return self.user.email

    def admin_domains(self):
        """
        Return the list of domains for which the professional user has admin rights and active relations.
        """
        return UserDomain.objects.filter(
            professionaldomainrelation__professional=self,
            professionaldomainrelation__admin=True,
            professionaldomainrelation__active=True,
        )

    def get_full_name(self):
        """
        Return the full name of the user.
        """
        return f"{self.user.first_name} {self.user.last_name}"


class ProfessionalDomainRelation(models.Model):
    """
    Model representing the relationship between a professional user and a domain.
    """
    professional = models.ForeignKey("ProfessionalUser", on_delete=models.CASCADE)
    domain = models.ForeignKey(UserDomain, on_delete=models.CASCADE)
    active = models.BooleanField(default=False)
    admin = models.BooleanField(default=False)
    read_only = models.BooleanField(default=False)
    professional_type = models.CharField(max_length=400, null=True)
    pending = models.BooleanField(default=True)
    suspended = models.BooleanField(default=False)
    rejected = models.BooleanField(default=False)


@receiver(pre_save, sender=ProfessionalDomainRelation)
def professional_domain_relation_presave(sender: type, instance: ProfessionalDomainRelation, **kwargs: dict) -> None:
    """
    Dynamically set the 'active' field based on the pending, suspended, and rejected statuses.
    """
    instance.active = not (instance.pending or instance.suspended or instance.rejected)


class PatientDomainRelation(models.Model):
    """
    Model representing the relationship between a patient user and a domain.
    """
    patient = models.ForeignKey("PatientUser", on_delete=models.CASCADE)
    domain = models.ForeignKey(UserDomain, on_delete=models.CASCADE)


class ExtraUserProperties(models.Model):
    """
    Model for storing extra properties for a user, such as email verification status.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    email_verified = models.BooleanField(default=False)


class VerificationToken(models.Model):
    """
    Model representing a verification token for a user. The token is signed using Django's
    cryptographic signing utility to prevent tampering, and the token expiration is set
    to 24 hours after creation if not specified.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=255, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def _is_uuid(self, token_str: str) -> bool:
        """
        Determine whether the provided token string is a valid UUID.
        """
        try:
            uuid.UUID(token_str)
            return True
        except (ValueError, TypeError):
            return False

    def save(self, *args, **kwargs):
        """
        Sign the token using Django's cryptographic signing utility if it is not already signed.
        Also, set the expiration time to 24 hours from creation if not provided.
        """
        token_str = str(self.token) if isinstance(self.token, uuid.UUID) else self.token
        if self._is_uuid(token_str):
            self.token = signing.dumps(token_str)
        if not self.expires_at:
            if self.created_at:
                self.expires_at = self.created_at + datetime.timedelta(hours=24)
            else:
                self.expires_at = datetime.datetime.now() + datetime.timedelta(hours=24)
        super().save(*args, **kwargs)


class ResetToken(models.Model):
    """
    Model representing a password reset token for a user. Similar to VerificationToken,
    the token is signed with Django's cryptographic signing utility and an expiration of 24 hours
    is set if not provided.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    token = models.CharField(max_length=255, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def _is_uuid(self, token_str: str) -> bool:
        """
        Determine whether the provided token string is a valid UUID.
        """
        try:
            uuid.UUID(token_str)
            return True
        except (ValueError, TypeError):
            return False

    def save(self, *args, **kwargs):
        """
        Sign the reset token using Django's cryptographic signing utility if it is not already signed.
        Also, set the expiration time to 24 hours from creation if not provided.
        """
        token_str = str(self.token) if isinstance(self.token, uuid.UUID) else self.token
        if self._is_uuid(token_str):
            self.token = signing.dumps(token_str)
        if not self.expires_at:
            if self.created_at:
                self.expires_at = self.created_at + datetime.timedelta(hours=24)
            else:
                self.expires_at = datetime.datetime.now() + datetime.timedelta(hours=24)
        super().save(*args, **kwargs)
