import re
from typing import Any
from django.core.management.base import BaseCommand, CommandParser, CommandError
from django.core.validators import validate_email, RegexValidator
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from fhi_users.auth.auth_utils import combine_domain_and_username
from fhi_users.models import UserDomain


class Command(BaseCommand):
    """Make a new user (for local dev work) if user already exists just move on."""

    help = "Securely create a new user with proper input validation and error handling."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--username",
            required=True,
            help="User's username (alphanumeric characters and underscores only).",
        )
        parser.add_argument(
            "--email", required=True, help="User's valid email address."
        )
        parser.add_argument(
            "--password", required=True, help="User's password (minimum 8 characters)."
        )
        parser.add_argument(
            "--domain",
            required=True,
            help="Domain associated with the user (e.g., company or organization name).",
        )
        parser.add_argument(
            "--visible-phone-number",
            required=True,
            help="Visible phone number for the domain.",
        )
        parser.add_argument(
            "--is-provider",
            type=lambda x: x.lower() in ["true", "1", "yes"],
            default=False,
            help="Set to 'true' if the user is a provider; otherwise 'false'.",
        )

    def handle(self, *args: str, **options: Any) -> None:
        User = get_user_model()

        # Directly index into options since these are required
        username_raw = options["username"].strip()
        email = options["email"].strip()
        password = options["password"]
        domain_input = options["domain"].strip()
        visible_phone_number = options.get("visible_phone_number", "0").strip()
        is_provider = options.get("is_provider", True)

        # Enhanced username validation
        if not re.match(r"^[a-zA-Z0-9_]{3,30}$", username_raw):
            raise CommandError(
                "Invalid username. Only alphanumeric characters and underscores are allowed."
            )

        try:
            validate_email(email)
        except ValidationError:
            raise CommandError("Invalid email address provided.")

        if len(password) < 8:
            raise CommandError("Password must be at least 8 characters long.")
        
        if not any(c.isupper() for c in password) or not any(c.islower() for c in password) or not any(c.isdigit() for c in password):
            raise CommandError("Password must contain at least one uppercase letter, one lowercase letter, and one digit.")

        # Domain validation
        domain_clean = domain_input.strip()
        if not domain_clean or len(domain_clean) < 2:
            raise CommandError("Domain name must be at least 2 characters long.")
        
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", domain_clean):
            raise CommandError("Domain name contains invalid characters.")

        # Phone number validation
        phone_validator = RegexValidator(
            regex=r"^\+?1?\d{9,15}$",
            message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
        )
        try:
            phone_validator(visible_phone_number)
        except ValidationError as e:
            raise CommandError(f"Invalid phone number: {e}")

        try:
            user_domain, created = UserDomain.objects.get_or_create(
                name=domain_clean,
                defaults={"active": True, "visible_phone_number": visible_phone_number},
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f"Domain '{domain_clean}' created successfully.")
                )
            else:
                self.stdout.write(f"Domain '{domain_clean}' already exists.")
        except Exception as e:
            raise CommandError(f"Error handling domain creation: {str(e)}")

        try:
            combined_username = combine_domain_and_username(
                username_raw, domain_name=user_domain.name
            )
        except Exception as e:
            raise CommandError(f"Error combining username and domain: {str(e)}")

        if User.objects.filter(username=combined_username).exists():
            self.stdout.write(
                f"User with username '{combined_username}' already exists."
            )
        else:
            try:
                user = User.objects.create_user(
                    username=combined_username,
                    email=email,
                    password=password,
                )
                if hasattr(user, "is_provider"):
                    user.is_provider = is_provider
                    user.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"User '{combined_username}' created successfully."
                    )
                )
            except Exception as e:
                raise CommandError(f"Failed to create user: {str(e)}")
