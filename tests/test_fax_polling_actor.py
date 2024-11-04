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
        """Test that the fax polling actor starts."""

        # Create a delayed fax that should be sent
        delayed_time = timezone.now() - timedelta(hours=4)
        fax = FaxesToSend.objects.create(
            hashed_email="test_hash",
            email="test@example.com",
            destination="1234567890",
            should_send=True,
            sent=False,
            paid=False,
        )
        # Start the actor running
        self.fax_polling_actor.run.remote()

        # Give it some time to process
        import time

        time.sleep(4)

        self.assertEqual(1, ray.get(self.fax_polling_actor.count.remote()))
