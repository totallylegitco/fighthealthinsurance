from django.forms import Form

from fighthealthinsurance.forms import *
from fighthealthinsurance.models import *
from fighthealthinsurance.generate_appeal import *
from dataclasses import dataclass


class RemoveDataHelper:
    @classmethod
    def remove_data_for_email(cls, email: str):
        hashed_email = Denial.get_hashed_email(email)
        denials = Denial.objects.filter(hashed_email=hashed_email).delete()
        FollowUpSched.objects.filter(email=email).delete()


states_with_caps = {
    "AR",
    "CA",
    "CT",
    "DE",
    "DC",
    "GA",
    "IL",
    "IA",
    "KS",
    "KY",
    "ME",
    "MD",
    "MA",
    "MI",
    "MS",
    "MO",
    "MT",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "MP",
    "OK",
    "OR",
    "PA",
    "RI",
    "TN",
    "TX",
    "VT",
    "VI",
    "WV",
}


@dataclass
class NextStepInfo:
    outside_help_details: list[str]
    combined_form: Form


class FindNextStepsHelper:
    @classmethod
    def find_next_steps(
        cls,
        denial_id: str,
        email: str,
        procedure: str,
        diagnosis: str,
        insurance_company,
        plan_id,
        claim_id,
        denial_type,
        your_state,
        denial_date,
        captcha=None,
        denial_type_text=None,
        plan_source=None,
    ) -> (list[str], Form):
        hashed_email = Denial.get_hashed_email(email)
        # Update the denial
        denial = Denial.objects.filter(
            denial_id=denial_id,
            # Include the hashed e-mail so folks can't brute force denial_id
            hashed_email=hashed_email,
        ).get()
        denial.denial_date = denial_date

        denial.procedure = procedure
        denial.diagnosis = diagnosis
        if plan_source is not None:
            denial.plan_source.set(plan_source)
        denial.save()

        outside_help_details = []
        state = your_state

        if state in states_with_caps:
            outside_help_details.append(
                (
                    (
                        "<a href='https://www.cms.gov/CCIIO/Resources/Consumer-Assistance-Grants/"
                        + state
                        + "'>"
                        + f"Your state {state} participates in a "
                        + f"Consumer Assistance Program(CAP), and you may be able to get help "
                        + f"through them.</a>"
                    ),
                    "Visit <a href='https://www.cms.gov/CCIIO/Resources/Consumer-Assistance-Grants/'>CMS for more info</a>",
                )
            )
        if denial.regulator == Regulator.objects.filter(alt_name="ERISA").get():
            outside_help_details.append(
                (
                    (
                        "Your plan looks to be an ERISA plan which means your employer <i>may</i>"
                        + " have more input into plan decisions. If your are on good terms with HR "
                        + " it could be worth it to ask them for advice."
                    ),
                    "Talk to your employer's HR if you are on good terms with them.",
                )
            )
        denial.insurance_company = insurance_company
        denial.plan_id = plan_id
        denial.claim_id = claim_id
        if denial_type_text is not None:
            denial.denial_type_text = denial_type_text
        denial.denial_type.set(denial_type)
        denial.state = your_state
        denial.save()
        advice = []
        question_forms = []
        for dt in denial.denial_type.all():
            new_form = dt.get_form()
            if new_form is not None:
                new_form = new_form(initial={"medical_reason": dt.appeal_text})
                question_forms.append(new_form)
        combined_form = magic_combined_form(question_forms)
        return NextStepInfo(outside_help_details, combined_form)
