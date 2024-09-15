import asyncio
import concurrent
import os
from io import BytesIO
from string import Template
from typing import *
from django.conf import settings

import time

import itertools

from asgiref.sync import async_to_sync
import json
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import StreamingHttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views import generic
from django.views.decorators.cache import cache_control


import numpy as np
import uszipcode
from fighthealthinsurance.forms import *
from fighthealthinsurance.models import *
from fighthealthinsurance.generate_appeal import *
from fighthealthinsurance.utils import *
from fighthealthinsurance.common_view_logic import *

appealGenerator = AppealGenerator()


class IndexView(generic.TemplateView):
    template_name = "index.html"


class AboutView(generic.TemplateView):
    template_name = "about_us.html"


class OtherResourcesView(generic.TemplateView):
    template_name = "other_resources.html"


class ScanView(generic.TemplateView):
    template_name = "scrub.html"

    def get_context_data(self, **kwargs):
        return {"ocr_result": "", "upload_more": True}


class PrivacyPolicyView(generic.TemplateView):
    template_name = "privacy_policy.html"

    def get_context_data(self, **kwargs):
        return {"title": "Privacy Policy"}


class TermsOfServiceView(generic.TemplateView):
    template_name = "tos.html"

    def get_context_data(self, **kwargs):
        return {"title": "Terms of Service"}


class ContactView(generic.TemplateView):
    template_name = "contact.html"

    def get_context_data(self, **kwargs):
        return {"title": "Contact Us"}


class ErrorView(View):
    def get(self, request):
        raise Exception("test")


class ShareDenialView(View):
    def get(self, request):
        return render(request, "share_denial.html", context={"title": "Share Denial"})

    def post(self, request):
        form = ShareDenailForm(request.POST)


class ShareAppealView(View):
    def get(self, request):
        return render(request, "share_appeal.html", context={"title": "Share Appeal"})

    def post(self, request):
        form = ShareAppealForm(request.POST)
        if form.is_valid():
            denial_id = form.cleaned_data["denial_id"]
            hashed_email = Denial.get_hashed_email(form.cleaned_data["email"])

            # Update the denial
            denial = Denial.objects.filter(
                denial_id=denial_id,
                # Include the hashed e-mail so folks can't brute force denial_id
                hashed_email=hashed_email,
            ).get()
            print(form.cleaned_data)
            denial.appeal = form.cleaned_data["appeal_text"]
            denial.save()
            pa = ProposedAppeal(
                appeal_text=form.cleaned_data["appeal_text"],
                for_denial=denial,
                chosen=True,
                editted=True,
            )
            pa.save()
            return render(request, "thankyou.html")


class RemoveDataView(View):
    def get(self, request):
        return render(
            request,
            "remove_data.html",
            context={
                "title": "Remove My Data",
                "form": DeleteDataForm(),
            },
        )

    def post(self, request):
        form = DeleteDataForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            RemoveDataHelper.remove_data_for_email(email)
            return render(
                request,
                "removed_data.html",
                context={
                    "title": "Remove My Data",
                },
            )
        else:
            return render(
                request,
                "remove_data.html",
                context={
                    "title": "Remove My Data",
                    "form": form,
                },
            )


class RecommendAppeal(View):
    def post(self, request):
        return render(request, "")


class FindNextSteps(View):
    def post(self, request):
        form = PostInferedForm(request.POST)
        if form.is_valid():
            denial_id = form.cleaned_data["denial_id"]
            email = form.cleaned_data["email"]

            next_step_info = FindNextStepsHelper.find_next_steps(**form.cleaned_data)
            denial_ref_form = DenialRefForm(
                initial={
                    "denial_id": denial_id,
                    "email": email,
                    "semi_sekret": next_step_info.semi_sekret,
                }
            )
            return render(
                request,
                "outside_help.html",
                context={
                    "outside_help_details": next_step_info.outside_help_details,
                    "combined": next_step_info.combined_form,
                    "denial_form": denial_ref_form,
                },
            )
        else:
            # If not valid take the user back.
            return render(
                request,
                "categorize.html",
                context={
                    "post_infered_form": form,
                    "upload_more": True,
                },
            )


