"""Tests for the Denial Watch public-data page.

The page is staged behind DENIAL_WATCH_PAGE_ENABLED (on in Dev/Test, off in
production until launch). Its numbers come from static/denial_watch.json, and
some of them are also written into the page's sentences, so these tests check
that the copy still agrees with the data after a refresh.
"""

import csv
import importlib.util
import json
import pathlib
import re
from datetime import date
from unittest import mock

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


def _between(html: str, start: str, end: str) -> str:
    """The part of the page from one marker up to the next, so a check stays in its section."""
    i = html.index(start)
    return html[i : html.index(end, i)]


def _page(day: date | None = None) -> str:
    """The rendered page, with today pinned when a day is given."""
    if day is None:
        return Client().get(reverse("denial-watch")).content.decode()
    with mock.patch("django.utils.timezone.localdate", return_value=day):
        return Client().get(reverse("denial-watch")).content.decode()


SHOWN_DRUGS = [r for tab in ("top", "per", "growth", "cheap") for r in DATA["drugs"][tab]]


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

    def test_method_note_explains_the_won_counts_left_out(self):
        self.assertIn("Nine insurers' 2024 appeals-won counts look like reporting errors", self.content)
        self.assertIn("With them, the 2024 rate would be 33.6%.", self.content)

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
            f"{_millions(latest['in_denied'])} among reporting insurers",
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

    def test_doubtful_won_counts_are_blanked_and_filed_kept(self):
        issuers = {k: dict(ap_filed=500.0, ap_over=0.0) for k in self.b.DOUBTFUL_WON[2026]}
        self.b.drop_doubtful_won(issuers, 2026)
        for row in issuers.values():
            self.assertEqual(row, dict(ap_filed=500.0, ap_over=None))

    def test_doubtful_won_list_is_only_for_its_plan_year(self):
        key = sorted(self.b.DOUBTFUL_WON[2026])[0]
        issuers = {key: dict(ap_filed=500.0, ap_over=0.0)}
        self.b.drop_doubtful_won(issuers, 2025)
        self.assertEqual(issuers[key]["ap_over"], 0.0)

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


class TestDenialWatchDrugUses(TestCase):
    """Each listed drug says what it's for, from a checked source."""

    def test_every_shown_drug_names_its_use(self):
        for tab in ("top", "per", "growth", "cheap"):
            for r in DATA["drugs"][tab]:
                self.assertTrue(1 <= len(r["use"].split()) <= 3, r["Brnd_Name"])

    def test_every_use_cites_medlineplus_or_the_fda_label(self):
        path = REPO / "scripts" / "denial_watch" / "drug_uses.csv"
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                self.assertRegex(
                    r["source_url"],
                    r"^https://(medlineplus\.gov|dailymed\.nlm\.nih\.gov|www\.accessdata\.fda\.gov)/",
                    r["brand"],
                )

    def test_builder_labels_from_the_curated_file(self):
        uses = _load_builder().load_drug_uses()
        for tab in ("top", "per", "growth", "cheap"):
            for r in DATA["drugs"][tab]:
                self.assertEqual(uses[r["Brnd_Name"]], r["use"])

    def test_builder_stops_on_an_unlabelled_drug(self):
        with self.assertRaises(SystemExit):
            _load_builder().attach_drug_uses({"top": [{"Brnd_Name": "Unlisted"}]}, {})


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

    def test_appeal_ratio_tile_rounds_to_tens_like_the_text(self):
        self.assertIn("fmt(Math.round(1/apShare/10)*10)", self.js)

    def test_win_rate_shows_the_latest_year_alone(self):
        # No tile or table column sets the win rate beside an earlier year's.
        self.assertIn("const T=D.trend[D.trend.length-1]", self.js)
        self.assertNotIn("down from", self.js)
        self.assertNotIn('<th class="dw-r">Won</th>', self.js)

    def test_all_states_view_ranks_no_company_across_states(self):
        # Rates are compared within a state, so the opening view is per state.
        self.assertIn('<option value="">All states</option>', self.js)
        self.assertIn("Insurer denial rates, lowest to highest", self.js)
        self.assertNotIn("highest and lowest 10", self.js)
        self.assertNotIn("slice(0,10)", self.js)

    def test_insurer_table_says_when_cms_withheld_the_win_count(self):
        self.assertIn("not reported (", self.js)

    def test_each_headline_number_has_a_label(self):
        for label in ("'claims denied'", "'denials per appeal'", "'appeals won'", "'reviews won'"):
            self.assertIn(label, self.js)

    def test_counter_says_what_it_counts(self):
        page = Client().get(reverse("denial-watch")).content.decode()
        self.assertIn("denied so far today, at 2024's pace", page)
        self.assertIn("denied per day in 2024, on average", page)

    def test_counter_can_be_paused(self):
        self.assertIn("prefers-reduced-motion", self.js)
        self.assertIn('id="tickpause"', Client().get(reverse("denial-watch")).content.decode())


