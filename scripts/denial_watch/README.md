# Denial Watch data

`/denial-watch` shows only public data. Its numbers live in
`fighthealthinsurance/static/denial_watch.json`, which `build_bundle.py` makes
from the files below. The site never reads the database for this page, and
nothing here runs in the app.

## Refresh

1. Download the sources into a directory (the default is `scripts/denial_watch/raw/`,
   which git ignores):

   | File | Source |
   |---|---|
   | `tic2022.xlsx` … `tic2025.xlsx` | `https://data.healthcare.gov/datafile/py<YEAR>/transparency_in_coverage_PUF.xlsx` |
   | `tic2026.xlsx` | `Transparency_in_Coverage_PUF.xlsx` inside `https://download.cms.gov/marketplace-puf/2026/transparency-in-coverage-puf.zip` |
   | `imr.csv` | CSV on the [DMHC IMR dataset page](https://data.chhs.ca.gov/dataset/independent-medical-review-imr-determinations-trend) |
   | `partd.csv` | "Medicare Part D Spending by Drug" CSV from [data.cms.gov](https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug/medicare-part-d-spending-by-drug) |
   | `sahie_2023.csv`, `sahie_2024.csv` | `https://www2.census.gov/programs-surveys/sahie/datasets/time-series/estimates-acs/sahie-<YEAR>-csv.zip` (the Census API now needs a key; the zips don't) |
   | `places_county.csv` | `https://data.cdc.gov/api/v3/views/i46a-9kgh/export.csv` (the old `rows.csv?accessType=DOWNLOAD` link was retired in October 2026) |

2. Build:

   ```sh
   pip install pandas openpyxl
   python scripts/denial_watch/build_bundle.py --raw-dir scripts/denial_watch/raw
   ```

3. Compare the printed figures with the page's copy. The headline sentences in
   `templates/denial_watch.html` name some numbers, such as the about 7% to 27% state
   range, 72% in California, and the correlations. When a new year arrives, adding
   it means extending `CLAIMS_YEAR` and `LATEST_PY`, then rereading the copy.

## Rules the build follows

- CMS suppresses small counts (`*`, `**`), and those cells are left out, never
  treated as zero. Appeal win rates use only insurers that reported both appeals
  filed and appeals won.
- Denial reasons are plan-level, in-network, and not exclusive (one claim can
  count under several), so the page shows them as shares of reasons, not of
  claims. CMS's out-of-network reason counts closed-network denials, so it is
  left out, as KFF leaves it out.
- The California IMR file has some exact duplicate rows, which are dropped.
- `medicare_prices.csv` tags each shown drug that has a Medicare-negotiated
  price, one row per brand with the CMS page it was checked against. The build
  doesn't look drugs up, so after a refresh check any newly shown drug against
  CMS's selected-drug lists. Update the file when CMS publishes the 2028 prices
  (due by November 30, 2026) and picks the next drugs (by February 1, 2027).
- The open-enrollment box's dates and plan year come from `views.py`
  (`DENIAL_WATCH_MEDICARE_ENROLLMENT`, `DENIAL_WATCH_ENROLLMENT_BOX_ENDS`); the
  box hides itself after the season. Each fall, also recheck its Sources line,
  which cites that year's CMS announcement.
- `medicare_prices.csv` must say `yes` or `no` for `price_published`, and the
  build stops on anything else or on a `price_until` before `price_from`.
- Insurer rows need at least 50,000 in-network claims. An insurer's appeal win
  rate needs at least 30 appeals, and a state's needs 50. When CMS withholds an
  insurer's number won, its row says "not reported" rather than "too few".
