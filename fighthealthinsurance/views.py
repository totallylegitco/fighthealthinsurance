from typing import *

import uszipcode
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View

import cv2
import numpy as np
from argon2 import PasswordHasher
from fighthealthinsurance.forms import *
from fighthealthinsurance.models import *
from fighthealthinsurance.process_denial import *
from fighthealthinsurance.utils import *


class IndexView(View):
    def get(self, request):
        return render(
            request,
            'index.html')


class ScanView(View):
    def get(self, request):
        return render(
            request,
            'scrub.html',
            context={
                'ocr_result': '',
                'upload_more': True
            })


class PrivacyPolicyView(View):
    def get(self, request):
        return render(
            request,
            'privacy_policy.html',
            context={
                'title': "Privacy Policy"
            })


class TermsOfServiceView(View):
    def get(self, request):
        return render(
            request,
            'tos.html',
            context={
                'title': "Terms of Service",
            })



class OptOutView(View):
    def get(self, request):
        return render(
            request,
            'opt_out.html',
            context={
                'title': "Opt Out",
            })


class RemoveDataView(View):
    def get(self, request):
        return render(
            request,
            'remove_data.html',
            context={
                'title': "Remove My Data",
            })


class RecommendAppeal(View):
    def post(self, request):
        return render(request, '')


states_with_caps = {
    "AR", "CA", "CT", "DE", "DC", "GA",
    "IL", "IA", "KS", "KY", "ME", "MD",
    "MA", "MI", "MS", "MO", "MT", "NV",
    "NH", "NJ", "NM", "NY", "NC", "MP",
    "OK", "OR", "PA", "RI", "TN", "TX",
    "VT", "VI", "WV"}

class FindNextSteps(View):
    def post(self, request):
        form = DenialForm(request.POST)
        if form.is_valid():
            ph = PasswordHasher()
            email = form.cleaned_data['email']
            hashed_email = ph.hash(email)
            denial = Denials.objects.filter(
                denial_id=form.cleaned_data["denial_id"],
                hashed_email=hashed_email).get()

            outside_help_details = ""
            state = form.cleaned_data["your_state"]
            if state in sates_with_caps:
                outside_help_details += (
                    "<a href='https://www.cms.gov/CCIIO/Resources/Consumer-Assistance-Grants/" +
                    state +
                    "'>" +
                    f"Your state {state} participates in a" +
                    f"Consumer Assistance Program(CAP), and you may be able to get help " +
                    f"through them.</a>")
            if denial.regulator == Regulators.objects.filter(alt_name=="ERISA").get():
                outside_help_details = (
                    "Your plan looks to be an ERISA plan which means your employer <i>may</i>" +
                    " have more input into plan decisions. If your are on good terms with HR " +
                    " it could be worth it to ask them for advice.")
            denial.insurance_company = form.cleaned_data["insurance_company"]
            denial.plan_id = form.cleaned_data["plan_id"]
            denial.claim_id = form.cleaned_data["claim_id"]
            denial.pre_service = form.cleaned_data["pre_service"]
            denial.plan_type = form.cleaned_data["plan_type"]
            denial.plan_type_text = form.cleaned_data["plan_type_text"]
            denial.denial_type_text = form.cleaned_data["denail_type_text"]
            denial.denial_type = form.cleaned_data["denail_type"]
            denial.state = form.cleaned_data["your_state"]
            denial.save()
            advice = []
            question_forms = {}
            for dt in denial.denial_type:
                if dt == medically_necessary:
                    question_forms += MedicalNeccessaryQuestions
                if dt.parent == medically_necessary:
                    question_forms += MedicalNeccessaryQuestions
                if dt == step_therapy:
                    question_forms += StepTherapyQuestions
                if dt == provider_bill:
                    question_forms += BalanceBillQuestions
            return render(
                request,
                'outside_help.html',
                context={
                    "forms": forms
                })
        else:
            # If not valid take the user back.
            return render(
                request,
                'categorize.html',
                context = {
                    'post_infered_form': form,
                    'upload_more': True,
                })
    
class OCRView(View):
    def __init__(self):
        from doctr.models import ocr_predictor
        self.model = ocr_predictor(
            det_arch='db_resnet50', reco_arch='crnn_vgg16_bn', pretrained=True)

    def get(self, request):
        return render(
            request,
            'server_side_ocr.html')

    def post(self, request):
        from doctr.io import DocumentFile
        txt = ""
        print(request.FILES)
        files = dict(request.FILES.lists())
        uploader = files['uploader']
        np_files = list(map(
            lambda x: np.frombuffer(x.read(), dtype=np.uint8),
            uploader))
        imgs = list(map(
            lambda npa: cv2.imdecode(npa, cv2.IMREAD_COLOR),
            np_files))
        result = self.model(imgs)
        print(result)
        words = map(
            lambda words: words['value'],
            flat_map(
                lambda lines: lines['words'],
                flat_map(
                    lambda block: block['lines'],
                    flat_map(
                        lambda page: page['blocks'], result.export()['pages']))))
        doc_txt = " ".join(words)
        return render(
            request,
            'scrub.html',
            context={
                'ocr_result': doc_txt,
                'upload_more': False
            })



class ProcessView(View):
    def __init__(self):
        self.regex_denial_processor = ProcessDenialRegex()
        self.codes_denial_processor = ProcessDenialCodes()
        self.regex_src = DataSource.objects.get(name="regex")
        self.codes_src = DataSource.objects.get(name="codes")


    def post(self, request):
        form = DenialForm(request.POST)
        if form.is_valid():
            # It's not a password per-se but we want password like hashing.
            # but we don't support changing the values.
            ph = PasswordHasher()
            email = form.cleaned_data['email']
            hashed_email = ph.hash(email)
            denial_text = form.cleaned_data['denial_text']
            print(denial_text)
            denial = Denial(
                denial_text = denial_text,
                hashed_email = hashed_email)
            denial.save()
            denial_types = self.regex_denial_processor.get_denialtype(denial_text)
            print(f"mmmk {denial_types}")
            denial_type = []
            for dt in denial_types:
                DenialTypesRelation(
                    denial=denial,
                    denial_type=dt,
                    src=self.regex_src).save()
                denial_type.append(dt)
            denial_types = self.codes_denial_processor.get_denialtype(denial_text)
            print(f"mmmk {denial_types}")
            for dt in denial_types:
                DenialTypesRelation(
                    denial=denial,
                    denial_type=dt,
                    src=self.codes_src).save()
                denial_type.append(dt)
            print(f"denial_type {denial_type}")
            form = PostInferedForm(
                initial = {
                    'denial_type': denial_type,
                    'denial_id': denial.denial_id,
                    'email': email,
                })
            return render(
                request,
                'categorize.html',
                context = {
                    'post_infered_form': form,
                    'upload_more': True,
                })
        else:
            return render(
                request,
                'scrub.html',
                context={
                    'error': form.errors,
                    '': request.POST.get('denial_text', ''),
                })
