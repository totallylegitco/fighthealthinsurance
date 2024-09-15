from django.forms import Form
from django.core.validators import validate_email

from fighthealthinsurance.forms import *
from fighthealthinsurance.models import *
from fighthealthinsurance.generate_appeal import *
from dataclasses import dataclass

import uszipcode

appealGenerator = AppealGenerator()


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
    semi_sekret: str

    def convert_to_serializable(self):
        return NextStepInfoSerializable(
            outside_help_details,
            map(self._field_to_dict, self.combined_form.items()),
            semi_sekret,
        )

    def _field_to_dict(self, field_name, field):
        label = field.label
        visible = not field.hidden_widget
        required = field.required
        help_text = field.help_text
        initial = field.initial
        field_type = field.__class__.__name__
        return {
            "field_name": field_type,
            "label": label,
            "visible": visble,
            "required": required,
            "help_text": help_text,
            "initial": initial,
            "type": field_type,
        }


@dataclass
class NextStepInfoSerializable:
    outside_help_details: list[str]
    combined_form: list[any]
    semi_sekret: str


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
        semi_sekret,
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
            semi_sekret=semi_sekret,
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
        return NextStepInfo(outside_help_details, combined_form, semi_sekret)


@dataclass
class DenialResponseInfo:
    selected_denial_type: list[DenialTypes]
    all_denial_types: list[DenialTypes]
    denial_id: str
    your_state: str
    procedure: str
    diagnosis: str
    semi_sekret: str


class DenialCreatorHelper:
    regex_denial_processor = ProcessDenialRegex()
    codes_denial_processor = ProcessDenialCodes()
    regex_src = DataSource.objects.get(name="regex")
    codes_src = DataSource.objects.get(name="codes")
    zip_engine = uszipcode.search.SearchEngine()
    all_denial_types = DenialTypes.objects.all()

    @classmethod
    def create_denial(
        cls,
        email,
        denial_text,
        zip,
        pii=False,
        tos=False,
        privacy=False,
        use_external_models=False,
        store_raw_email=False,
    ):
        hashed_email = Denial.get_hashed_email(email)
        # If they ask us to store their raw e-mail we do
        possible_email = None
        validate_email(email)
        if store_raw_email:
            possible_email = email

        denial = Denial.objects.create(
            denial_text=denial_text,
            hashed_email=hashed_email,
            use_external=use_external_models,
            raw_email=possible_email,
        )

        # Try and guess at the denial types
        denial_types = cls.regex_denial_processor.get_denialtype(denial_text)
        denial_type = []
        for dt in denial_types:
            DenialTypesRelation(denial=denial, denial_type=dt, src=cls.regex_src).save()
            denial_type.append(dt)

        # Guess at the plan type
        plan_type = cls.codes_denial_processor.get_plan_type(denial_text)
        # Infer the state
        your_state = None
        if zip is not None and zip != "":
            try:
                your_state = cls.zip_engine.by_zipcode(zip).state
            except:
                # Default to no state
                your_state = None
        (procedure, diagnosis) = appealGenerator.get_procedure_and_diagnosis(
            denial_text
        )
        return DenialResponseInfo(
            denial_type,
            cls.all_denial_types,
            denial.denial_id,
            your_state,
            procedure,
            diagnosis,
            denial.semi_sekret,
        )
