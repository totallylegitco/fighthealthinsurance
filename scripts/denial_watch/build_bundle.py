"""Build static/denial_watch.json, the numbers behind the Denial Watch page.

Every number on the page comes from the public files listed in README.md next
to this script. Download them into a raw directory, then:

    pip install pandas openpyxl
    python scripts/denial_watch/build_bundle.py --raw-dir /path/to/raw

It writes fighthealthinsurance/static/denial_watch.json and prints the headline
figures so a person can check them against the last build before committing.
This runs by hand, not in the app: the site only ever reads the JSON.
"""

import csv
import io
import json
import math
import pathlib
import re

import argparse
import datetime
import sys
import typing

if typing.TYPE_CHECKING:
    import pandas as pd

HERE = pathlib.Path(__file__).parent
REPO = HERE.parent.parent
DEFAULT_OUT = REPO / "fighthealthinsurance" / "static" / "denial_watch.json"
RAW = HERE / "raw"  # replaced by --raw-dir

# PUF plan year -> the calendar year its claims come from.
CLAIMS_YEAR = {2022: 2020, 2023: 2021, 2024: 2022, 2025: 2023, 2026: 2024}
LATEST_PY = 2026
MIN_ISSUER_CLAIMS = 50_000  # in-network claims, for the insurer table
MIN_APPEALS_FOR_RATE = 30  # an insurer's appeal win rate is shown only on this many appeals
MIN_STATE_APPEALS = 50

# Plan-level reason columns (in-network, and a claim can count under more than one).
REASONS = {
    "plan_number_claims_denied_referral_required": "Prior authorization or referral required",
    "plan_number_claims_denied_due_to_out_of_network": "Out of network",
    "plan_number_claims_denied_services_excluded": "Service excluded from the plan",
    "plan_number_claims_denied_not_medically_necessary_excluding_behavioral_health": '"Not medically necessary" (physical health)',
    "plan_number_claims_denied_not_medically_necessary_behavioral_health_only": '"Not medically necessary" (behavioral health)',
    "plan_number_claims_denied_due_to_enrolle_benefit_limit_reached": "Benefit limit reached",
    "plan_number_claims_denied_due_to_member_not_covered": "Person not covered on the date of service",
    "plan_number_claims_denied_due_to_investigational_experimental_cosmetic_proceduce": "Experimental, investigational or cosmetic",
    "plan_number_claims_denied_due_to_administrative_reason": "Administrative (missing information, duplicate, late filing, billing)",
    "plan_number_claims_denied_other": "Other / not specified",
}
PLAN_DENIED_IN = "plan_number_claims_denied_in_network"


def num(x):
    """A reported count, or None for suppressed/blank cells ('*', '**', '***', 'N/A')."""
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    if isinstance(x, str) and re.fullmatch(r"\s*[\d,]+(\.\d+)?\s*", x):
        return float(x.replace(",", ""))
    return None


def norm(h):
    return re.sub(r"[^A-Za-z_]", "", h or "").lower()


def read_puf(py):
    import openpyxl

    wb = openpyxl.load_workbook(RAW / f"tic{py}.xlsx", read_only=True)
    ws = next(w for w in wb.worksheets if "Ind QHP" in w.title)
    hdr, issuers, reasons, plan_denied = None, {}, {}, 0.0
    for row in ws.iter_rows(values_only=True):
        if hdr is None:
            if row and "Issuer_ID" in row:
                hdr = [norm(c) for c in row]
            continue
        r = dict(zip(hdr, row))
        if not r.get("state"):
            continue
        kind = r.get("qhporsadp") or r.get("qhpsadp")
        if kind and kind != "QHP":
            continue

        def g(*keys):
            return next((num(r.get(k)) for k in keys if k in r), None)

        key = (r["state"], r["issuer_id"])
        if key not in issuers:  # issuer fields repeat on every plan row
            issuers[key] = dict(
                state=r["state"], issuer=str(r["issuer_name"]).strip(), id=r["issuer_id"],
                rec_in=g("issuer_claims_received_in_network"), den_in=g("issuer_claims_denied_in_network"),
                rec_out=g("issuer_claims_received_out_of_network"), den_out=g("issuer_claims_denied_out_of_network"),
                rec_all=g("issuer_claims_received"), den_all=g("issuer_claims_denials", "issuer_claims_denied"),
                ap_filed=g("issuer_internal_appeals_filed"), ap_over=g("issuer_number_internal_appeals_overturned"),
            )
        for col in REASONS:
            v = num(r.get(col))
            if v:
                reasons[col] = reasons.get(col, 0.0) + v
        plan_denied += num(r.get(PLAN_DENIED_IN)) or 0.0
    return list(issuers.values()), reasons, plan_denied


