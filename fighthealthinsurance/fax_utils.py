import requests
import re
from typing import Optional
import os
import time

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
        return True


class SonicFax(FaxSenderBase):
    base_cost = 0
    cost_per_page = 0
    csrf_regex = re.compile(r"\"csrfKey\" value=\"(.*?)\"")
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en-US,en;q=0.9",
    }

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
        with requests.Session() as s:
            cookies = self._login(s)
            self._send_fax_non_blocking(
                s=s,
                cookies=cookies,
                destination=destination,
                path=path,
                dest_name=dest_name,
            )
            return self._blocking_check_fax_status(
                s=s,
                cookies=cookies,
                destination=destination,
                path=path,
                dest_name=dest_name,
            )

    def _login(self, s):
        cookies = {"mt2FAToken": self.token}
        r = s.get("https://members.sonic.net/", headers=self.headers, cookies=cookies)
        r = s.post(
            "https://members.sonic.net/",
            data={"login": "login", "user": self.username, "pw": self.password},
            headers=self.headers,
            cookies=cookies,
        )
        if "Member Login" in r.text:
            raise Exception(f"Error logging into sonic got back {r.text}")
        return cookies

    def blocking_check_fax_status(
        self, destination: str, path: str, dest_name: Optional[str] = None
    ) -> bool:
        with requests.Session() as s:
            cookies = self._login(s)
            return self._blocking_check_fax_status(
                s, cookies, destination, path, dest_name
            )

    def _blocking_check_fax_status(
        self, s, cookies, destination: str, path: str, dest_name: Optional[str] = None
    ) -> bool:
        r = s.get(
            "https://members.sonic.net/labs/fax/?a=history",
            headers=self.headers,
            cookies=cookies,
        )
        filename = self._get_filename(path)
        c = 0
        max_initial_count = 5
        max_final_count = 25
        # Polling check for the filename
        while c < max_initial_count:
            r = s.get(
                "https://members.sonic.net/labs/fax/?a=history",
                headers=self.headers,
                cookies=cookies,
            )
            c = c + 1
            time.sleep(c)
            if filename in r.text:
                break
        if filename not in r.text:
            return False
        c = 0
        chunk = None
        while c < max_final_count:
            c = c + 1
            time.sleep(c)
            r = s.get(
                "https://members.sonic.net/labs/fax/?a=history",
                headers=self.headers,
                cookies=cookies,
            )
            chunks = r.text.split("tr>")
            for chunk in chunks:
                if filename in chunk and destination in chunk:
                    if ">failed<" in chunk:
                        print(f"Failed :( {chunk}")
                        return False
                    elif ">success<" in chunk:
                        print(f"Success: {chunk}")
                        return True
        print(f"Timed out! last chunk {cunk}")
        return False

    def send_fax_non_blocking(self, destination, path, dest_name: Optional[str] = None):
        with requests.Session() as s:
            cookies = self._login(s)
            return self._send_fax_non_blocking(s, cookies, destination, path, dest_name)

    def _get_filename(self, path: str) -> str:
        head, tail = os.path.split(path)
        return tail

    def _send_fax_non_blocking(
        self, s, cookies, destination: str, path: str, dest_name: Optional[str] = None
    ):
        r = s.get(
            "https://members.sonic.net/labs/fax", headers=self.headers, cookies=cookies
        )
        r.raise_for_status()
        csrf_matched = self.csrf_regex.search(r.text)
        if csrf_matched is None:
            raise Exception(f"No CSRF found in {r.text}")
        csrf_key = csrf_matched.group(1)
        filename = self._get_filename(path)
        r = s.post(
            "https://members.sonic.net/labs/fax/?a=upload",
            files={"filename": (filename, open(path, "rb"))},
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


class HylaFaxClient(FaxSenderBase):
    base_cost = 0
    cost_per_page = 0
    host = None
    proxy = None

    def send_fax(
        self, destination: str, path: str, dest_name: Optional[str] = None
    ) -> bool:
        # Going above 9600 causes issues sometimes
        command = f"sendfax -n -d '{phonenumber}' -B 9600 -o {self.user} -h {self.host} {destination}"
