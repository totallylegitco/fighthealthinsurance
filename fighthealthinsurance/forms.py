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
    denial_type = forms.ModelMultipleChoiceField(queryset=DenialTypes.objects.all())
    denial_type_text = forms.CharField(required=False)
    pre_service =  forms.BooleanField(required=False)
    urgent = forms.BooleanField(required=False)
    appeal_by_mail = forms.BooleanField(required=False)
    appeal_by_fax = forms.BooleanField(required=False)
    appeal_by_email = forms.BooleanField(required=False)
    appeal_contact = forms.CharField(required=True)
    urgent_appeal_contact = forms.CharField(required=True)
    plan_id = forms.CharField(required=True)
    claim_id = forms.CharField(required=True)
    medical_reason = forms.CharField(required=False)
    insurance_company = forms.CharField(required=False)
    plan_type = forms.ModelMultipleChoiceField(queryset=PlanType.objects.all())
    plan_type_text = forms.CharField(required=False)
    denial_date = forms.DateField(required=False)