class ChooseAppeal(View):
    def post(self, request):
        form = ChooseAppealForm(request.POST)
        if form.is_valid():
            denial_id = form.cleaned_data["denial_id"]
            hashed_email = Denial.get_hashed_email(form.cleaned_data["email"])
            appeal_text = form.cleaned_data["appeal_text"]
            email = form.cleaned_data["email"]

            # Get the current info
            denial = Denial.objects.filter(
                denial_id=denial_id, hashed_email=hashed_email
            ).get()
            denial.appeal_text = appeal_text
            denial.save()
            return render(
                request,
                "appeal.html",
                context={
                    "appeal": appeal_text,
                    "user_email": email,
                    "denial_id": denial_id,
                },
            )
            pa = ProposedAppeal(appeal_text=appeal_text, for_denial=denial, chosen=True)
            pa.save()
        else:
            print(form)
            pass


class GenerateAppeal(View):
    def post(self, request):
        form = DenialRefForm(request.POST)
        if form.is_valid():
            denial_id = form.cleaned_data["denial_id"]
            hashed_email = Denial.get_hashed_email(form.cleaned_data["email"])
            elems = dict(request.POST)
            # Query dict is of lists
            elems = dict((k, v[0]) for k, v in elems.items())
            del elems["csrfmiddlewaretoken"]
            return render(
                request,
                "appeals.html",
                context={
                    "form_context": json.dumps(elems),
                    "user_email": form.cleaned_data["email"],
                    "denial_id": form.cleaned_data["denial_id"],
                    "semi_sekret": form.cleaned_data["semi_sekret"],
                },
            )
        else:
            # TODO: Send user back to fix the form.
            pass


class AppealsBackend(View):
    """Streaming back the appeals as json :D"""

    def __init__(self):
        self.regex_denial_processor = ProcessDenialRegex()

    def post(self, request):
        print(request)
        print(request.POST)
        form = DenialRefForm(request.POST)
        return self.handle_for_form(request, form)

    def get(self, request):
        form = DenialRefForm(request.GET)
        return self.handle_for_form(request, form)

    def handle_for_form(self, request, form):
        if form.is_valid():
            denial_id = form.cleaned_data["denial_id"]
            hashed_email = Denial.get_hashed_email(form.cleaned_data["email"])

            # Get the current info
            denial = Denial.objects.filter(
                denial_id=denial_id, hashed_email=hashed_email
            ).get()

            non_ai_appeals = list(
                map(
                    lambda t: t.appeal_text,
                    self.regex_denial_processor.get_appeal_templates(
                        denial.denial_text, denial.diagnosis
                    ),
                )
            )

            insurance_company = denial.insurance_company or "insurance company;"
            claim_id = denial.claim_id or "YOURCLAIMIDGOESHERE"
            prefaces = []
            main = []
            footer = []
            medical_reasons = []
            medical_context = ""
            # Extract any medical context AND
            # Apply all of our 'expert system'
            # (aka six regexes in a trench coat hiding behind a database).
            for dt in denial.denial_type.all():
                form = dt.get_form()
                if form is not None:
                    parsed = form(request.POST)
                    if parsed.is_valid():
                        # Check and see if the form has a context method
                        op = getattr(parsed, "medical_context", None)
                        if op is not None and callable(op):
                            try:
                                medical_context += parsed.medical_context()
                            except Exception as e:
                                print(
                                    f"Error {e} processing form {form} for medical context"
                                )
                        print(parsed.cleaned_data)
                        print(request.POST)
                        if (
                            "medical_reason" in parsed.cleaned_data
                            and parsed.cleaned_data["medical_reason"] != ""
                        ):
                            medical_reasons.append(
                                parsed.cleaned_data["medical_reason"]
                            )
                            print(f"Med reason {medical_reasons}")

                        new_prefaces = parsed.preface()
                        for p in new_prefaces:
                            if p not in prefaces:
                                prefaces.append(p)
                        new_main = parsed.main()
                        for m in new_main:
                            if m not in main:
                                main.append(m)
                        new_footer = parsed.footer()
                        for f in new_footer:
                            if f not in footer:
                                footer.append(f)
                else:
                    if dt.appeal_text is not None:
                        main.append(dt.appeal_text)

            # Add the context to the denial
            denial.qa_context = medical_context
            denial.save()
            appeals = itertools.chain(
                non_ai_appeals,
                appealGenerator.make_appeals(
                    denial,
                    AppealTemplateGenerator(prefaces, main, footer),
                    medical_context=medical_context,
                    medical_reasons=medical_reasons,
                ),
            )

            def save_appeal(appeal_text):
                # Save all of the proposed appeals, so we can use RL later.
                t = time.time()
                print(f"{t}: Saving {appeal_text}")
                pa = ProposedAppeal(appeal_text=appeal_text, for_denial=denial)
                pa.save()
                return appeal_text

            def sub_in_appeals(appeal: str) -> str:
                print(f"Processing {appeal}")
                s = Template(appeal)
                ret = s.safe_substitute(
                    {
                        "insurance_company": denial.insurance_company
                        or "{insurance_company}",
                        "[Insurance Company Name]": denial.insurance_company
                        or "{insurance_company}",
                        "[Insert Date]": denial.date or "{date}",
                        "[Reference Number from Denial Letter]": denial.claim_id
                        or "{claim_id}",
                        "[Claim ID]": denial.claim_id or "{claim_id}",
                        "{claim_id}": denial.claim_id or "{claim_id}",
                        "[Diagnosis]": denial.diagnosis or "{diagnosis}",
                        "[Procedure]": denial.procedure or "{procedure}",
                        "{diagnosis}": denial.diagnosis or "{diagnosis}",
                        "{procedure}": denial.procedure or "{procedure}",
                    }
                )
                return ret

            filtered_appeals = filter(lambda x: x != None, appeals)
            saved_appeals = map(save_appeal, filtered_appeals)
            subbed_appeals = map(sub_in_appeals, saved_appeals)
            subbed_appeals_json = map(lambda e: json.dumps(e) + "\n", subbed_appeals)
            return StreamingHttpResponse(
                subbed_appeals_json, content_type="application/json"
            )
        else:
            print(f"form {combined_form} is not valid")


