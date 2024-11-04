import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import ray
from django.test import TestCase
from django.utils import timezone

from fighthealthinsurance.fax_polling_actor import FaxPollingActor
from fighthealthinsurance.models import Denial, FaxesToSend


@pytest.mark.django_db
class TestFaxPollingActor(TestCase):
    fixtures = ["fighthealthinsurance/fixtures/initial.yaml"]

    def setUp(self):
        # Initialize Ray for testing
        if not ray.is_initialized():
            ray.init(namespace="fhi", ignore_reinit_error=True)
        self.fax_polling_actor = FaxPollingActor.remote()

    def tearDown(self):
        # Clean up Ray
        if ray.is_initialized():
            ray.shutdown()

    def test_init(self):
        """Test that the actor initializes correctly."""
        result = ray.get(self.fax_polling_actor.hi.remote())
        self.assertEqual(result, "ok")

    def test_send_delayed_faxes_success(self):
        """Test successful sending of delayed faxes."""
        # Create a test denial
        denial = Denial.objects.create(
            hashed_email="test_hash",
            email="test@example.com",
            denial_text="Test denial",
            use_external=False,
        )

        # Create a delayed fax that should be sent
        delayed_time = timezone.now() - timedelta(hours=5)
        fax = FaxesToSend.objects.create(
            hashed_email="test_hash",
            email="test@example.com",
            denial_id=denial,
            destination="1234567890",
            should_send=True,
            sent=False,
            date=delayed_time,
        )

        # Mock the fax actor's send_fax method to return success
        with patch(
            "fighthealthinsurance.fax_actor.FaxActor.do_send_fax_object"
        ) as mock_send:
            mock_send.return_value = True
            # Call the method and verify results
            result = ray.get(self.fax_polling_actor.send_delayed_faxes.remote())
            self.assertTrue(result)
            mock_send.assert_called_once()

    def test_send_delayed_faxes_no_delayed_faxes(self):
        """Test behavior when there are no delayed faxes to send."""
        # Create a recent fax that should not be sent yet
        denial = Denial.objects.create(
            hashed_email="test_hash",
            email="test@example.com",
            denial_text="Test denial",
            use_external=False,
        )

        recent_time = timezone.now() - timedelta(hours=1)
        fax = FaxesToSend.objects.create(
            hashed_email="test_hash",
            email="test@example.com",
            denial_id=denial,
            destination="1234567890",
            should_send=True,
            sent=False,
            date=recent_time,
        )

        # Mock the fax actor's send_fax method
        with patch(
            "fighthealthinsurance.fax_actor.FaxActor.do_send_fax_object"
        ) as mock_send:
            # Call the method and verify results
            result = ray.get(self.fax_polling_actor.send_delayed_faxes.remote())
            self.assertTrue(result)
            mock_send.assert_not_called()

    def test_send_delayed_faxes_error_handling(self):
        """Test error handling when sending faxes fails."""
        # Create a test denial
        denial = Denial.objects.create(
            hashed_email="test_hash",
            email="test@example.com",
            denial_text="Test denial",
            use_external=False,
        )

        # Create multiple delayed faxes
        delayed_time = timezone.now() - timedelta(hours=5)
        fax1 = FaxesToSend.objects.create(
            hashed_email="test_hash1",
            email="test1@example.com",
            denial_id=denial,
            destination="1234567890",
            should_send=True,
            sent=False,
            date=delayed_time,
        )

        fax2 = FaxesToSend.objects.create(
            hashed_email="test_hash2",
            email="test2@example.com",
            denial_id=denial,
            destination="0987654321",
            should_send=True,
            sent=False,
            date=delayed_time,
        )

        # Mock the fax actor's send_fax method to raise an exception
        with patch(
            "fighthealthinsurance.fax_actor.FaxActor.do_send_fax_object"
        ) as mock_send:
            mock_send.side_effect = Exception("Fax sending failed")
            # Call the method and verify results
            result = ray.get(self.fax_polling_actor.send_delayed_faxes.remote())
            self.assertTrue(result)  # Should still return True even with errors
            self.assertEqual(mock_send.call_count, 2)  # Should attempt both faxes

    def test_run_method_handles_errors(self):
        """Test that the run method properly handles errors and continues running."""
        with patch(
            "fighthealthinsurance.fax_actor.FaxActor.send_delayed_faxes"
        ) as mock_send:
            mock_send.side_effect = [Exception("Test error"), True]

            # Start the actor running
            self.fax_polling_actor.run.remote()

            # Give it some time to process
            import time

            time.sleep(2)

            # Verify it called the method and handled the error
            mock_send.assert_called()
