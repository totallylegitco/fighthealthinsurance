"""The send page hands the person their letter exactly as it was written.

The draft box on appeal.html sat on an indented line inside its textarea, so
every letter arrived with four spaces in front and a line break and two
spaces after, and appeal.ts copied them into the finished letter that is
printed and faxed. The page now puts the letter in the box as it is, and the
script trims what is around a letter before it builds the finished one.

The page is rendered by the real view and read the way a browser reads a
textarea. The script is the real TypeScript, compiled with the repo's own
tsc (the same flags as test_letter_placeholders.py) and loaded in node over
tests/js/fake_page.cjs through tests/js/appeal_send_page_behaviour.cjs.
Skipped, not silently passed, where node or the front-end toolchain is not
installed; the checks against the rendered page need neither.
"""

import json
import os
import pathlib
import re
import subprocess

import pytest
from bs4 import BeautifulSoup
from django.test import Client, TestCase
from django.urls import reverse

from fighthealthinsurance.models import Denial
from tests.sync.test_entity_fetcher_behaviour import NODE, TSC, needs_node

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
JS = REPO_ROOT / "fighthealthinsurance" / "static" / "js"
DRIVER = REPO_ROOT / "tests" / "js" / "appeal_send_page_behaviour.cjs"

EMAIL = "patient@example.com"
# Made up, like every person and plan here.
LETTER = (
    "Dear Example Health,\n\n"
    "I am writing to appeal the denial of my MRI.\n\n"
    "Sincerely,\n"
    "Rebecca Lee Crumpler"
)


def textarea_value(textarea) -> str:
    """A textarea's value as a browser has it: the one line break straight
    after the opening tag is not part of it."""
    text = textarea.string or ""
    return text[1:] if text.startswith("\n") else text


class SendPageRendersTheLetterAsItIsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.denial = Denial.objects.create(
            denial_text="denied",
            semi_sekret="the-case-secret",
            hashed_email=Denial.get_hashed_email(EMAIL),
            insurance_company="Example Health",
            appeal_fax_number="15550000000",
        )

    def render(self, appeal_text: str = LETTER) -> BeautifulSoup:
        response = self.client.post(
            reverse("choose_appeal"),
            {
                "denial_id": self.denial.denial_id,
                "email": EMAIL,
                "semi_sekret": self.denial.semi_sekret,
                "appeal_text": appeal_text,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "appeal.html")
        return BeautifulSoup(response.content.decode(), "html.parser")

    def test_the_draft_box_holds_the_letter_and_nothing_around_it(self):
        draft = self.render().find("textarea", id="scrubbed_appeal_text")
        self.assertEqual(textarea_value(draft), LETTER)

    def test_markup_in_a_letter_stays_text_in_the_box(self):
        letter = "Dear Example Health, </textarea><b>not markup</b> & more."
        draft = self.render(letter).find("textarea", id="scrubbed_appeal_text")
        self.assertEqual(textarea_value(draft), letter)

    def test_the_fake_page_has_the_real_ids(self):
        """appeal_send_page_behaviour.cjs mirrors this page by id, so a
        rename cannot leave it testing a page that no longer exists."""
        page = self.render()
        fixture = DRIVER.read_text()
        ids = re.findall(r'id="([^"]+)"', fixture.split("const MARKUP = `")[1].split("`;")[0])
        own = {"share-form", "pii-panel", "fax-form"}
        missing = [i for i in ids if i not in own and page.find(id=i) is None]
        self.assertEqual(missing, [])


@pytest.fixture(scope="module")
def compiled(tmp_path_factory) -> pathlib.Path:
    """The real appeal.ts and what it imports, compiled the way the bundle
    is built. The shared JSON sits outside static/js, so the output keeps the
    layout from fighthealthinsurance/ down."""
    out = tmp_path_factory.mktemp("appeal-send-page")
    result = subprocess.run(
        [
            NODE,
            str(TSC),
            "--target",
            "es5",
            "--module",
            "commonjs",
            "--moduleResolution",
            "node",
            "--lib",
            "dom,dom.iterable,esnext",
            "--strict",
            "--esModuleInterop",
            "--allowSyntheticDefaultImports",
            "--forceConsistentCasingInFileNames",
            "--skipLibCheck",
            "--resolveJsonModule",
            "--outDir",
            str(out),
            str(JS / "appeal.ts"),
        ],
        cwd=str(JS),
        capture_output=True,
        text=True,
        timeout=300,
    )
    built = out / "static" / "js" / "appeal.js"
    if not built.exists():
        pytest.fail(
            f"tsc did not emit appeal.js\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    assert result.returncode == 0, result.stdout + result.stderr
    return out


def run_scenario(compiled: pathlib.Path, name: str, **given) -> dict:
    result = subprocess.run(
        [NODE, str(DRIVER), str(compiled), name],
        cwd=str(REPO_ROOT),
        input=json.dumps(given),
        capture_output=True,
        text=True,
        timeout=120,
        env=dict(os.environ, NODE_ENV="test"),
    )
    if result.returncode != 0:
        pytest.fail(
            f"scenario {name} crashed\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return json.loads(result.stdout)


# What an older page put in the draft box, as the browser read it out.
INDENTED = "    " + LETTER + "\n  "


@needs_node
def test_the_finished_letter_starts_at_its_first_word(compiled):
    page = run_scenario(compiled, "load", draft=INDENTED)
    assert page["letter"] == LETTER


@needs_node
def test_the_finished_letter_stays_trimmed_as_the_draft_is_edited(compiled):
    page = run_scenario(
        compiled, "type-in-draft", draft=LETTER, typed="\n\n  " + LETTER + " Thank you.\n\n"
    )
    assert page["letter"] == LETTER + " Thank you."


@needs_node
def test_the_details_block_still_follows_a_trimmed_letter(compiled):
    page = run_scenario(
        compiled, "load", draft=INDENTED, stored={"store_fname": "Rebecca", "store_lname": "Crumpler"}
    )
    assert page["letter"] == LETTER + "\n\n---\nPatient Information:\nName: Rebecca Crumpler"
