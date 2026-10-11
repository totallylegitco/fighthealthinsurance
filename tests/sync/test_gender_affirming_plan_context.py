"""The gender-affirming-care plan context: WPATH and the HRC, read right.

GenderAffirmingCareQuestions.plan_context tells the appeal which WPATH
Standards of Care version the person's plan documents cite, and whether
their employer told the Human Rights Campaign it covers transgender care.
None of it reached an appeal:

* The appeal generator called the hook inline from async code, where its
  plan-document query raised SynchronousOnlyOperation, logged at DEBUG and
  dropped -- with the CA regulation and HRC text built before it.
* It read the unencrypted file field, empty for every upload (uploads are
  stored encrypted), so it never saw a plan document.
* It returned after the first document, and its open-ended regex could
  backtrack for minutes over a long one.

These live in tests/sync/ because TransactionTestCase can't run under the
async suite's xdist workers (see tests/sync/test_ml_plan_doc_helper.py).
"""

import asyncio
import time
from unittest.mock import MagicMock, patch

import pymupdf
from django.core.exceptions import SynchronousOnlyOperation
from django.core.files.base import ContentFile
from django.test import SimpleTestCase, TransactionTestCase

from fighthealthinsurance.common_view_logic import form_plan_context
from fighthealthinsurance.forms.questions import (
    HRC_TIMEOUT_SECONDS,
    GenderAffirmingCareBreastAugmentationQuestions,
    GenderAffirmingCareQuestions,
    wpath_version_in,
)
from fighthealthinsurance.models import Denial, PlanDocuments


def _pdf_bytes(text: str) -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), text)
    data: bytes = doc.tobytes()
    doc.close()
    return data


class WpathVersionInTest(SimpleTestCase):
    def test_the_standards_of_care_version(self):
        self.assertEqual(
            wpath_version_in(["The plan follows WPATH Standards of Care, Version 7."]),
            "7",
        )

    def test_the_full_title_of_the_standards(self):
        text = (
            "World Professional Association for Transgender Health (WPATH) "
            "Standards of Care for the Health of Transsexual, Transgender, and "
            "Gender Nonconforming People, Version 7"
        )
        self.assertEqual(wpath_version_in([text]), "7")

    def test_the_short_form(self):
        self.assertEqual(wpath_version_in(["Criteria follow WPATH SOC-8."]), "8")

    def test_a_version_named_before_the_mention(self):
        self.assertEqual(wpath_version_in(["Per SOC 8 (WPATH, 2022), ..."]), "8")

    def test_the_title_broken_across_lines(self):
        text = "per the WPATH Standards of\nCare, Version 8 guidelines"
        self.assertEqual(wpath_version_in([text]), "8")

    def test_a_mention_without_a_version(self):
        self.assertEqual(wpath_version_in(["Criteria follow WPATH guidance."]), "")

    def test_no_mention(self):
        self.assertIsNone(wpath_version_in(["Dental coverage only."]))

    def test_no_documents(self):
        self.assertIsNone(wpath_version_in([]))

    def test_a_later_document_is_read_too(self):
        # The first upload is often the summary of benefits, not the policy.
        self.assertEqual(
            wpath_version_in(["Summary of benefits.", "WPATH SOC-8 applies."]), "8"
        )

    def test_a_version_in_a_later_document_beats_a_bare_mention(self):
        self.assertEqual(
            wpath_version_in(["See WPATH.", "WPATH Standards of Care Version 8"]),
            "8",
        )

    def test_a_long_document_without_a_version_is_read_quickly(self):
        # The regex this replaces, WPATH.*?Standards of.*?Care.*?Version.*?(\d+)
        # under DOTALL, tried every Care after every Standards of after the
        # mention before failing: polynomial in the document's length.
        text = "WPATH " + "Standards of Care " * 3000
        started = time.monotonic()
        self.assertEqual(wpath_version_in([text]), "")
        self.assertLess(time.monotonic() - started, 2)


