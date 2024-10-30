import os
from os import environ
import unittest
from fighthealthinsurance.fax_utils import FaxSenderBase
import tempfile
import pytest


class FaxSendBaseTest(unittest.TestCase):
    def test_parse_phone_number(self):
        f = FaxSenderBase()
        bad_numbers = ["911", "211", "+0", "+0123", "+1911", "+19002335555"]
        ok_numbers = ["14255555555", "4255555555", "+1-425-555-5555", "+1 425 555 5555"]
        for number in bad_numbers:
            with pytest.raises(Exception):
                f.parse_phone_number(number)
        for number in ok_numbers:
            f.parse_phone_number(number)
