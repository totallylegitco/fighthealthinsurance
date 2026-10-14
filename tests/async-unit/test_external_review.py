from unittest.mock import patch

from django.test import SimpleTestCase

from fighthealthinsurance.external_review import get_state_config
from fighthealthinsurance.state_help import StateHelp

# Minimal state_help-style entry for a state without a hand-verified
# external-review config (used to test the DOI contact fallback).
OREGON_STATE_HELP = {
    "slug": "oregon",
    "name": "Oregon",
    "abbreviation": "OR",
    "insurance_department": {
        "name": "Oregon Division of Financial Regulation",
        "url": "https://dfr.oregon.gov/",
        "phone": "503-378-4140",
        "consumer_line": "888-877-4894",
        "complaint_url": "https://dfr.oregon.gov/help/complaints-licenses/Pages/file-a-complaint.aspx",
    },
    "consumer_assistance": {},
    "medicaid": {},
    "external_review": {
        "available": True,
        "info_url": "https://dfr.oregon.gov/insurance-help/Pages/external-review.aspx",
    },
}


class StateConfigTests(SimpleTestCase):
    def test_missing_state_falls_back(self):
        cfg = get_state_config(None)
        self.assertEqual(cfg["state"], "FEDERAL")

    def test_new_seed_state_configured(self):
        cfg = get_state_config("WA")
        self.assertEqual(cfg["state"], "WA")
        self.assertIn("Washington Office of the", cfg["regulator_name"])

    def test_unconfigured_state_uses_state_doi_contact(self):
        """States without a hand-verified entry should point at their own
        insurance regulator (name + consumer phone line) from state_help
        instead of only the federal fallback number."""
        with patch(
            "fighthealthinsurance.external_review.get_state_help_by_abbreviation",
            return_value=StateHelp(OREGON_STATE_HELP),
        ):
            cfg = get_state_config("OR")
        self.assertEqual(cfg["state"], "OR")
        self.assertTrue(cfg["not_configured"])
        self.assertEqual(
            cfg["regulator_name"], "Oregon Division of Financial Regulation"
        )
        self.assertEqual(cfg["phone"], "888-877-4894")
        self.assertEqual(
            cfg["external_review_url"],
            "https://dfr.oregon.gov/insurance-help/Pages/external-review.aspx",
        )
        self.assertIn("file-a-complaint", cfg["form_url"])

    def test_unconfigured_state_without_state_help_keeps_federal_contact(self):
        with patch(
            "fighthealthinsurance.external_review.get_state_help_by_abbreviation",
            return_value=None,
        ):
            cfg = get_state_config("ZZ")
        self.assertEqual(cfg["state"], "ZZ")
        self.assertEqual(cfg["regulator_name"], "CMS / Federal External Review")
        self.assertEqual(cfg["phone"], "1-877-267-2323")

    def test_configured_state_keeps_hand_verified_contact(self):
        """Hand-verified entries must win over the generic DOI enrichment."""
        cfg = get_state_config("CA")
        self.assertEqual(
            cfg["regulator_name"], "California Department of Managed Health Care"
        )
        self.assertEqual(cfg["phone"], "1-888-466-2219")