def all_claims(i):
    if i["rec_all"] and i["den_all"] is not None:
        return i["rec_all"], i["den_all"]
    parts = (i["rec_in"], i["rec_out"], i["den_in"], i["den_out"])
    if None not in parts and i["rec_in"] + i["rec_out"]:
        return i["rec_in"] + i["rec_out"], i["den_in"] + i["den_out"]
    return None


def matched_appeals(issuers):
    """Appeals filed and overturned, counting only issuers that reported both numbers."""
    both = [i for i in issuers if i["ap_filed"] is not None and i["ap_over"] is not None]
    return sum(i["ap_filed"] for i in both), sum(i["ap_over"] for i in both)


def state_rates(issuers):
    out = {}
    for i in issuers:
        if not (i["rec_in"] and i["den_in"] is not None):
            continue
        s = out.setdefault(i["state"], dict(rec=0.0, den=0.0, n=0, ap=0.0, ov=0.0))
        s["rec"] += i["rec_in"]
        s["den"] += i["den_in"]
        s["n"] += 1
        if i["ap_filed"] is not None and i["ap_over"] is not None:
            s["ap"] += i["ap_filed"]
            s["ov"] += i["ap_over"]
    return {
        k: dict(rate=v["den"] / v["rec"], denied=v["den"], claims=v["rec"], issuers=v["n"],
                appeals=v["ap"], overturned=v["ov"],
                won=(v["ov"] / v["ap"] if v["ap"] >= MIN_STATE_APPEALS else None))
        for k, v in out.items()
    }


def build_denials():
    trend, per_year = [], {}
    for py, cy in CLAIMS_YEAR.items():
        issuers, reasons, plan_denied = read_puf(py)
        per_year[py] = (issuers, reasons, plan_denied)
        pairs = [p for p in map(all_claims, issuers) if p]
        filed, over = matched_appeals(issuers)
        t = dict(year=cy, days=366 if cy % 4 == 0 else 365, claims=sum(p[0] for p in pairs),
                 denied=sum(p[1] for p in pairs), appeals=filed, overturned=over,
                 appeals_all=sum(i["ap_filed"] or 0 for i in issuers),
                 states=len({i["state"] for i in issuers}), issuers=len(issuers))
        t["rate"] = t["denied"] / t["claims"]
        inn = [i for i in issuers if i["rec_in"] and i["den_in"] is not None]
        if inn:
            t["in_denied"] = sum(i["den_in"] for i in inn)
            t["in_claims"] = sum(i["rec_in"] for i in inn)
            t["in_rate"] = t["in_denied"] / t["in_claims"]
        trend.append(t)

    issuers, reasons, plan_denied = per_year[LATEST_PY]
    states = state_rates(issuers)
    prev = state_rates(per_year[LATEST_PY - 1][0])
    for k, v in states.items():
        if k in prev:
            v["prev"] = prev[k]["rate"]

    table = []
    for i in issuers:
        if not (i["rec_in"] and i["rec_in"] >= MIN_ISSUER_CLAIMS and i["den_in"] is not None):
            continue
        ok = i["ap_filed"] is not None and i["ap_over"] is not None and i["ap_filed"] >= MIN_APPEALS_FOR_RATE
        table.append(dict(s=i["state"], n=i["issuer"], r=round(i["den_in"] / i["rec_in"], 4),
                          c=int(i["rec_in"]), d=int(i["den_in"]),
                          a=int(i["ap_filed"]) if ok else None, o=int(i["ap_over"]) if ok else None))

    reason_rows = sorted(({"k": REASONS[k], "v": v} for k, v in reasons.items()), key=lambda x: -x["v"])
    return dict(trend=trend, states=states, issuers=table, reasons=reason_rows,
                reason_meta=dict(entries=sum(reasons.values()), plan_denied_in=plan_denied))


IMR_LABELS = {
    "Mental Health": "Mental health care", "Pain Management": "Pain management",
    "Ear-Nose-Thro Proc": "Ear, nose & throat procedures", "Pharmacy": "Prescription drugs",
    "Acute Med Svc Inpt": "Inpatient hospital care", "Cardio-Vasc Proc": "Heart & vascular procedures",
    "DME": "Medical equipment", "Gen Surg Proc": "General surgery", "Cancer Care": "Cancer care",
    "Autism Related Tx": "Autism treatment", "Diag Imag & Screen": "Imaging & screening",
    "Reconstr/Plast Proc": "Reconstructive surgery", "Rehab/ Svc - Outpt": "Outpatient rehab",
    "Orthopedic Proc": "Orthopedic procedures", "Rehab/Svcs SNF Inpt": "Skilled nursing / inpatient rehab",
    "Elect/Therm/Radfreq": "Nerve & radiofrequency treatments", "Diag/ MD Eval": "Diagnostic evaluations",
    "Special Proc": "Special procedures",
}


