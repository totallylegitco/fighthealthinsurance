import asyncio
import io
from asgiref.sync import async_to_sync
from unittest.mock import patch, Mock
from typing import AsyncIterator
import pytest
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

        # Test helper: Async generator yielding items with delay.
        async def async_generator(items) -> AsyncIterator[str]:
            for item in items:
                await asyncio.sleep(0.1)
                yield item

        async def test():
            # Mocking appeal generation with an async generator
            mock_appeal_generator.generate_appeals.return_value = async_generator(
                ["test appeal data"]
            )
            
            # Running the backend helper that processes the appeals
            response = await AppealsBackendHelper.generate_appeals(
                {
                    "denial_id": 1,
                    "email": email,
                    "semi_sekret": denial.semi_sekret,
                }
            )
            
            # Create a StringIO buffer to capture the response
            buf = io.StringIO()

            # Write each chunk from the async generator to the StringIO
            async for chunk in response:
                buf.write(chunk)

            # Go back to the beginning of the StringIO to read the value
            buf.seek(0)
            string_data = buf.getvalue()

            # Assert that the string data matches the expected output
            self.assertEqual(string_data, "test appeal data")

        # Convert the async test function to run synchronously
        async_to_sync(test)()

