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
