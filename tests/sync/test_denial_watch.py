"""Tests for the Denial Watch public-data page.

The page is staged behind DENIAL_WATCH_PAGE_ENABLED (on in Dev/Test, off in
production until launch). Its numbers come from static/denial_watch.json, and
some of them are also written into the page's sentences, so these tests check
that the copy still agrees with the data after a refresh.
"""

import importlib.util
import json
import pathlib
import re

from django.test import Client, TestCase, override_settings
from django.urls import reverse

REPO = pathlib.Path(__file__).resolve().parents[2]
DATA = json.loads(
    (REPO / "fighthealthinsurance" / "static" / "denial_watch.json").read_text()
)


def _load_builder():
    path = REPO / "scripts" / "denial_watch" / "build_bundle.py"
    spec = importlib.util.spec_from_file_location("denial_watch_build", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _millions(x: float) -> str:
    return f"{x / 1e6:.1f} million"


def _without_data(html: str) -> str:
    """The page as a reader sees it, without the embedded JSON."""
    return re.sub(r'<script id="dw-data".*?</script>', "", html, flags=re.S)


class TestDenialWatchPage(TestCase):
    """The page renders with its data embedded."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        response = Client().get(reverse("denial-watch"))
        cls.status_code = response.status_code
        cls.content = response.content.decode()

    def test_page_renders(self):
        self.assertEqual(self.status_code, 200)

    def test_data_is_embedded_for_the_script(self):
        self.assertIn('id="dw-data"', self.content)
        self.assertIn("js/denial_watch.js", self.content)

    def test_page_links_to_starting_an_appeal(self):
        self.assertIn(reverse("scan"), self.content)

    def test_counter_is_labeled_as_an_illustration(self):
        # Reviewers flagged a running count as reading like a live feed.
        self.assertIn("An illustration, not a live count", self.content)
        # Screen readers hear the group's label first.
        self.assertNotIn("Estimated denials today", self.content)

    def test_appeal_deadlines_match_the_glossary(self):
        # Medicare Advantage is 60 days from receipt, presumed 5 days after the notice.
        self.assertIn("Medicare Advantage gives 65 days from the date on the notice", self.content)
        self.assertIn("Medicaid plans give 60", self.content)

    def test_page_names_its_sources(self):
        # Checked outside the embedded JSON, which carries every URL anyway.
        visible = _without_data(self.content)
        for source in DATA["sources"]:
            self.assertIn(f'href="{source["url"]}"', visible)

    def test_page_sits_on_the_wide_column_without_its_own_stylesheet(self):
        self.assertIn('class="fhi-page-wide dw"', self.content)
        self.assertNotIn("denial_watch.css", self.content)


class TestDenialWatchCopyMatchesData(TestCase):
    """Numbers written into sentences must match the JSON they came from."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.content = Client().get(reverse("denial-watch")).content.decode()

    def test_state_range_headline(self):
        rates = [s["rate"] for s in DATA["states"].values()]
        self.assertIn(
            # "about": the lowest state (South Dakota, 6.55%) rounds to 7% on the
            # map legend but shows as 6.5% in its tooltip.
            f"Denial rates run from about {_pct(min(rates))} to {_pct(max(rates))}",
            self.content,
        )

    def test_california_review_rates(self):
        by_year = {r["y"]: r["r"] for r in DATA["imr_trend"]}
        self.assertIn(f"overturned {_pct(by_year[2025])} of the denials", self.content)
        self.assertIn(f"up from {_pct(by_year[2017])} in 2017", self.content)

    def test_appeal_win_rate_is_not_compared_with_2023(self):
        # The insurers reporting changed between years, so it isn't like for like.
        prev = next(t for t in DATA["trend"] if t["year"] == 2023)
        self.assertIn(
            "In 2024 insurers reversed about a third of the internal appeals people filed.",
            self.content,
        )
        self.assertNotIn(_pct(prev["overturned"] / prev["appeals"]), self.content)

    def test_share_of_denials_appealed_in_the_steps(self):
        latest = DATA["trend"][-1]
        ratio = latest["in_denied"] / latest["appeals_all"]
        self.assertIn(
            f"about 1 appeal for every {round(ratio, -1):.0f} in-network denials",
            self.content,
        )

    def test_headline_counts_in_network_claims(self):
        # One basis for the headline: in-network, as KFF and the map count.
        latest = DATA["trend"][-1]
        self.assertEqual(round(1 / latest["in_rate"]), 5)
        self.assertIn(
            "about one in five in-network claims in 2024, "
            f"{_millions(latest['in_denied'])} in all",
            self.content,
        )

    def test_method_note_gives_both_counting_bases(self):
        latest = DATA["trend"][-1]
        ratio = latest["in_denied"] / latest["appeals_all"]
        self.assertIn(
            f"{_millions(latest['in_denied'])} denials in 2024, "
            f"{_pct(latest['in_rate'])} of in-network claims, and "
            f"{latest['appeals_all']:,.0f} internal appeals, "
            f"about 1 for every {round(ratio, -1):.0f} of those denials",
            self.content,
        )
        self.assertIn(
            f"({latest['denied'] / 1e6:.0f} million denials, "
            f"{_pct(latest['rate'])}, in 2024)",
            self.content,
        )

    def test_trend_text_names_the_all_claims_figures(self):
        latest = DATA["trend"][-1]
        self.assertIn(
            f"puts 2024 at {latest['denied'] / 1e6:.0f} million denials and "
            f"{_pct(latest['rate'])}, a little above the in-network "
            f"{_pct(latest['in_rate'])}",
            self.content,
        )

    def test_trend_years_without_an_in_network_split(self):
        # Why the trend chart counts all claims.
        split = {t["year"]: "in_denied" in t for t in DATA["trend"]}
        self.assertFalse(split[2020] or split[2021])

    def test_denial_share_in_the_trend_starts_at_2020_and_names_the_peak(self):
        by_year = {t["year"]: t["rate"] for t in DATA["trend"]}
        peak = max(by_year, key=lambda y: by_year[y])
        self.assertIn(
            f"went from {_pct(by_year[2020])} in 2020 to about "
            f"{_pct(by_year[max(by_year)])}, after peaking at "
            f"{_pct(by_year[peak])} in {peak}",
            self.content,
        )

    def test_not_medically_necessary_share_of_reasons(self):
        total = sum(r["v"] for r in DATA["reasons"])
        parts = [r["v"] for r in DATA["reasons"] if "medically necessary" in r["k"]]
        self.assertEqual(len(parts), 2)
        self.assertIn(
            f"is {sum(parts) / total:.1%} of all reasons "
            f"({sum(parts) / 1e6:.1f} million of {total / 1e6:.1f} million)",
            self.content,
        )

    def test_california_rate_in_the_steps(self):
        by_year = {r["y"]: r["r"] for r in DATA["imr_trend"]}
        self.assertIn(f"in {_pct(by_year[2025])} of the cases they decided in 2025", self.content)

    def test_correlations(self):
        corr = DATA["corr"]
        self.assertIn(f"correlation {corr['fair_poor_health']:.2f}", self.content)
        self.assertIn(f"diabetes ({corr['diabetes']:.2f})", self.content)


class TestDenialWatchStaging(TestCase):
    """The staging flag controls both routing and discoverability."""

    @override_settings(DENIAL_WATCH_PAGE_ENABLED=False)
    def test_page_serves_404_when_disabled(self):
        response = Client().get(reverse("denial-watch"))
        self.assertEqual(response.status_code, 404)

    @override_settings(DENIAL_WATCH_PAGE_ENABLED=False)
    def test_options_does_not_reveal_the_route_when_disabled(self):
        response = Client().options(reverse("denial-watch"))
        self.assertEqual(response.status_code, 404)

    @override_settings(DENIAL_WATCH_PAGE_ENABLED=True)
    def test_page_is_in_the_static_sitemap_when_enabled(self):
        from fighthealthinsurance.sitemap import StaticViewSitemap

        self.assertIn("denial-watch", StaticViewSitemap().items())

    @override_settings(DENIAL_WATCH_PAGE_ENABLED=False)
    def test_page_is_hidden_from_the_sitemap_when_disabled(self):
        from fighthealthinsurance.sitemap import StaticViewSitemap

        self.assertNotIn("denial-watch", StaticViewSitemap().items())


class TestDenialWatchData(TestCase):
    """The shipped JSON keeps the rules the build promises."""

    def test_rates_are_proportions(self):
        for state, s in DATA["states"].items():
            self.assertTrue(0 < s["rate"] < 1, state)
            if s["won"] is not None:
                self.assertTrue(0 <= s["won"] <= 1, state)
                self.assertGreaterEqual(s["appeals"], 50, state)

    def test_insurer_rows_meet_the_thresholds(self):
        for row in DATA["issuers"]:
            self.assertGreaterEqual(row["c"], 50_000, row["n"])
            if row["a"] is not None:
                self.assertGreaterEqual(row["a"], 30, row["n"])
                if row["o"] is not None:
                    self.assertLessEqual(row["o"], row["a"], row["n"])
            else:
                self.assertIsNone(row["o"], row["n"])

    def test_reasons_leave_out_the_out_of_network_column(self):
        # CMS defines it as closed-network denials; KFF leaves it out too.
        self.assertNotIn("Out of network", [r["k"] for r in DATA["reasons"]])
        self.assertEqual(
            DATA["reason_meta"]["entries"], sum(r["v"] for r in DATA["reasons"])
        )

    def test_no_2020_drug_total(self):
        # The 2024 file lists only drugs still dispensed in 2024.
        self.assertEqual(set(DATA["drugs"]["total"]), {"y2024"})

    def test_trend_is_in_year_order_with_leap_years(self):
        years = [t["year"] for t in DATA["trend"]]
        self.assertEqual(years, sorted(years))
        for t in DATA["trend"]:
            self.assertEqual(t["days"], 366 if t["year"] % 4 == 0 else 365)

    def test_win_rates_use_matched_counts(self):
        for t in DATA["trend"]:
            self.assertLessEqual(t["appeals"], t["appeals_all"])
            self.assertLessEqual(t["overturned"], t["appeals"])


class TestDenialWatchBuilder(TestCase):
    """Pure helpers in scripts/denial_watch/build_bundle.py (no pandas needed)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.b = _load_builder()

    def test_suppressed_cells_are_missing_not_zero(self):
        for cell in ("*", "**", "***", "N/A", None, ""):
            self.assertIsNone(self.b.num(cell))
        self.assertEqual(self.b.num("1,234"), 1234.0)
        self.assertEqual(self.b.num(7), 7.0)
        self.assertIsNone(self.b.num(True))

    def test_matched_appeals_skip_issuers_missing_either_count(self):
        issuers = [
            dict(ap_filed=100.0, ap_over=40.0),
            dict(ap_filed=50.0, ap_over=None),  # overturned count suppressed
            dict(ap_filed=None, ap_over=5.0),
        ]
        self.assertEqual(self.b.matched_appeals(issuers), (100.0, 40.0))

    def test_all_claims_falls_back_to_in_plus_out(self):
        issuer = dict(
            rec_all=None,
            den_all=None,
            rec_in=90.0,
            rec_out=10.0,
            den_in=9.0,
            den_out=5.0,
        )
        self.assertEqual(self.b.all_claims(issuer), (100.0, 14.0))
        issuer["den_out"] = None
        self.assertIsNone(self.b.all_claims(issuer))

    def test_state_win_rate_needs_enough_appeals(self):
        base = dict(state="XX", rec_in=1000.0, den_in=100.0)
        few = self.b.state_rates([dict(base, ap_filed=10.0, ap_over=5.0)])
        self.assertIsNone(few["XX"]["won"])
        many = self.b.state_rates([dict(base, ap_filed=60.0, ap_over=30.0)])
        self.assertEqual(many["XX"]["won"], 0.5)
        self.assertEqual(many["XX"]["rate"], 0.1)


class TestDenialWatchPriorAuth(TestCase):
    """Prior-authorization rows are copied as posted, each with its source."""

    def test_every_row_links_its_source(self):
        rows = DATA["prior_auth"]
        self.assertGreater(len(rows), 0)
        for r in rows:
            self.assertTrue(r["url"].startswith("https://"), r["n"])
            self.assertIn(r["line"], {"ma", "mcd", "mkt", "ffs"}, r["n"])
            if r["std"] is not None:
                self.assertTrue(0 <= r["std"] <= 1, r["n"])

    def test_every_row_says_what_it_counts(self):
        for r in DATA["prior_auth"]:
            self.assertIn(r["unit"], {"requests", "procedure codes"}, r["n"])

    def test_source_links_are_https_only(self):
        # The page refuses any other scheme too; this keeps the data honest.
        for r in DATA["prior_auth"]:
            self.assertRegex(r["url"], r"^https://[^\s\"<>]+$", r["n"])

    def test_builder_reads_the_curated_file(self):
        rows = _load_builder().build_prior_auth()
        self.assertEqual(rows, DATA["prior_auth"])


class TestDenialWatchIsEasyToFind(TestCase):
    """Once the page is live it is one click from everywhere; before, nowhere."""

    def _pages(self):
        return {
            name: Client().get(reverse(name)).content.decode()
            for name in ("root", "explain_denial", "about")
        }

    @override_settings(DENIAL_WATCH_PAGE_ENABLED=True)
    def test_every_page_links_to_it_when_live(self):
        link = f'href="{reverse("denial-watch")}"'
        for name, html in self._pages().items():
            self.assertIn(link, html, f"{name} has no link to Denial Watch")

    @override_settings(DENIAL_WATCH_PAGE_ENABLED=True)
    def test_each_place_links_to_it_when_live(self):
        # One check per place, so the footer can't stand in for the others.
        href = reverse("denial-watch")
        about = Client().get(reverse("about")).content.decode()
        home = Client().get(reverse("root")).content.decode()
        explain = Client().get(reverse("explain_denial")).content.decode()
        self.assertIn(f'<a href="{href}" class="fhi-nav-link" id="denialwatchlink">', about)
        self.assertIn(f'<a href="{href}">Denial Watch</a>', about)
        self.assertRegex(home, rf'(?s)id="denial-watch-home".*?href="{href}"')
        self.assertIn(f'<a href="{href}">See how often, on Denial Watch</a>', explain)

    @override_settings(DENIAL_WATCH_PAGE_ENABLED=True)
    def test_the_home_strip_states_the_latest_number(self):
        latest = DATA["trend"][-1]
        html = Client().get(reverse("root")).content.decode()
        self.assertIn(
            f"About 1 in {round(1 / latest['in_rate'])} in-network claims on "
            f"HealthCare.gov plans were denied in {latest['year']}",
            html,
        )

    @override_settings(DENIAL_WATCH_PAGE_ENABLED=False)
    def test_nothing_links_to_it_before_launch(self):
        link = f'href="{reverse("denial-watch")}"'
        for name, html in self._pages().items():
            self.assertNotIn(link, html, f"{name} links to an unlaunched page")
            self.assertNotIn("Denial Watch", html, name)


class TestDenialWatchScriptCountsInNetwork(TestCase):
    """The tests above never run the script, so read which fields it uses."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.js = (
            REPO / "fighthealthinsurance" / "static" / "js" / "denial_watch.js"
        ).read_text()

    def test_counter_spreads_in_network_denials(self):
        self.assertIn("const perDay=T.in_denied/T.days", self.js)

    def test_appeal_ratio_uses_in_network_denials(self):
        self.assertIn("apShare=T.appeals_all/T.in_denied", self.js)

    def test_win_rate_shows_the_latest_year_alone(self):
        # No tile or table column sets the win rate beside an earlier year's.
        self.assertIn("const T=D.trend[D.trend.length-1]", self.js)
        self.assertNotIn("down from", self.js)
        self.assertNotIn('<th class="dw-r">Won</th>', self.js)

    def test_insurer_table_says_when_cms_withheld_the_win_count(self):
        self.assertIn("not reported (", self.js)

    def test_counter_can_be_paused(self):
        self.assertIn("prefers-reduced-motion", self.js)
        self.assertIn('id="tickpause"', Client().get(reverse("denial-watch")).content.decode())
