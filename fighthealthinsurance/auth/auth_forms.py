from django import forms


class DomainAuthenticationForm(forms.Form):
    username = forms.CharField(required=True)
    password = forms.CharField(required=True)
    domain = forms.CharField(required=True)
