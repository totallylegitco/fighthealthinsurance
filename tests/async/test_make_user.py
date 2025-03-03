from io import StringIO
from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from fhi_users.models import UserDomain

User = get_user_model()


class MakeUserCommandTest(TestCase):
    def setUp(self):
        self.out = StringIO()

    def test_valid_user_creation(self):
        """Test that a valid user can be created successfully."""
        args = [
            "--username=testuser",
            "--email=test@example.com",
            "--password=TestPass123",
            "--domain=testdomain",
            "--visible-phone-number=+12345678901",
            "--is-provider=true",
        ]
        
        call_command("make_user", *args, stdout=self.out)
        self.assertIn("created successfully", self.out.getvalue())
        self.assertTrue(User.objects.filter(email="test@example.com").exists())
        self.assertTrue(UserDomain.objects.filter(name="testdomain").exists())

    def test_invalid_username(self):
        """Test that invalid usernames are rejected."""
        args = [
            "--username=test@user",
            "--email=test@example.com",
            "--password=TestPass123",
            "--domain=testdomain",
            "--visible-phone-number=+12345678901",
        ]
        
        with self.assertRaises(CommandError) as context:
            call_command("make_user", *args)
        
        self.assertIn("Invalid username", str(context.exception))
        
        args[0] = "--username=ab"
        
        with self.assertRaises(CommandError) as context:
            call_command("make_user", *args)
        
        self.assertIn("Invalid username", str(context.exception))

    def test_invalid_email(self):
        """Test that invalid emails are rejected."""
        args = [
            "--username=testuser",
            "--email=invalid-email",
            "--password=TestPass123",
            "--domain=testdomain",
            "--visible-phone-number=+12345678901",
        ]
        
        with self.assertRaises(CommandError) as context:
            call_command("make_user", *args)
        
        self.assertIn("Invalid email", str(context.exception))

    def test_weak_password(self):
        """Test that weak passwords are rejected."""
        args = [
            "--username=testuser",
            "--email=test@example.com",
            "--password=Short1", 
            "--domain=testdomain",
            "--visible-phone-number=+12345678901",
        ]
        
        with self.assertRaises(CommandError) as context:
            call_command("make_user", *args)
        
        self.assertIn("Password must be at least 8 characters", str(context.exception))
        
        args[2] = "--password=password123"
        
        with self.assertRaises(CommandError) as context:
            call_command("make_user", *args)
        
        self.assertIn("Password must contain", str(context.exception))
        
        args[2] = "--password=PASSWORD123"
        
        with self.assertRaises(CommandError) as context:
            call_command("make_user", *args)
        
        self.assertIn("Password must contain", str(context.exception))
        
        args[2] = "--password=PasswordOnly"
        
        with self.assertRaises(CommandError) as context:
            call_command("make_user", *args)
        
        self.assertIn("Password must contain", str(context.exception))

    def test_invalid_domain(self):
        """Test that invalid domains are rejected."""
        args = [
            "--username=testuser",
            "--email=test@example.com",
            "--password=TestPass123",
            "--domain=a",
            "--visible-phone-number=+12345678901",
        ]
        
        with self.assertRaises(CommandError) as context:
            call_command("make_user", *args)
        
        self.assertIn("Domain name must be at least 2 characters", str(context.exception))
        
        args[3] = "--domain=test@domain"
        
        with self.assertRaises(CommandError) as context:
            call_command("make_user", *args)
        
        self.assertIn("Domain name contains invalid characters", str(context.exception))

    def test_invalid_phone_number(self):
        """Test that invalid phone numbers are rejected."""
        args = [
            "--username=testuser",
            "--email=test@example.com",
            "--password=TestPass123",
            "--domain=testdomain",
            "--visible-phone-number=invalid-phone",
        ]
        
        with self.assertRaises(CommandError) as context:
            call_command("make_user", *args)
        
        self.assertIn("Invalid phone number", str(context.exception))

    def test_existing_user(self):
        """Test behavior when trying to create a user that already exists."""
        args = [
            "--username=existinguser",
            "--email=existing@example.com",
            "--password=TestPass123",
            "--domain=testdomain",
            "--visible-phone-number=+12345678901",
        ]
        
        call_command("make_user", *args, stdout=self.out)
        self.out.seek(0)
        
        call_command("make_user", *args, stdout=self.out)
        
        self.assertIn("already exists", self.out.getvalue())
