from django.contrib.auth.forms import AuthenticationForm
from django import forms


class DomainAuthenticationForm(AuthenticationForm):
    domain = forms.CharField(required=True)
