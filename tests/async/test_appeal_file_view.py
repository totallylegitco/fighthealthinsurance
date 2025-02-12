from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from fighthealthinsurance.models import Appeal
from fhi_users.models import PatientUser, ProfessionalUser
from django.core.files.uploadedfile import SimpleUploadedFile


class AppealFileViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        # Create the initial provider user (should have acccess) + implicitly the domain

        # Create a second provider user in same domain (should not have access)

        # Create a third provider user in same domain and admin (should have access)

        # Create the initial patient user in same domainm (should have access)

        # Create a second patient user in the same domain (should not have access)

        # Create the appeal
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
        self.client.login(username="testuser", password="12345")
        response = self.client.get(
            reverse("appeal_file_view", kwargs={"appeal_uuid": self.appeal.uuid})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        # Check for provider
        self.client.login(username="alt_alt_testuser", password="12345")
        response = self.client.get(
            reverse("appeal_file_view", kwargs={"appeal_uuid": self.appeal.uuid})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_appeal_file_view_authenticated_incorrect(self):
        self.client.login(username="alt_testuser", password="12345")
        response = self.client.get(
            reverse("appeal_file_view", kwargs={"appeal_uuid": self.appeal.uuid})
        )
        self.assertEqual(response.status_code, 404)
