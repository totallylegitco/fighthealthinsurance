"""Denial Watch's view buttons, run in a browser.

The sync tests read the script's source; these check that switching a view
changes what a reader sees, and that the map buttons wrap on a phone.
"""

import json
import pathlib

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from seleniumbase import BaseCase

from .fhi_selenium_base import FHISeleniumBase

BaseCase.main(__name__, __file__)

DATA = json.loads(
    (pathlib.Path(__file__).resolve().parents[2] / "fighthealthinsurance" / "static" / "denial_watch.json").read_text()
)


class SeleniumTestDenialWatchViews(FHISeleniumBase, StaticLiveServerTestCase):
    """The map and trend buttons on /denial-watch."""

    @classmethod
    def setUpClass(cls):
        super(StaticLiveServerTestCase, cls).setUpClass()
        super(BaseCase, cls).setUpClass()

    @classmethod
    def tearDownClass(cls):
        super(StaticLiveServerTestCase, cls).tearDownClass()
        super(BaseCase, cls).tearDownClass()

    def _open(self, width=1280, height=900):
        self.set_window_size(width, height)
        self.open(f"{self.live_server_url}{reverse('denial-watch')}")
        self.wait_for_page_ready(predicate=lambda d: d.execute_script("return !!document.querySelector('#dmap g')"))

    def test_out_of_network_view_is_on_the_trend_chart_only(self):
        self._open()
        self.assertEqual(self.execute_script("return document.querySelectorAll('#dmode button[data-m=\"out\"]').length"), 0)
        self.click('#tmode button[data-m="out"]')
        self.assert_text_eventually_contains("about twice the in-network rate", "tnote")
        self.assertIn(
            "out-of-network denial rate by year, 2022 to 2024",
            self.get_attribute("#tline", "aria-label"),
        )
        self.assertTrue(self.execute_script("return !!document.querySelector('#tnote a[href=\"#who-to-call\"]')"))

    def test_all_claims_map_outlines_left_out_states_and_greys_the_rest(self):
        self._open()
        self.click('#dmode button[data-m="all"]')
        gone = self.execute_script(
            "return ['AK','ND','OH','CA'].map(s=>document.querySelector('#dmap g[data-s=\"'+s+'\"]').classList.contains('dw-gone'));"
        )
        # Alaska and North Dakota report but have no all-claims figure; Ohio has one; California has no data here.
        self.assertEqual(gone, [True, True, False, False])

    def _rows(self):
        return self.execute_script("return [...document.querySelectorAll('#itable tbody tr')].map(r => r.cells[0].textContent)")

    def test_picking_a_state_on_the_map_lists_its_insurers(self):
        texas = sorted(i["n"] for i in DATA["issuers"] if i["s"] == "TX")
        self._open()
        self.assert_text_eventually_contains("in Florida", "icount")
        self.click('#dmap g[data-s="TX"]')
        self.assert_text_eventually_contains("in Texas", "icount")
        self.assertEqual(self.get_value("#istate"), "TX")
        self.assertEqual(sorted(self._rows()), texas)
        # Hovering another state previews it without moving the table.
        self.hover('#dmap g[data-s="OH"]')
        self.assert_text_eventually_contains("Ohio", "dread")
        self.assertEqual(sorted(self._rows()), texas)

    def test_picking_a_state_with_no_insurers_says_so(self):
        self._open()
        self.click('#dmap g[data-s="CA"]')
        self.assert_text_eventually_contains("California isn't in this data", "itable")
        self.assertEqual(self.get_value("#istate"), "")

    def test_map_buttons_wrap_on_a_phone(self):
        self._open(375, 812)
        sizes = self.execute_script(
            """
            var box = document.getElementById('dmode').getBoundingClientRect();
            var out = [...document.querySelectorAll('#dmode button')].filter(
                b => b.getBoundingClientRect().right > box.right + 1).length;
            var wrap = document.querySelector('#insurers .dw-table-wrap');
            return [document.documentElement.scrollWidth, window.innerWidth, out,
                    getComputedStyle(wrap).overflowX];
            """
        )
        page, window, buttons_out, table_overflow = sizes
        self.assertLessEqual(page, window + 1, "the page scrolls sideways on a phone")
        self.assertEqual(buttons_out, 0, "a map button runs past its row")
        # A table wider than the phone scrolls inside its own box, as elsewhere on the site.
        self.assertIn(table_overflow, ("auto", "scroll"))
