import asyncio
import json
import io
import uuid
from asgiref.sync import async_to_sync
from unittest.mock import Mock, patch
from typing import AsyncIterator
from fighthealthinsurance.common_view_logic import (
    RemoveDataHelper,
    SendFaxHelper,
    FindNextStepsHelper,
    DenialCreatorHelper,
    AppealsBackendHelper,
    DenialResponseInfo,
    NextStepInfo
)
from fighthealthinsurance.utils import as_valid_semi_sekret
from fighthealthinsurance.models import Denial, DenialTypes, FaxesToSend
import pytest
from django.test import TestCase, Client


class TestCommonViewLogic(TestCase):
    fixtures = ["fighthealthinsurance/fixtures/initial.yaml"]

    @pytest.mark.django_db
    @patch("fighthealthinsurance.common_view_logic.Denial.objects")
    def test_remove_data_for_email(self, mock_denial_objects):
        mock_denial = Mock()
        mock_denial_objects.filter.return_value.delete.return_value = 1
        RemoveDataHelper.remove_data_for_email("test@example.com")
        mock_denial_objects.filter.assert_called()
        mock_denial_objects.filter.return_value.delete.assert_called()

    @pytest.mark.django_db
    @patch("fighthealthinsurance.common_view_logic.Denial.objects")
    def test_find_next_steps(self, mock_denial_objects):
        denial = Denial.objects.create(
            denial_id=1,
            semi_sekret="sekret",
            hashed_email=Denial.get_hashed_email("test@example.com"),
        )
        denial.denial_type.all.return_value = [
            DenialTypes.objects.get(name="Insurance Company"),
            DenialTypes.objects.get(name="Medically Necessary"),
        ]
        next_steps = FindNextStepsHelper.find_next_steps(
            denial_id=1,
            email="test@example.com",
            semi_sekret=denial.semi_sekret,
            procedure="prep",
            plan_id="1",
            denial_type=None,
            denial_date=None,
            diagnosis="high risk homosexual behvaiour",
            insurance_company="evilco",
            claim_id=7,
        )
        self.assertIsInstance(next_steps, NextStepInfo)

    @pytest.mark.django_db
    @patch("fighthealthinsurance.common_view_logic.appealGenerator")
    def test_generate_appeals(self, mock_appeal_generator):
        email = "test@example.com"
        denial = Denial.objects.create(
            denial_id=1,
            semi_sekret="sekret",
            hashed_email=Denial.get_hashed_email(email),
        )

        async def async_generator(items) -> AsyncIterator[str]:
            """Test helper: Async generator yielding items with delay."""
            for item in items:
                await asyncio.sleep(0.1)
                yield item

        async def test():
            mock_appeal_generator.generate_appeals.return_value = async_generator(
                ["test"]
            )
            responses = AppealsBackendHelper.generate_appeals(
                {
                    "denial_id": 1,
                    "email": email,
                    "semi_sekret": denial.semi_sekret,
                }
            )
            buf = io.StringIO()

            async for chunk in responses:
                buf.write(chunk)

            buf.seek(0)
            string_data = buf.getvalue()

        async_to_sync(test)()

    @pytest.mark.django_db
    def test_as_valid_semi_sekret(self):
        # Test valid UUID format
        valid_uuid = str(uuid.uuid4())
        self.assertTrue(as_valid_semi_sekret(valid_uuid))
        
        # Test invalid formats
        self.assertFalse(as_valid_semi_sekret(None))
        self.assertFalse(as_valid_semi_sekret(123))
        self.assertFalse(as_valid_semi_sekret(""))
        self.assertFalse(as_valid_semi_sekret("not-a-uuid"))
        self.assertFalse(as_valid_semi_sekret("12345678-1234-1234-1234-1234567890ab-extra"))
        self.assertFalse(as_valid_semi_sekret("12345678-1234-1234-1234-1234567890"))
        
        # Test with invalid characters
        self.assertFalse(as_valid_semi_sekret("12345678-1234-1234-1234-1234567890zz"))
        
        # Test with uppercase (if your implementation is case-sensitive)
        uppercase_uuid = str(uuid.uuid4()).upper()
        self.assertFalse(as_valid_semi_sekret(uppercase_uuid))

    @pytest.mark.django_db
    def test_generated_semi_sekret_passes_validation(self):
        """Test that our method of generating semi_sekrets passes validation."""
        # This assumes you generate semi_sekrets using uuid.uuid4()
        for _ in range(100):  # Test multiple generations
            generated_uuid = str(uuid.uuid4())
            self.assertTrue(as_valid_semi_sekret(generated_uuid), 
                           f"Generated UUID {generated_uuid} failed validation")
