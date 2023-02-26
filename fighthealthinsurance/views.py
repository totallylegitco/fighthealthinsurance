from typing import *

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
from fighthealthinsurance.forms import DenialForm
from fighthealthinsurance.models import *
from fighthealthinsurance.utils import *
from fighthealthinsurance.process_denial import ProcessDenialRegex


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
        self.regex_src = DataSource.objects.get(name="regex")


    def post(self, request):
        form = DenialForm(request.POST)
        if form.is_valid():
            # It's not a password per-se but we want password like hashing.
            # but we don't support changing the values.
            ph = PasswordHasher()
            email = form.cleaned_data['email']
            hashed_email = ph.hash(email)
            denial_text = form.cleaned_data['denial_text']
            denial = Denial(
                denial_text = denial_text,
                hashed_email = hashed_email)
            denial.save()
            denial_types = self.regex_denial_processor.get_denialtype(denial_text)
            for dt in denial_types:
                DenialTypesRelation(
                    denial=denial,
                    denial_type=dt,
                    src=self.regex_src).save()
            form = PostInferedForm(
                initial = {
                    'denial_type': denial_type
                })
            return render(
                request,
                'categorize.html',
                context = {
                    'post_infered_from': form,
                    'upload_more': True,
                })
        else:
            return render(
                request,
                'image_recognize.html',
                context={
                    'error': form.errors
                })
