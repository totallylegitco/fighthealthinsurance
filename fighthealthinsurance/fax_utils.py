import requests
import telnyx
import re
from typing import Optional
import os

FROM_FAX = os.getenv("FROM_FAX", "4158407591")
FROM_VOICE = os.getenv("FROM_VOICE", "2029383266")

class FaxSenderBase(object):
    base_cost = 0
    cost_per_page = 0

    def estimate_cost(self, pages: int) -> int:
        return self.base_cost + self.cost_per_page * pages

    def send_fax(
        self, destination: str, path: str, dest_name: Optional[str] = None
    ) -> bool:
        pass


class SonicFax(FaxSenderBase):
    base_cost = 0
    cost_per_page = 0
    csrf_regex = re.compile(r"\"csrfKey\" value=\"(.*?)\"")

    def __init__(self):
        self.username = os.getenv("SONIC_USERNAME")
        self.password = os.getenv("SONIC_PASSWORD")
        self.token = os.getenv("SONIC_TOKEN")
        self.notification_email = os.getenv(
            "SONIC_NOTIFICATION_EMAIL", "support42@fighthealthinsurance.com"
        )

    def send_fax(
        self, destination: str, path: str, dest_name: Optional[str] = None
    ) -> bool:
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9",
        }
        with requests.Session() as s:
            cookies = {"mt2FAToken": self.token}
            r = s.get("https://members.sonic.net/", headers=headers, cookies=cookies)
            r = s.post(
                "https://members.sonic.net/",
                data={"login": "login", "user": self.username, "pw": self.password},
                headers=headers,
                cookies=cookies,
            )
            r = s.get(
                "https://members.sonic.net/labs/fax", headers=headers, cookies=cookies
            )
            r.raise_for_status()
            csrf_matched = self.csrf_regex.search(r.text)
            if csrf_matched is None:
                raise Exception(f"No CSRF found in {r.text}")
            csrf_key = csrf_matched.group(1)
            print(f"Got csrf {csrf_key}")
            head, tail = os.path.split(path)
            r = s.post(
                "https://members.sonic.net/labs/fax/?a=upload",
                files={"filename": (tail, open(path, "rb"))}
            )
            r.raise_for_status
            r = s.post(
                "https://members.sonic.net/labs/fax/",
                data={
                    "destination": destination,
                    "a": "sendFax",
                    "csrfKey": csrf_key,
                    "coverTo": dest_name or destination or "HealthCo",
                    "coverFrom": "Fight Health Insurance",
                    "MAX_FILE_SIZE": "52428800",
                    "email": self.notification_email,
                    "fromVoice": FROM_VOICE,
                    "fromFax": FROM_FAX,
                    "message": "Fight Health Insurance",
                    "includeCover": "1",
                },
            )
            print(r)
            r.raise_for_status
            return (tail in r.text and destination in r.text)
