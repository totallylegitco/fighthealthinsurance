from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from fighthealthinsurance.models import Appeal
from fhi_users.models import PatientUser, ProfessionalUser
from django.core.files.uploadedfile import SimpleUploadedFile


class AppealFileViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        # Create the initial provider user has domain access
        professional_create_url = reverse("professional_user-list")
        data = {
            "user_signup_info": {
                "username": "newprouser_domain_admin",
                "password": "newpass",
                "email": "newprouser_domain_admin@example.com",
                "first_name": "New",
                "last_name": "User",
                "domain_name": "newdomain",
                "visible_phone_number": "1234567891",
                "continue_url": "http://example.com/continue",
            },
            "make_new_domain": True,
            "user_domain": {
                "name": "newdomain",
                "visible_phone_number": "1234567891",
                "internal_phone_number": "0987654322",
                "display_name": "New Domain",
                "country": "USA",
                "state": "CA",
                "city": "New City",
                "address1": "456 New St",
                "zipcode": "67890",
            },
        }
        response = self.client.post(professional_create_url, data, format="json")
        self.assertIn(response.status_code, range(200, 300))
        # Create a second provider user in same domain (should not have access)
        data = {
            "user_signup_info": {
                "username": "newprouser_unrelated",
                "password": "newpass",
                "email": "newprouser_unrelated@example.com",
                "first_name": "New",
                "last_name": "User",
                "domain_name": "newdomain",
                "visible_phone_number": "1234567891",
                "continue_url": "http://example.com/continue",
            },
            "make_new_domain": False,
        }
        response = self.client.post(professional_create_url, data, format="json")
        self.assertIn(response.status_code, range(200, 300))
        # Create a third provider user in same domain (this one creates the appeal so should have access)
        data = {
            "user_signup_info": {
                "username": "newprouser_creator",
                "password": "newpass",
                "email": "newprouser_creator@example.com",
                "first_name": "New",
                "last_name": "User",
                "domain_name": "newdomain",
                "visible_phone_number": "1234567891",
                "continue_url": "http://example.com/continue",
            },
            "make_new_domain": False,
        }
        response = self.client.post(professional_create_url, data, format="json")
        self.assertIn(response.status_code, range(200, 300))
        # Create the initial patient user in same domainm (should have access)
        create_patient_url = reverse("create_patient_user-list")
        initial_patient_data = {
            "username": "newuserp1",
            "password": "newpass",
            "email": "newuser1289p1@example.com",
            "provider_phone_number": "1234567890",
            "country": "USA",
            "state": "CA",
            "city": "Test City",
            "address1": "123 Test St",
            "address2": "",
            "zipcode": "12345",
            "domain_name": "testdomain",
        }
        response = self.client.post(create_patient_url, initial_patient_data, format="json")
        self.assertIn(response.status_code, range(200, 300))
        # Create a second patient user in the same domain (should not have access)
        second_patient_data = {
            "username": "newuserp2",
            "password": "newpass",
            "email": "newuser1289p2@example.com",
            "provider_phone_number": "1234567890",
            "country": "USA",
            "state": "CA",
            "city": "Test City",
            "address1": "123 Test St",
            "address2": "",
            "zipcode": "12345",
            "domain_name": "testdomain",
        }
        response = self.client.post(create_patient_url, second_patient_data, format="json")
        self.assertIn(response.status_code, range(200, 300))
        self.primary_patient_user = User.objects.get(username="newuserp1")
        self.secondary_patient_user = User.objects.get(username="newuserp2")
        self.professional_user = User.objects.get(username="newprouser_creator")
        # Create the appeal manually
        self.appeal = Appeal.objects.create(
            appeal_text="This is a test appeal.",
            combined_document_enc=SimpleUploadedFile("farts.pdf", b"Test PDF content"),
            patient_user=self.primary_patient_user,
            primary_professional=self.professional_user,
        )

    def test_appeal_file_view_unauthenticated(self):
        response = self.client.get(
            reverse("appeal_file_view", kwargs={"appeal_uuid": self.appeal.uuid})
        )
        self.assertEqual(response.status_code, 401)

    def test_appeal_file_view_authenticated(self):
        # Check for self
        self.client.login(username="newuserp1", password="newpass")
        response = self.client.get(
            reverse("appeal_file_view", kwargs={"appeal_uuid": self.appeal.uuid})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        # Check for provider
        self.client.login(username="newprouser_creator", password="newpass")
        response = self.client.get(
            reverse("appeal_file_view", kwargs={"appeal_uuid": self.appeal.uuid})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        # Check for the domain admin
        self.client.login(username="newprouser_domain_admin", password="newpass")
        response = self.client.get(
            reverse("appeal_file_view", kwargs={"appeal_uuid": self.appeal.uuid})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_appeal_file_view_authenticated_incorrect(self):
        # Check for different patient
        self.client.login(username="newuserp2", password="newpass")
        response = self.client.get(
            reverse("appeal_file_view", kwargs={"appeal_uuid": self.appeal.uuid})
        )
        self.assertEqual(response.status_code, 404)
        # For different non-domain admin provider
        self.client.login(username="newprouser_unrelated", password="newpass")
        response = self.client.get(
            reverse("appeal_file_view", kwargs={"appeal_uuid": self.appeal.uuid})
        )