class TestDenialWatchEnrollment(TestCase):
    """The open-enrollment box shows only in season; tests pin the date."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from fighthealthinsurance.views import denial_watch_enrollment

        cls.season = staticmethod(denial_watch_enrollment)

    def test_medicare_line_runs_october_15_to_december_7(self):
        self.assertEqual(self.season(date(2026, 10, 15)), {"medicare": True})
        self.assertEqual(self.season(date(2026, 12, 7)), {"medicare": True})

    def test_box_stays_for_healthcare_gov_after_medicare_closes(self):
        self.assertEqual(self.season(date(2026, 12, 8)), {"medicare": False})
        self.assertEqual(self.season(date(2027, 1, 15)), {"medicare": False})

    def test_box_is_hidden_out_of_season(self):
        self.assertIsNone(self.season(date(2026, 10, 14)))
        self.assertIsNone(self.season(date(2027, 1, 16)))

    def test_page_shows_the_box_in_season(self):
        html = _page(date(2026, 10, 18))
        box = _between(html, 'id="enroll"', "</section>")
        self.assertIn("Medicare open enrollment runs from October 15 to December 7, 2026", box)
        self.assertIn('href="https://www.medicare.gov/plan-compare/"', box)
        self.assertIn('href="https://www.healthcare.gov/"', box)
        self.assertIn('href="#insurers"', box)
        self.assertIn('href="#prior-auth"', box)

    def test_box_sits_near_the_top(self):
        html = _page(date(2026, 10, 18))
        self.assertLess(html.index('id="enroll"'), html.index('class="fhi-jump-links"'))

    def test_insurer_section_points_to_healthcare_gov_in_season(self):
        html = _page(date(2026, 10, 18))
        section = _between(html, 'id="insurers"', "</section>")
        self.assertIn("Picking a 2027 HealthCare.gov plan?", section)

    def test_box_prints_no_healthcare_gov_dates(self):
        # The 2027 marketplace window is in court, so the box links out instead.
        box = _between(_page(date(2026, 10, 18)), 'id="enroll"', "</section>")
        for day in ("November 1", "December 15", "January 15"):
            self.assertNotIn(day, box)

    def test_page_drops_the_medicare_line_after_december_7(self):
        html = _page(date(2026, 12, 8))
        self.assertIn('id="enroll"', html)
        self.assertNotIn("Medicare open enrollment runs", html)

    def test_page_has_no_enrollment_box_after_the_season(self):
        html = _page(date(2027, 1, 16))
        self.assertNotIn('id="enroll"', html)
        self.assertNotIn("Picking a 2027 HealthCare.gov plan?", html)
        self.assertNotIn("<b>Open enrollment:</b>", html)


class TestDenialWatchWhoToCall(TestCase):
    """Where to turn, by kind of coverage, and from each state on the map."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.content = _page()
        cls.js = (REPO / "fighthealthinsurance" / "static" / "js" / "denial_watch.js").read_text()

    def test_card_sits_in_what_you_can_do(self):
        section = _between(self.content, 'id="act"', "</section>")
        self.assertIn('id="who-to-call"', section)

    def test_card_links_each_office(self):
        card = _between(self.content, 'id="who-to-call"', "</section>")
        for href in (
            "https://askebsa.dol.gov/",
            "https://www.medicare.gov/my/medicare-complaint",
            "https://content.naic.org/state-insurance-departments",
            "https://www.cms.gov/initiatives/your-patient-rights/medical-bill-rights",
            "https://www.shiphelp.org/",
            reverse("state_help_index"),
        ):
            self.assertIn(f'href="{href}"', card)

    def test_card_gives_each_phone_number(self):
        card = _between(self.content, 'id="who-to-call"', "</section>")
        for phone in ("1-866-444-3272", "1-800-633-4227", "1-800-985-3059", "1-877-839-2675"):
            self.assertIn(phone, card)

    def test_medicare_denials_go_to_appeal_not_the_complaint_form(self):
        card = _between(self.content, 'id="who-to-call"', "</section>")
        self.assertIn("To fight a denial, appeal with the steps in your notice.", card)

    def test_map_readout_links_to_the_state_help_pages(self):
        self.assertIn(f'data-state-help="{reverse("state_help_index")}"', self.content)
        self.assertIn("$('dread').innerHTML=h+helpLink(s)", self.js)

    def test_every_map_state_has_a_state_help_page(self):
        from fighthealthinsurance.state_help import load_state_help

        names = dict(re.findall(r"([A-Z]{2}):'([^']+)'", re.search(r"const NAMES=\{(.*?)\};", self.js).group(1)))
        self.assertEqual(len(names), 51)
        pages = load_state_help()
        for code, name in names.items():
            # The script's slug: the name, lower case, hyphens for spaces.
            slug = name.lower().replace(" ", "-")
            self.assertIn(slug, pages, code)
            self.assertEqual(reverse("state_help", kwargs={"slug": slug}), f"{reverse('state_help_index')}{slug}/")


