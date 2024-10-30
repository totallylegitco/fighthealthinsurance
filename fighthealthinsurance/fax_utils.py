import tempfile
import requests
import re
from typing import Optional
import os
import time
import subprocess
from PyPDF2 import PdfFileReader, PdfFileWriter


FROM_FAX = os.getenv("FROM_FAX", "4158407591")
FROM_VOICE = os.getenv("FROM_VOICE", "2029383266")


class FaxSenderBase(object):
    base_cost = 0
    cost_per_page = 0
    # Avoid calling 211/etc.
    special_naps = re.compile(r"^1?(\d11|\d\d\d\d11)")

    def estimate_cost(self, destination: str, pages: int) -> int:
        return self.base_cost + self.cost_per_page * pages

    def parse_phone_number(self, input: str) -> str:
        """Parse a phone number, raise exception if it's a \"bad\" one."""
        numbers = re.findall(r"\d+", input)
        number_str = "".join(map(str, numbers))
        # Add 1 in front of any phone number we call
        if number_str[0] != "1":
            number_str = f"1{number_str}"
        if number_str.startswith("1900"):
            raise Exception("No calling 1900 numbers")
        if number_str.startswith("1911"):
            raise Exception("No trying to call 911 this is for faxes.")
        if number_str.startswith("10"):
            raise Exception("No trying to call the operator")
        if self.special_naps.match(number_str):
            raise Exception("No calling special svc numbers")
        return number_str

    def send_fax(
        self,
        destination: str,
        path: str,
        dest_name: Optional[str] = None,
        blocking: bool = False,
    ):
        if blocking:
            self.send_fax_blocking(
                destination=destination, path=path, dest_name=dest_name
            )
        else:
            self.send_fax_nonblocking(
                destination=destination, path=path, dest_name=dest_name
            )

    def send_fax_blocking(
        self, destination: str, path: str, dest_name: Optional[str] = None
    ) -> bool:
        pass
        return True

    def send_fax_nonblocking(
        self, destination: str, path: str, dest_name: Optional[str] = None
    ) -> bool:
        pass
        return True


class SonicFax(FaxSenderBase):
    base_cost = 0
    cost_per_page = 2
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

    def send_fax_blocking(
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
        print(f"Timed out! last chunk {chunk}")
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
    host: Optional[str] = None
    max_speed = 9600

    def send_fax_blocking(
        self, destination: str, path: str, dest_name: Optional[str] = None
    ) -> bool:
        return self._send_fax(
            destination=destination, path=path, dest_name=dest_name, blocking=True
        )

    def send_fax_nonblocking(
        self, destination: str, path: str, dest_name: Optional[str] = None
    ) -> bool:
        return self._send_fax(
            destination=destination, path=path, dest_name=dest_name, blocking=False
        )

    def _send_fax(
        self,
        destination: str,
        path: str,
        dest_name: Optional[str] = None,
        blocking: bool = False,
    ) -> bool:
        if self.host is None:
            raise Exception("Can not send fax without a host to fax from")
        # Going above 9600 causes issues sometimes
        with tempfile.NamedTemporaryFile(
            suffix=".txt", prefix="meeps", mode="w+t", delete=True
        ) as f:
            f.write(destination)
            f.flush()
            os.sync()
            time.sleep(1)
            destination_file = f.name
            command = ["sendfax"]
            if blocking:
                command.append("-w")
            command.extend(
                [
                    "-n",
                    f"-B{self.max_speed}",
                    f"-h{self.host}",
                    path,
                    f"-z{destination_file}",  # It is important this is last
                ]
            )
            print(f"Sending command {command}")
            result = subprocess.run(command)
            print(result.stdout)  # Output of the command
            print(result.stderr)  # Error output (if any)
            print(result.returncode)  # Exit code of the command
            return result.returncode == 0


class FaxyMcFaxFace(HylaFaxClient):
    base_cost = 0
    cost_per_page = 1
    host = os.getenv("FAXYMCFAXFACE_HOST")
    max_speed = 9600


class FlexibleFaxMagic(object):
    """Fax interface that routes to different backends and chops pages etc."""

    def __init__(self, backends: list[FaxSenderBase], max_pages=10):
        self.backends = backends
        self.max_pages = max_pages

    def assemble_outputs(self, user_header: str, input_paths: list[str]) -> list[str]:
        """Assemble the outputs into chunks of max_pages length"""
        # Keep track of the total pages
        total_input_pages = 0
        # Start with converting everything into pdf & counting the pages
        for input_path in input_paths:
            command = ["pandoc", input_path, f"-o{input_path}.pdf"]
            result = subprocess.run(command)
            reader = PdfFileReader(f"{input_path}.pdf")
            total_input_pages += len(reader.pages)
        # How many chunks do we need to make
        number_of_transmissions = 1 + int(total_input_pages / self.max_pages)
        results: list[str] = []
        # Iterate through making the chunks
        input_index = 0
        current_input_file = PdfFileReader(f"{input_path[0]}.pdf")
        index_in_current_file = 0
        for i in range(1, number_of_transmissions):
            # Compute the number of pages in this transmission.
            x_pages = self.max_pages
            if i == number_of_transmissions:
                x_pages = total_input_pages % self.max_pages
            # Write out the header
            header_path = ""
            with tempfile.NamedTemporaryFile(
                suffix=".txt", prefix="meeps", mode="w+t", delete=False
            ) as f:
                header = f"""This part of transmission {user_header} which is transmission {i} of {number_of_transmissions} with {x_pages} in this transmission in addition to the cover page [this page]."""
                f.write(header)
                f.sync()
                command = ["pandoc", f.name, f"-o{f.name}.pdf"]
                subprocess.run(command)
                header_path = f"{f.name}.pdf"
            with tempfile.NamedTemporaryFile(
                suffix=".pdf", prefix="meeps", mode="w+t", delete=False
            ) as f:
                results.append(f.name)
                w = PdfFileWriter(f)
                header_reader = PdfFileReader(header_path)
                w.addPage(header_reader.pages[0])
                transmission_page_count = 0
                while transmission_page_count < self.max_pages:
                    if index_in_current_file < len(current_input_file.pages):
                        w.addPage(current_input_file.pages[index_in_current_file])
                        transmission_page_count += 1
                        index_in_current_file += 1
                    elif input_index < len(input_paths):
                        index_in_current_file = 0
                        input_index += 1
                        current_input_file = PdfFileReader(
                            f"{input_paths[input_index]}.pdf"
                        )
                    else:
                        break
        return results

    def send_fax(
        self, input_paths: list[str], destination: str, blocking: bool
    ) -> bool:
        import uuid

        myuuid = uuid.uuid4()
        myuuidStr = str(myuuid)
        transmission_files = self.assemble_outputs(myuuidStr, input_paths)
        for transmission in transmission_files:
            r = self._send_fax(
                path=transmission, destination=destination, blocking=blocking
            )
            if r is False:
                return r
        return True

    def _send_fax(self, path: str, destination: str, blocking: bool) -> bool:
        backend = self.backends[0]
        page_count = len(PdfFileReader(path).pages)
        backend_cost = backend.estimate_cost(destination, page_count)
        for candidate in self.backends[1:]:
            candidate_cost = candidate.estimate_cost(destination, page_count)
            if backend_cost > candidate_cost:
                backend = candidate
                backend_cost = candidate_cost
        return backend.send_fax(destination=destination, path=path, blocking=blocking)


flexible_fax_magic = FlexibleFaxMagic([SonicFax(), FaxyMcFaxFace()])
