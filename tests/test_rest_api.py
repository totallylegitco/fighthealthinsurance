"""Test the rest API functionality"""

import hashlib
import os
import time
import sys

from rest_framework import status
from rest_framework.test import APITestCase

from fighthealthinsurance.models import *

class Delete(APITestCase):
    def test_url_root(self):
        url = reverse('rest:api_delete')
        email = "timbit@fighthealthinsurance.com"
        hashed_email = hashlib.sha512(email.encode("utf-8")).hexdigest()
        # Create the object
        Denial.objects.create(
            denial_text="test",
            hashed_email=hashed_email).save()
        denials_for_user_count = Denial.objects.filter(
            hashed_email=hashed_email
        ).count()
        assert denials_for_user_count > 1
        # Delete it
        response = self.client.delete(url, {'email': email})
        self.assertTrue(status.is_success(response.status_code))
        # Make sure we did that
        denials_for_user_count = Denial.objects.filter(
            hashed_email=hashed_email
        ).count()
        assert denials_for_user_count > 0