class TestDenialWatchPlanClockAndPriorAuth(TestCase):
    """The plan's deadlines sit with prior authorization, which says it isn't every plan."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.section = _between(_page(), 'id="prior-auth"', "</section>")

    def test_clock_gives_the_deadlines_and_who_they_cover(self):
        clock = _between(self.section, 'id="plan-clock"', "</div>")
        for words in (
            "Since 2026, Medicare Advantage, Medicaid and CHIP plans",
            "within 72 hours if it's urgent, or 7 days if not",
            "up to 14 more days",
            "a missed deadline counts as a denial you can appeal",
            "the specific reason",
            "15 days (72 hours if urgent)",
            "don't cover prescription drugs",
        ):
            self.assertIn(words, clock)

    def test_clock_cites_the_cms_rule(self):
        self.assertIn(
            'href="https://www.cms.gov/newsroom/fact-sheets/cms-interoperability-and-prior-authorization-final-rule-cms-0057-f"',
            self.section,
        )

    def test_section_says_it_shows_the_largest_plans_found(self):
        self.assertIn(f"these {len(DATA['prior_auth'])} are the largest we found", self.section)

    def test_section_points_to_the_fuller_collections(self):
        self.assertIn('<a href="https://www.authdenied.com/">AuthDenied</a>', self.section)
        self.assertIn(
            'href="https://www.kff.org/patient-consumer-protections/prior-authorization-metrics-provide-new-insights-into-insurer-practices-but-gaps-remain/"',
            self.section,
        )


class TestDenialWatchOthersAppeals(TestCase):
    """Lookups of how others' appeals went sit with independent review."""

    def test_lookups_link_california_new_york_and_propublica(self):
        section = _between(_page(), 'id="appeals"', "</section>")
        card = _between(section, 'id="others-appeals"', "</div>")
        for href in (
            "https://data.chhs.ca.gov/dataset/independent-medical-review-imr-determinations-trend",
            "https://www.dfs.ny.gov/public-appeal/search",
            "https://projects.propublica.org/claimfile/",
        ):
            self.assertIn(f'href="{href}"', card)


