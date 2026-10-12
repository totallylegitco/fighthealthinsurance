"""The route the encrypted file fields reverse for a file's .url."""

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django_encrypted_filefield.checks import fetch_url_check
from django_encrypted_filefield.constants import FETCH_URL_NAME

from fighthealthinsurance.models import PlanDocuments


class EncryptedFileUrlTest(TestCase):
    def test_the_name_the_library_reads_still_reverses(self):
        url = reverse(FETCH_URL_NAME, kwargs={"path": "plans/rebecca-lee-crumpler.pdf"})
        self.assertEqual(url, "/timbit/no-file/plans/rebecca-lee-crumpler.pdf")

    def test_the_reversed_url_answers_404(self):
        url = reverse("fake_fetch_url", kwargs={"path": "plans/notes.pdf"})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_an_encrypted_files_url_answers_404(self):
        document = PlanDocuments(plan_document_enc="plans/notes.pdf")
        url = document.plan_document_enc.url
        self.assertTrue(url.startswith("/timbit/no-file/"), url)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_the_old_test_route_is_gone(self):
        for url in ("/timbit/sentry-debug/", "/timbit/sentry-debug/x"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_the_librarys_own_check_passes(self):
        self.assertEqual(fetch_url_check(None), [])

    def test_the_system_check_passes(self):
        call_command("check")