class OCRView(View):
    def __init__(self):
        # Load easy ocr reader if possible
        try:
            import easyocr

            self._easy_ocr_reader = easyocr.Reader(["en"], gpu=False)
        except:
            pass

    def get(self, request):
        return render(request, "server_side_ocr.html")

    def post(self, request):
        try:
            txt = ""
            print(request.FILES)
            files = dict(request.FILES.lists())
            uploader = files["uploader"]
            doc_txt = self._ocr(uploader)
            return render(
                request,
                "scrub.html",
                context={"ocr_result": doc_txt, "upload_more": False},
            )
        except AttributeError as e:
            error_txt = "Unsupported file type"
            return render(
                request, "server_side_ocr_error.html", context={"error": error_txt}
            )
        except KeyError as e:
            error_txt = "Missing file"
            return render(
                request, "server_side_ocr_error.html", context={"error": error_txt}
            )

    def _ocr(self, uploader):
        from PIL import Image

        def ocr_upload(x):
            try:
                import pytesseract

                img = Image.open(x)
                return pytesseract.image_to_string(img)
            except:
                result = self._easy_ocr_reader.readtext(x.read())
                return " ".join([text for _, text, _ in result])

        texts = map(ocr_upload, uploader)
        return "\n".join(texts)


class ProcessView(generic.FormView):
    template_name = "scrub.html"
    form_class = DenialForm

    def get_ocr_result(self):
        if self.request.method == "POST":
            return self.request.POST.get("denial_text", "")
        return ""

    def get_context_data(self, **kwargs):
        context = {
            "ocr_result": self.get_ocr_result(),
            "upload_more": True,
        }
        return context

    def form_valid(self, form):
        # It's not a password per-se but we want password like hashing.
        # but we don't support changing the values.

        denial_response = DenialCreatorHelper.create_denial(**form.cleaned_data)

        form = PostInferedForm(
            initial={
                "denial_type": denial_response.selected_denial_type,
                "denial_id": denial_response.denial_id,
                "email": form.cleaned_data["email"],
                "your_state": denial_response.your_state,
                "procedure": denial_response.procedure,
                "diagnosis": denial_response.diagnosis,
                "semi_sekret": denial_response.semi_sekret,
            }
        )

        # TODO: This should be a redirect to a new view to prevent
        # double-submission and other potentially unexpected issues. Normally,
        # this can be done by assigning a success_url to the view and Django
        # will take care of the rest. Since we need to pass extra information
        # along, we can use get_success_url to generate a querystring.
        return render(
            self.request,
            "categorize.html",
            context={
                "post_infered_form": form,
                "upload_more": True,
            },
        )