class TestDenialWatchMedicareDrugs(TestCase):
    """Medicare drug help and the negotiated-price tags, from the curated file."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.b = _load_builder()
        cls.prices = cls.b.load_medicare_prices()
        cls.costs = _between(_page(), 'id="costs"', "</section>")

    def test_tags_match_the_curated_file(self):
        for r in SHOWN_DRUGS:
            if r["Brnd_Name"] in self.prices:
                self.assertEqual(r["medicare_price"], self.prices[r["Brnd_Name"]], r["Brnd_Name"])
            else:
                self.assertNotIn("medicare_price", r, r["Brnd_Name"])

    def test_every_curated_brand_is_a_shown_drug(self):
        # A misspelt brand would tag nothing.
        self.assertLessEqual(set(self.prices), {r["Brnd_Name"] for r in SHOWN_DRUGS})

    def test_every_price_row_cites_cms(self):
        with open(REPO / "scripts" / "denial_watch" / "medicare_prices.csv", newline="") as f:
            for r in csv.DictReader(f):
                self.assertRegex(r["source_url"], r"^https://www\.cms\.gov/", r["brand"])

    def test_tags_say_the_year(self):
        label = self.b.medicare_price_label
        self.assertEqual(label(2026, None, True), "Medicare price from 2026")
        self.assertEqual(label(2026, 2026, True), "Medicare price in 2026 only")
        self.assertEqual(label(2028, None, False), "Picked for a Medicare price in 2028")

    def test_xarelto_price_ends_after_2026(self):
        # CMS removed it from 2027 because a generic is marketed.
        self.assertEqual(self.prices["Xarelto"]["label"], "Medicare price in 2026 only")

    def test_script_shows_the_tag_escaped(self):
        js = (REPO / "fighthealthinsurance" / "static" / "js" / "denial_watch.js").read_text()
        self.assertIn('<span class="dw-chip">${esc(d.medicare_price.label)}</span>', js)

    def test_page_says_the_negotiated_price_is_not_your_copay(self):
        note = _between(self.costs, 'id="dgprice"', "</p>")
        self.assertIn("not your copay", note)
        self.assertIn(
            'href="https://www.medicare.gov/health-drug-plans/part-d/what-drug-plans-cover/how-drug-plans-work"', note
        )

    def test_drug_help_gives_the_cap_and_where_to_get_help(self):
        card = _between(self.costs, 'id="drug-help"', "</div>")
        self.assertIn("$2,100 in 2026 and $2,400 in 2027", card)
        for href in (
            "https://www.medicare.gov/basics/costs/help/drug-costs",
            "https://www.medicare.gov/prescription-payment-plan",
            "https://www.shiphelp.org/",
        ):
            self.assertIn(f'href="{href}"', card)


class TestDenialWatchMoreData(TestCase):
    """Where to find more data like this, just before the sources."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.content = _page()
        cls.section = _between(cls.content, 'id="more-data"', "</section>")

    def test_listing_comes_just_before_sources(self):
        self.assertLess(self.content.index('id="gaps"'), self.content.index('id="more-data"'))
        self.assertLess(self.content.index('id="more-data"'), self.content.index('id="sources"'))

    def test_listing_links_authdenied_plaininsurer_and_kff(self):
        for href in (
            "https://www.authdenied.com/",
            "https://plaininsurer.com/states",
            "https://www.kff.org/patient-consumer-protections/claims-denials-and-appeals-in-aca-marketplace-plans-in-2024/",
        ):
            self.assertIn(f'href="{href}"', self.section)

    def test_plaininsurer_line_says_why_its_rates_differ(self):
        self.assertIn("outside the plan's network", self.section)

    def test_join_forces_note_links_to_contact(self):
        self.assertIn("join forces", self.section)
        self.assertIn(f'href="{reverse("contact")}"', self.section)


class TestDenialWatchLinksAndStyle(TestCase):
    """Every outside link on the page is https, and the copy has no em dashes."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        html = _page(date(2026, 10, 18))
        cls.body = _between(html, '<div class="fhi-page-wide dw"', '<script id="dw-data"')

    def test_outside_links_are_https(self):
        for href in re.findall(r'href="([^"]+)"', self.body):
            if not href.startswith(("/", "#")):
                self.assertTrue(href.startswith("https://"), href)

    def test_no_em_dashes(self):
        self.assertNotIn("—", self.body)

    def test_new_facts_are_in_the_sources(self):
        sources = _between(self.body, 'id="sources"', "</section>")
        for href in (
            "https://www.cms.gov/files/document/2027-announcement.pdf",
            "https://www.cms.gov/files/document/ipay-2028-final-guidance.pdf",
            "https://www.federalregister.gov/documents/2024/02/08/2024-00895/medicare-and-medicaid-programs-patient-protection-and-affordable-care-act-advancing-interoperability",
            "https://www.cms.gov/newsroom/press-releases/medicare-advantage-medicare-prescription-drug-programs-expected-remain-stable-2027",
        ):
            self.assertIn(f'href="{href}"', sources)
