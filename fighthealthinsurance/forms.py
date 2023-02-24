from django import forms

class DenialForm(forms.Form):
    zip = forms.BooleanField(required=False)
    pii = forms.BooleanField(required=True)
    privacy = forms.BooleanField(required=True)
    store_raw_email = forms.BooleanField(required=False)
    denial_text = forms.CharField(required=True)
    email = forms.EmailField(required=True)