def build_imr():
    import pandas as pd

    d = pd.read_csv(RAW / "imr.csv", usecols=["ReferenceID", "ReportYear", "TreatmentCategory", "Determination"])
    before = len(d)
    d = d.drop_duplicates()
    dup_ids = int(d.ReferenceID.duplicated().sum())
    d["o"] = d.Determination.str.startswith("Overturned")
    trend = [dict(y=int(y), n=int(g.size), r=round(float(g.mean()), 3))
             for y, g in d.groupby("ReportYear").o if 2010 <= y <= 2025]
    recent = d[(d.ReportYear >= 2021) & (d.ReportYear <= 2025)]
    cats = [dict(k=IMR_LABELS.get(k, k), n=int(g.size), r=round(float(g.mean()), 3))
            for k, g in recent.groupby("TreatmentCategory").o if g.size >= 100]
    cats.sort(key=lambda x: -x["r"])
    return dict(imr_trend=trend, imr_cat=cats,
                imr_meta=dict(duplicates_dropped=before - len(d), duplicate_ids_left=dup_ids))


def build_drugs():
    import pandas as pd

    p = pd.read_csv(RAW / "partd.csv")
    p = p[p.Mftr_Name == "Overall"].copy()
    cols = ["Brnd_Name", "Gnrc_Name", "Tot_Spndng_2024", "Tot_Benes_2024", "Avg_Spnd_Per_Bene_2024",
            "Tot_Spndng_2020", "Avg_Spnd_Per_Clm_2024"]
    for c in cols[2:]:
        p[c] = pd.to_numeric(p[c], errors="coerce")

    def rows(df):
        out = []
        for t in df[cols].itertuples(index=False):
            out.append({k: (None if isinstance(v, float) and math.isnan(v)
                            else v.strip().rstrip("*") if isinstance(v, str) else float(v))
                        for k, v in zip(cols, t)})
        return out

    g = p[p.Tot_Spndng_2020 >= 1e8].copy()
    g["x"] = g.Tot_Spndng_2024 / g.Tot_Spndng_2020
    return dict(
        total=dict(y2024=float(p.Tot_Spndng_2024.sum()), y2020=float(p.Tot_Spndng_2020.sum())),
        top=rows(p.nlargest(10, "Tot_Spndng_2024")),
        per=rows(p[p.Tot_Benes_2024 >= 1000].nlargest(10, "Avg_Spnd_Per_Bene_2024")),
        growth=rows(g.nlargest(10, "x")),
        cheap=rows(p[p.Tot_Benes_2024 >= 2_000_000].nsmallest(10, "Avg_Spnd_Per_Clm_2024")),
    )


def build_sahie():
    out = {}
    for y in (2023, 2024):
        lines = (RAW / f"sahie_{y}.csv").read_text(encoding="latin-1").splitlines()
        start = next(i for i, l in enumerate(lines) if l.startswith("year"))
        yr = {}
        for row in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
            k = {a.strip(): b.strip() for a, b in row.items() if a}
            if (k["geocat"], k["agecat"], k["racecat"], k["sexcat"], k["iprcat"]) == ("40", "0", "0", "0", "0"):
                yr[k["state_name"]] = dict(pct=float(k["PCTUI"]), n=int(k["NUI"]))
        out[str(y)] = yr
    return out


PLACES = {"GHLTH": "fair_poor_health", "DIABETES": "diabetes", "DEPRESSION": "depression"}


def build_places():
    import pandas as pd

    d = pd.read_csv(RAW / "places_county.csv", dtype=str)
    d["p"] = pd.to_numeric(d.TotalPop18plus, errors="coerce")
    res = {}
    for st, g in d.groupby("StateAbbr"):
        res[st] = {}
        for m, name in PLACES.items():
            v = pd.to_numeric(g[m + "_CrudePrev"], errors="coerce")
            w = g.p[v.notna()]
            if w.sum():
                res[st][name] = round(float((v[v.notna()] * w).sum() / w.sum()), 1)
    return res


