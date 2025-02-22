import asyncio
import io
from asgiref.sync import async_to_sync
from unittest.mock import patch, Mock
from typing import AsyncIterator
import pytest
from unittest import TestCase 
from fighthealthinsurance.models import Denial, DenialTypes
from fighthealthinsurance.common_view_logic import AppealsBackendHelper

class TestCommonViewLogic(TestCase):
    fixtures = ["fighthealthinsurance/fixtures/initial.yaml"]

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
            for item in items:
                await asyncio.sleep(0.1)
                yield item

        async def test():
            mock_appeal_generator.generate_appeals.return_value = async_generator(
                ["test appeal data"]
            )
            
            response = await AppealsBackendHelper.generate_appeals(
                {
                    "denial_id": 1,
                    "email": email,
                    "semi_sekret": denial.semi_sekret,
                }
            )
            
            buf = io.StringIO()

            async for chunk in response:
                buf.write(chunk)

            buf.seek(0)
            string_data = buf.getvalue()

            self.assertEqual(string_data, "test appeal data")

        async_to_sync(test)()

