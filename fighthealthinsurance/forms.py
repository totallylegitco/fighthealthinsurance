from django import forms

from fighthealthinsurance.models import DenialTypes, PlanType


class DenialForm(forms.Form):
    zip = forms.BooleanField(required=False)
    pii = forms.BooleanField(required=True)
    privacy = forms.BooleanField(required=True)
    store_raw_email = forms.BooleanField(required=False)
    denial_text = forms.CharField(required=True)
    email = forms.EmailField(required=True)


class PostInferedForm(forms.Form):
    # Send denial id and e-mail back that way people can't just change the ID
    # and get someone elses denial.
    denial_id = forms.IntegerField(required=True, widget=forms.HiddenInput())
    email = forms.IntegerField(required=True, widget=forms.HiddenInput())
    denial_type = forms.ModelMultipleChoiceField(queryset=DenialTypes.objects.all())
    denial_type_text = forms.CharField(
        required=False,
        label="Denial Type (text, you can type if the categories don't match the denial type)")
    pre_service =  forms.BooleanField(required=False)
    plan_id = forms.CharField(required=False)
    claim_id = forms.CharField(required=False)
    insurance_company = forms.CharField(required=False)
    plan_type = forms.ModelMultipleChoiceField(queryset=PlanType.objects.all())
    plan_type_text = forms.CharField(required=False)
    denial_date = forms.DateField(required=False)
    your_state = forms.CharField(max_length="2", required=False)



class MedicalNeccessaryQuestions(forms.Form):
    """Questions to ask for medical necessiety."""
    medical_reason = forms.CharField(max_length=3000)
    urgent = forms.BooleanField(required=False)


class BalanceBillQuestions(forms.Form):
    """Questions to ask for surprise billing."""
    in_network = forms.BooleanField(required=False)
    emergency = forms.BooleanField(required=False)
    match_eob = forms.BooleanField(required=False)
    

class PriorAuthQuestions(forms.Form):
    """Question to ask for a prior auth denial."""
    in_network = forms.BooleanField(required=False)
    emergency = forms.CharField(required=False)
    prior_auth_id = forms.CharField(required=False)
    told_prior_auth_not_needed = forms.CharField(required=False)


class StepTherapy(forms.Form):
    """Question to ask for step therapy."""
    why_does_the_option_from_insurance_not_work = forms.CharField(required=False)
