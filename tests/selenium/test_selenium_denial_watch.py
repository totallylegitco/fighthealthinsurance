"""Denial Watch's view buttons, run in a browser.

The sync tests read the script's source; these check that switching a view
changes what a reader sees, and that the map buttons wrap on a phone.
"""

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from seleniumbase import BaseCase

from .fhi_selenium_base import FHISeleniumBase

BaseCase.main(__name__, __file__)


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

    def test_out_of_network_view_changes_the_readout_and_the_chart_label(self):
        self._open()
        self.click('#dmode button[data-m="out"]')
        self.assert_text_eventually_contains("of out-of-network claims denied in 2024", "dread")
        self.assertIn("Not mapped by state", self.get_text("#dread"))
        self.click('#tmode button[data-m="out"]')
        self.assertIn(
            "out-of-network denial rate by year, 2022 to 2024",
            self.get_attribute("#tline", "aria-label"),
        )

    def test_out_of_network_map_outlines_reporting_states_and_greys_the_rest(self):
        self._open()
        self.click('#dmode button[data-m="out"]')
        gone = self.execute_script(
            "return ['OH','CA'].map(s=>document.querySelector('#dmap g[data-s=\"'+s+'\"]').classList.contains('dw-gone'));"
        )
        # Ohio reports to HealthCare.gov but isn't mapped; California has no data here.
        self.assertEqual(gone, [True, False])

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
