from typing import Any, Optional

from fighthealthinsurance.state_help import get_state_help_by_abbreviation

STATE_CONFIG: dict[str, dict[str, Any]] = {
    "CA": {
        "state": "CA",
        "regulator_name": "California Department of Managed Health Care",
        "external_review_url": "https://www.dmhc.ca.gov/FileaComplaint.aspx#howToApply",
        "form_url": "https://www.dmhc.ca.gov/FileaComplaint/IndependentMedicalReviewComplaintForms.aspx#imrForms",
        "phone": "1-888-466-2219",
        "deadline_days_or_months": "6 months",
        "expedited_available": True,
        "notes": "Department of Insurance may apply for some plans.",
        "last_verified_at": "2026-05-02",
    },
    "NY": {
        "state": "NY",
        "regulator_name": "New York Department of Financial Services",
        "external_review_url": "https://www.dfs.ny.gov/complaints/file_external_appeal",
        "form_url": "https://myportal.dfs.ny.gov/web/externalappeals",
        "phone": "1-800-400-8882",
        "deadline_days_or_months": "4 months",
        "expedited_available": True,
        "notes": "Check plan notices for exact filing window.",
        "last_verified_at": "2026-05-02",
    },
    "TX": {
        "state": "TX",
        "regulator_name": "Texas Department of Insurance",
        "external_review_url": "https://www.tdi.texas.gov/consumer/complaint-health.html",
        "form_url": "https://www.tdi.texas.gov/consumer/file-health-cmplnt.html",
        "phone": "1-800-252-3439",
        "deadline_days_or_months": "4 months",
        "expedited_available": True,
        "notes": "Expedited review available for urgent situations.",
        "last_verified_at": "2026-05-02",
    },
    "WA": {
        "state": "WA",
        "regulator_name": "Washington Office of the Insurance Commissioner",
        "external_review_url": "https://www.insurance.wa.gov/sites/default/files/2024-10/appeals-guide.pdf",
        "form_url": "https://www.insurance.wa.gov/insurance-resources/health-insurance/appealing-health-insurance-denial/how-appeal-health-insurance-denial",
        "phone": "1-800-562-6900",
        "deadline_days_or_months": "...",
        "expedited_available": True,
        "notes": "Some plans route through federal process.",
        "last_verified_at": "2026-05-02",
    },
    "IL": {
        "state": "IL",
        "regulator_name": "Illinois Department of Insurance",
        "external_review_url": "https://idoi.illinois.gov/consumers/file-an-external-review.html",
        "form_url": "https://idoi.illinois.gov/consumers/file-an-external-review.html",
        "phone": "1-866-445-5364",
        "deadline_days_or_months": "4 months",
        "expedited_available": True,
        "notes": "External review eligibility depends on product type.",
        "last_verified_at": "2026-05-02",
    },
    "AZ": {
        "state": "AZ",
        "regulator_name": "Arizona Department of Insurance and Financial Institutions",
        "external_review_url": "https://difi.az.gov/",
        "form_url": "https://difi.az.gov/consumers/health-insurance#appeals-forms",
        "phone": "1-800-325-2548",
        "deadline_days_or_months": "4 months",
        "expedited_available": True,
        "notes": "Check plan denial for exact filing deadline.",
        "last_verified_at": "2026-05-02",
    },
    "CO": {
        "state": "CO",
        "regulator_name": "Colorado Division of Insurance",
        "external_review_url": "https://doi.colorado.gov/sites/doi/files/documents/When%20Your%20Health%20Insurance%20Company%20Says%20_No_.pdf",
        "form_url": "https://doi.colorado.gov/sites/doi/files/documents/When%20Your%20Health%20Insurance%20Company%20Says%20_No_.pdf",
        "phone": "1-800-930-3745",
        "deadline_days_or_months": "",
        "expedited_available": True,
        "notes": "Independent review pathway can vary by policy.",
        "last_verified_at": "2026-05-02",
    },
    "GA": {
        "state": "GA",
        "regulator_name": "Georgia Office of Commissioner of Insurance",
        "external_review_url": "https://healthyfuturega.org/wp-content/uploads/2015/12/ET10_AppealsComplaints.pdf",
        "form_url": "https://oci.georgia.gov/consumer-services/file-complaint",
        "phone": "1-800-656-2298",
        "deadline_days_or_months": "6 months",
        "expedited_available": True,
        "notes": "Use complaint + external review instructions from denial packet.",
        "last_verified_at": "2026-05-02",
    },
}

FEDERAL_FALLBACK: dict[str, Any] = {
    "state": "FEDERAL",
    "regulator_name": "CMS / Federal External Review",
    "external_review_url": "https://www.cms.gov/CCIIO/Programs-and-Initiatives/Consumer-Support-and-Information/External-Appeals",
    "form_url": "https://www.cms.gov/CCIIO/Programs-and-Initiatives/Consumer-Support-and-Information/External-Appeals",
    "phone": "1-877-267-2323",
    "deadline_days_or_months": "varies",
    "expedited_available": True,
    "notes": "Federal fallback when state route is unclear.",
    "last_verified_at": "2026-05-02",
}


def get_state_config(state: Optional[str]) -> dict[str, Any]:
    if not state:
        result = dict(FEDERAL_FALLBACK)
        result["notes"] = f'{result["notes"]} State not provided.'
        return result

    state_up = state.upper().strip()
    if state_up in STATE_CONFIG:
        return dict(STATE_CONFIG[state_up])

    result = dict(FEDERAL_FALLBACK)
    result.update(
        {
            "state": state_up,
            "not_configured": True,
            "notes": f"State {state_up} not yet configured. Use state DOI plus federal instructions.",
        }
    )
    # Even without a hand-verified external-review entry we know the
    # state's insurance regulator (name, consumer phone line, complaint
    # URL) from state_help.json, which covers every state plus DC. Point
    # the user at their actual regulator instead of only the federal
    # fallback number.
    state_help = get_state_help_by_abbreviation(state_up)
    if state_help is not None and state_help.insurance_department.name:
        dept = state_help.insurance_department
        complaint_url = dept.complaint_url or dept.url
        external_review_url = complaint_url
        if state_help.external_review and state_help.external_review.info_url:
            external_review_url = state_help.external_review.info_url
        result.update(
            {
                "regulator_name": dept.name,
                "phone": dept.consumer_line or dept.phone or result["phone"],
                "external_review_url": external_review_url
                or result["external_review_url"],
                "form_url": complaint_url or result["form_url"],
                "notes": (
                    f"External review details for {state_help.name} have not "
                    f"been hand-verified yet; contact {dept.name} to confirm "
                    "the exact process and deadlines, and keep the federal "
                    "instructions as a backup."
                ),
                "deadline_days_or_months": "varies",
            }
        )
    return result