def correlations(sahie, places):
    """State-level Pearson r between the uninsured rate and each health measure (for the copy)."""
    import pandas as pd

    abbr = {n: a for a, n in STATE_NAMES.items()}
    out = {}
    for m in PLACES.values():
        xs, ys = [], []
        for name, v in sahie["2024"].items():
            a = abbr.get(name)
            if a in places and m in places[a]:
                xs.append(v["pct"])
                ys.append(places[a][m])
        out[m] = round(float(pd.Series(xs).corr(pd.Series(ys))), 2)
    return out


STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}


PRIOR_AUTH_CSV = HERE / "prior_auth_2025.csv"


def build_prior_auth(path=PRIOR_AUTH_CSV):
    """Insurers' own 2025 prior-authorization reports (CMS-0057-F), as posted.

    prior_auth_2025.csv is hand-curated: each row was copied from the
    insurer's or state's own page (source_url), with a plain display name and
    place. Rows whose scope or units were unclear are left out of that file.
    """
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(dict(
                line=r["line"], n=r["insurer"], where=r["where"],
                std=float(r["std_denied_pct"]) / 100 if r["std_denied_pct"] else None,
                exp=float(r["exp_denied_pct"]) / 100 if r["exp_denied_pct"] else None,
                std_posted=r["std_denied_pct"] or None, exp_posted=r["exp_denied_pct"] or None,
                req=int(r["std_requests"]) if r["std_requests"] else None,
                unit=r["unit"],
                note=r["note"], url=r["source_url"],
            ))
    return rows


SOURCES = [
    dict(name="CMS Transparency in Coverage public use files", years="plan years 2022-2026 (claims 2020-2024)",
         url="https://www.cms.gov/marketplace/resources/data/public-use-files"),
    dict(name="California DMHC Independent Medical Review determinations", years="2010-2025",
         url="https://data.chhs.ca.gov/dataset/independent-medical-review-imr-determinations-trend"),
    dict(name="Census Small Area Health Insurance Estimates", years="2023-2024",
         url="https://www.census.gov/programs-surveys/sahie.html"),
    dict(name="CDC PLACES county data", years="2025 release",
         url="https://www.cdc.gov/places/"),
    dict(name="Insurers' and states' own prior-authorization reports (CMS-0057-F)", years="2025",
         url="https://www.cms.gov/initiatives/burden-reduction/overview/interoperability/policies-regulations/cms-interoperability-prior-authorization-final-rule-cms-0057-f"),
    dict(name="CMS Medicare Part D Spending by Drug", years="2020-2024",
         url="https://data.cms.gov/summary-statistics-on-use-and-payments/medicare-medicaid-spending-by-drug/medicare-part-d-spending-by-drug"),
]


def main(argv=None):
    global RAW
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw-dir", type=pathlib.Path, default=RAW, help="directory holding the downloaded source files")
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    RAW = args.raw_dir
    missing = [n for n in [f"tic{py}.xlsx" for py in CLAIMS_YEAR] + ["imr.csv", "partd.csv", "sahie_2023.csv", "sahie_2024.csv", "places_county.csv"]
               if not (RAW / n).exists()]
    if missing:
        sys.exit(f"missing source files in {RAW}: {', '.join(missing)} (see README.md)")

    bundle = build_denials()
    bundle.update(build_imr())
    bundle["drugs"] = build_drugs()
    bundle["sahie"] = build_sahie()
    bundle["places"] = build_places()
    bundle["corr"] = correlations(bundle["sahie"], bundle["places"])
    bundle["prior_auth"] = build_prior_auth()
    bundle["sources"] = SOURCES
    bundle["built"] = datetime.date.today().isoformat()
    args.out.write_text(json.dumps(bundle, separators=(",", ":"), sort_keys=True) + "\n")
    print("wrote", args.out)

    for t in bundle["trend"]:
        print(t["year"], f"rate {t['rate']:.2%}", f"in {t.get('in_rate', 0):.2%}",
              f"denied {t['denied']:,.0f}", f"appeals {t['appeals']:,.0f}",
              f"won {t['overturned'] / t['appeals']:.2%}", f"states {t['states']}")
    rm = bundle["reason_meta"]
    print("reason entries", f"{rm['entries']:,.0f}", "plan-level in-network denials", f"{rm['plan_denied_in']:,.0f}")
    print("imr", bundle["imr_meta"], [r for r in bundle["imr_trend"] if r["y"] in (2017, 2025)])
    print("issuers", len(bundle["issuers"]), "corr", bundle["corr"])
    for line in ("ma", "mcd", "mkt", "ffs"):
        std = [r["std"] for r in bundle["prior_auth"] if r["line"] == line and r["std"] is not None]
        print("prior auth", line, len(std), f"{min(std):.2%} to {max(std):.2%}")


if __name__ == "__main__":
    main()