class HrcLookupTest(SimpleTestCase):
    def test_every_request_has_a_timeout(self):
        # It runs on the appeal's critical path; requests waits forever
        # without one.
        response = MagicMock(text='<a href="https://www.hrc.org/resources/buyers-guide/acme">Acme</a>')
        with patch(
            "fighthealthinsurance.forms.questions.requests.get", return_value=response
        ) as get:
            GenderAffirmingCareQuestions().employer_hrc_lookup("Acme")
        self.assertTrue(get.call_args_list)
        for call in get.call_args_list:
            self.assertEqual(call.kwargs.get("timeout"), HRC_TIMEOUT_SECONDS)


class GenderAffirmingPlanContextTest(TransactionTestCase):
    def _denial_with(self, *documents, employer_name=None) -> Denial:
        denial = Denial.objects.create(
            hashed_email=Denial.get_hashed_email("gac@example.com"),
            denial_text="Denied: gender affirming surgery.",
            employer_name=employer_name,
        )
        for name, body in documents:
            doc = PlanDocuments(denial=denial)
            doc.plan_document_enc.save(name, ContentFile(body), save=True)
        return denial

    def test_the_version_is_read_from_an_encrypted_plan_document(self):
        denial = self._denial_with(
            ("plan.pdf", _pdf_bytes("This plan follows WPATH SOC-8 criteria."))
        )
        version = asyncio.run(GenderAffirmingCareQuestions().wpath_version(denial))
        self.assertEqual(version, "8")

    def test_every_uploaded_document_is_read(self):
        denial = self._denial_with(
            ("benefits.txt", b"Summary of benefits and coverage."),
            ("policy.txt", b"Surgery criteria follow WPATH SOC-8."),
        )
        version = asyncio.run(GenderAffirmingCareQuestions().wpath_version(denial))
        self.assertEqual(version, "8")

    def test_the_plan_context_cites_the_plans_version(self):
        denial = self._denial_with(("policy.txt", b"Criteria follow WPATH SOC-8."))
        context = asyncio.run(
            form_plan_context(GenderAffirmingCareQuestions().plan_context, denial)
        )
        self.assertIn("WPATH8 standards of care", context)

    def test_breast_augmentation_gets_the_version_7_requirements(self):
        denial = self._denial_with(
            ("policy.txt", b"Criteria follow the WPATH Standards of Care, Version 7.")
        )
        context = asyncio.run(
            form_plan_context(
                GenderAffirmingCareBreastAugmentationQuestions().plan_context, denial
            )
        )
        self.assertIn("The plan references version 7 of the WPATH SOC", context)

    def test_the_employers_hrc_pledge_is_cited(self):
        denial = self._denial_with(employer_name="Acme")
        with patch.object(
            GenderAffirmingCareQuestions, "employer_hrc_lookup", return_value=True
        ):
            context = asyncio.run(
                form_plan_context(GenderAffirmingCareQuestions().plan_context, denial)
            )
        self.assertIn("Human Rights Campaign", context)


class FormPlanContextTest(TransactionTestCase):
    """form_plan_context: how the appeal generator calls a form's hook."""

    def _denial(self) -> Denial:
        return Denial.objects.create(
            hashed_email=Denial.get_hashed_email("hook@example.com"),
            denial_text="Denied.",
        )

    @staticmethod
    def _counts_plan_documents(denial):
        """A sync hook that reads the database, as plan_context hooks do."""
        return f"{PlanDocuments.objects.filter(denial=denial).count()} documents"

    def test_called_inline_from_async_code_a_sync_hook_cannot_read(self):
        # What the appeal generator used to do.
        denial = self._denial()

        async def inline():
            return self._counts_plan_documents(denial)

        with self.assertRaises(SynchronousOnlyOperation):
            asyncio.run(inline())

    def test_a_sync_hook_runs_off_the_event_loop(self):
        denial = self._denial()
        self.assertEqual(
            asyncio.run(form_plan_context(self._counts_plan_documents, denial)),
            "0 documents",
        )

    def test_an_async_hook_is_awaited(self):
        denial = self._denial()

        async def hook(d):
            return f"denial {d.denial_id}"

        self.assertEqual(
            asyncio.run(form_plan_context(hook, denial)),
            f"denial {denial.denial_id}",
        )
