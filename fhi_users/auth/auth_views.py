from django.shortcuts import render
from django.http import HttpResponseRedirect, JsonResponse, HttpResponse
from django.urls import reverse, reverse_lazy
from django.views import generic, View
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from .auth_utils import combine_domain_and_username
from .auth_forms import DomainAuthenticationForm
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

User = get_user_model()


class LoginView(generic.FormView):
    template_name = "login.html"
    form_class = DomainAuthenticationForm

    def form_valid(self, form):
        context = {}
        raw_username = form.cleaned_data["username"]
        request = self.request
        domain = form.cleaned_data["domain"]
        phone = form.cleaned_data["phone"]
        try:
            if domain:
                username = combine_domain_and_username(raw_username, domain)
            else:
                user_domain = UserDomain.objects.get(visible_phone_number=phone)  # Corrected field name
                username = combine_domain_and_username(raw_username, user_domain.name)
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


@csrf_exempt
def rest_login_view(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        user = authenticate(username=username, password=password)
        if user:
            login(request, user)
            return JsonResponse({'status': 'success'})
        return JsonResponse({'status': 'failure'}, status=400)

@csrf_exempt
def create_user_view(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')
        user = User.objects.create_user(username=username, password=password, email=email)
        user.is_active = False
        user.save()
        send_verification_email(request, user)
        return JsonResponse({'status': 'pending'})

def send_verification_email(request, user):
    current_site = get_current_site(request)
    mail_subject = 'Activate your account.'
    message = render_to_string('acc_active_email.html', {
        'user': user,
        'domain': current_site.domain,
        'uid': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': default_token_generator.make_token(user),
    })
    to_email = user.email
    send_mail(mail_subject, message, settings.EMAIL_HOST_USER, [to_email])

class VerifyEmailView(View):
    def get(self, request, uidb64, token):
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except(TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        if user is not None and default_token_generator.check_token(user, token):
            user.is_active = True
            user.userextraproperties.email_verified = True  # Corrected attribute name
            user.save()
            return HttpResponseRedirect(reverse_lazy('login'))
        else:
            return HttpResponse('Activation link is invalid!')
