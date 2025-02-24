from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from fighthealthinsurance.models import Appeal, AppealAttachment
from django.contrib.auth import get_user_model
from fighthealthinsurance.tests.factories import (
    UserFactory,
    AppealFactory,
    PatientUserFactory,
    ProfessionalUserFactory,
)


class AppealAttachmentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = UserFactory()
        self.patient = PatientUserFactory(user=self.user)
        self.professional = ProfessionalUserFactory()
        self.appeal = AppealFactory(patient_user=self.patient)
        self.client.force_authenticate(user=self.user)

        self.test_file = SimpleUploadedFile(
            "test.pdf", b"file_content", content_type="application/pdf"
        )

    def test_upload_attachment(self):
        response = self.client.post(
            "/api/appeal-attachments/",
            {"appeal_id": self.appeal.id, "file": self.test_file},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            AppealAttachment.objects.filter(
                appeal=self.appeal, filename="test.pdf"
            ).exists()
        )

    def test_list_attachments(self):
        attachment = AppealAttachment.objects.create(
            appeal=self.appeal,
            file=self.test_file,
            filename="test.pdf",
            mime_type="application/pdf",
        )

        response = self.client.get(
            f"/api/appeal-attachments/?appeal_id={self.appeal.id}"
        )
        self.assertEqual(response.status_code, 200)
        loaded = json.loads(response.content)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["filename"], "test.pdf")

    def test_delete_attachment(self):
        attachment = AppealAttachment.objects.create(
            appeal=self.appeal,
            file=self.test_file,
            filename="test.pdf",
            mime_type="application/pdf",
        )

        response = self.client.delete(f"/api/appeal-attachments/{attachment.id}/")
        self.assertEqual(response.status_code, 204)
        self.assertFalse(AppealAttachment.objects.filter(id=attachment.id).exists())

    def test_unauthorized_access(self):
        other_user = UserFactory()
        other_patient = PatientUserFactory(user=other_user)
        other_appeal = AppealFactory(patient_user=other_patient)

        attachment = AppealAttachment.objects.create(
            appeal=other_appeal,
            file=self.test_file,
            filename="test.pdf",
            mime_type="application/pdf",
        )

        response = self.client.get(f"/api/appeal-attachments/{attachment.id}/")
        self.assertEqual(response.status_code, 404)
