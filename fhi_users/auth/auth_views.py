from django.shortcuts import render
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse
from django.urls import reverse, reverse_lazy
from django.views import generic, View
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from .auth_utils import combine_domain_and_username
from .auth_forms import LoginForm
import fhi_users
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.template.loader import render_to_string
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import get_object_or_404
from django.conf import settings
import json
from fhi_users.models import UserDomain
from fhi_users.emails import send_verification_email

from typing import Any

User = get_user_model()


class LoginView(generic.FormView):
    template_name = "login.html"
    form_class = LoginForm

    def form_valid(self, form):
        context: dict[str, Any] = {}
        raw_username = form.cleaned_data["username"]
        request = self.request
        domain = form.cleaned_data["domain"]
        phone = form.cleaned_data["phone"]
        try:
            if domain:
                username = combine_domain_and_username(raw_username, domain)
            elif phone:
                user_domain = UserDomain.objects.get(visible_phone_number=phone)
                username = combine_domain_and_username(raw_username, user_domain.name)
            else:
                context["invalid"] = True
                context["error_message"] = "One of domain or phone is required." # TODO: Expose in template
                return render(request, "login.html", context)
        except UserDomain.DoesNotExist:
            context["domain_invalid"] = True
            return render(request, "login.html", context)
        password = form.cleaned_data["password"]
        user = authenticate(username=username, password=password)
        if user:
            from mfa.helpers import has_mfa

            res = has_mfa(
                username=username, request=request
            )  # has_mfa returns false or HttpResponseRedirect
            if res:
                return res
            return create_session(request, user.username)
        context["invalid"] = True
        return render(request, "login.html", context)


def create_session(request, username):
    user = User.objects.get(username=username)
    login(request, user)
    return HttpResponseRedirect(reverse("root"))


class LogoutView(generic.TemplateView):
    template_name = "logout.html"

    def get(self, request, *args, **kwargs):
        logout(request)
        response = super().get(request, *args, **kwargs)
        return response

class VerifyEmailView(View):
    def get(self, request, uidb64, token):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except(TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        if user is not None and default_token_generator.check_token(user, token):
            user.is_active = True
            user.extrauserproperties.email_verified = True
            user.save()
            return HttpResponseRedirect(reverse_lazy('login'))
        else:
            return HttpResponse('Activation link is invalid!')
