from asgiref.sync import async_to_sync
from unittest.mock import Mock, patch, MagicMock
from typing import AsyncIterator
import pytest
import json
import tempfile
import os
from datetime import datetime
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.base import ContentFile
from django.core.files import File

from fighthealthinsurance.common_view_logic import (
    RemoveDataHelper,
    SendFaxHelper,
    FindNextStepsHelper,
    DenialCreatorHelper,
    AppealsBackendHelper,
    DenialResponseInfo,
    NextStepInfo,
    AppealAssemblyHelper,
)
from fighthealthinsurance.models import (
    Denial,
    DenialTypes,
    FaxesToSend,
    Appeal,
    PatientUser,
    ProfessionalUser,
    UserDomain,
)
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from io import BytesIO

User = get_user_model()


class TestCommonViewLogic(TestCase):
    fixtures = ["fighthealthinsurance/fixtures/initial.yaml"]

    @pytest.mark.django_db
    @patch("fighthealthinsurance.common_view_logic.Denial.objects")
    def test_remove_data_for_email(self, mock_denial_objects):
        mock_denial = Mock()
        mock_denial_objects.filter.return_value.delete.return_value = 1
        RemoveDataHelper.remove_data_for_email("test@example.com")
        mock_denial_objects.filter.assert_called_once()

    @pytest.mark.django_db
    def test_find_next_steps(self):
        # Create a real Denial instance
        denial = Denial.objects.create(
            denial_text="Test denial text",
            hashed_email=Denial.get_hashed_email("test@example.com"),
            qa_context=json.dumps({}),  # Empty but valid JSON
            semi_sekret="secret",
        )

        # Call the method under test - the real database object will be used
        result = FindNextStepsHelper.find_next_steps(
            denial_id=str(denial.denial_id),
            email="test@example.com",
            procedure="test procedure",
            diagnosis="test diagnosis",
            insurance_company="test insurance",
            plan_id="12345",
            claim_id="67890",
            denial_type=[],
            semi_sekret="secret",
        )

        # Verify we got a proper result
        self.assertIsInstance(result, NextStepInfo)

        # Refresh the denial object to verify updates
        denial.refresh_from_db()
        self.assertEqual(denial.procedure, "test procedure")
        self.assertEqual(denial.diagnosis, "test diagnosis")
        self.assertEqual(denial.insurance_company, "test insurance")

    @pytest.mark.django_db
    def test_generate_appeals(self):
        # Skip testing async functionality in unittest
        # This is better tested in an integration test
        pass

    @pytest.mark.django_db
    def test_create_or_update_appeal_new(self):
        """Test creating a new appeal"""
        helper = AppealAssemblyHelper()

        # Create an actual denial object
        denial = Denial.objects.create(
            denial_text="Test denial text",
            hashed_email=Denial.get_hashed_email("test@example.com"),
            claim_id="12345",
            semi_sekret="secret",
        )

        # Mock the _assemble_appeal_pdf method to create a real PDF file
        with patch.object(helper, "_assemble_appeal_pdf") as mock_assemble:
            # Set up the mock to create a real file when called
            def side_effect(*args, **kwargs):
                # Write some dummy content to the target file
                target_file = kwargs.get("target")
                with open(target_file, "wb") as f:
                    f.write(b"Test PDF content")
                return target_file

            mock_assemble.side_effect = side_effect

            # Test creating a new appeal
            appeal = helper.create_or_update_appeal(
                fax_phone="123-456-7890",
                completed_appeal_text="This is a new appeal text",
                company_name="Test Company",
                email="test@example.com",
                include_provided_health_history=False,
                name="Test Patient",
                denial=denial,
            )

            # Verify the appeal was created properly
            self.assertIsNotNone(appeal)
            self.assertEqual(appeal.appeal_text, "This is a new appeal text")
            self.assertEqual(appeal.for_denial, denial)
            self.assertEqual(appeal.hashed_email, denial.hashed_email)

            # Verify the mock was called correctly
            mock_assemble.assert_called_once()

    @pytest.mark.django_db
    def test_create_or_update_appeal_existing(self):
        """Test updating an existing appeal"""
        helper = AppealAssemblyHelper()

        # Create an actual denial object
        denial = Denial.objects.create(
            denial_text="Test denial text",
            hashed_email=Denial.get_hashed_email("test@example.com"),
            claim_id="12345",
            semi_sekret="secret",
        )

        # Create an actual appeal in the database
        existing_appeal = Appeal.objects.create(
            appeal_text="Original appeal text",
            for_denial=denial,
            hashed_email=denial.hashed_email,
        )

        # Mock the _assemble_appeal_pdf method to create a real PDF file
        with patch.object(helper, "_assemble_appeal_pdf") as mock_assemble:
            # Set up the mock to create a real file when called
            def side_effect(*args, **kwargs):
                # Write some dummy content to the target file
                target_file = kwargs.get("target")
                with open(target_file, "wb") as f:
                    f.write(b"Test PDF content")
                return target_file

            mock_assemble.side_effect = side_effect

            # Test updating the existing appeal
            updated_appeal = helper.create_or_update_appeal(
                appeal=existing_appeal,
                fax_phone="123-456-7890",
                completed_appeal_text="This is updated appeal text",
                company_name="Test Company",
                email="test@example.com",
                include_provided_health_history=False,
                name="Test Patient",
                denial=denial,
            )

            # Get the latest data from database
            existing_appeal.refresh_from_db()

            # Verify the appeal was updated correctly
            self.assertEqual(updated_appeal.id, existing_appeal.id)
            self.assertEqual(updated_appeal.appeal_text, "This is updated appeal text")
            self.assertEqual(updated_appeal.for_denial, denial)

            # Verify the mock was called correctly
            mock_assemble.assert_called_once()

    async def _collect_async_results(self, async_iterator: AsyncIterator) -> list:
        """Helper method to collect results from an async iterator"""
        results = []
        async for item in async_iterator:
            results.append(item)
        return results
