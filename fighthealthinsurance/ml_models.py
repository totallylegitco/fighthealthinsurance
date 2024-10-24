import concurrent
import csv
import itertools
import os
import re
import time
import traceback
from abc import ABC, abstractmethod
from concurrent.futures import Future
from functools import cache, lru_cache
from stopit import ThreadingTimeout as Timeout
from typing import Any, Callable, Iterable, List, Optional, Tuple, Union

import icd10
import requests
from typing_extensions import reveal_type

from fighthealthinsurance.exec import *
from fighthealthinsurance.models import (
    AppealTemplates,
    DenialTypes,
    Diagnosis,
    PlanType,
    Procedures,
    Regulator,
)


class RemoteModel(object):
    """
    For models which produce a "full" appeal tag them with "full"
    For medical reason (e.g. ones where we hybrid with our "expert system"
    ) tag them with "medically_necessary".
    """

    def infer(self, prompt, patient_context, plan_context, infer_type):
        pass


class PalmAPI(RemoteModel):
    def bad_result(self, result) -> bool:
        return result is not None

    @cache
    def infer(
        self, prompt: str, patient_context, plan_context, infer_type: str
    ) -> List[Tuple[str, str]]:
        result = self._infer(prompt)
        if self.bad_result(result):
            result = self._infer(prompt)
        if result is not None:
            return [(infer_type, result)]
        else:
            return []

    def get_procedure_and_diagnosis(self, prompt):
        return (None, None)

    def _infer(self, prompt) -> Optional[str]:
        API_KEY = os.getenv("PALM_KEY")
        if API_KEY is None:
            return None
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={API_KEY}"
        try:
            s = requests.Session()
            result = s.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
            json_result = result.json()
            candidates = json_result["candidates"]
            return candidates[0]["content"]["parts"][0]["text"]
        except Exception as e:
            return None


class RemoteOpenLike(RemoteModel):

    _expensive = False

    def __init__(
        self,
        api_base,
        token,
        model,
        system_prompts,
        backup_model=None,
        backup_api_base=None,
        expensive=False,
    ):
        self.api_base = api_base
        self.token = token
        self.model = model
        self.system_prompts = system_prompts
        self.max_len = 4096 * 8
        self._timeout = 90
        self.procedure_response_regex = re.compile(
            r"\s*procedure\s*:?\s*", re.IGNORECASE
        )
        self.diagnosis_response_regex = re.compile(
            r"\s*diagnosis\s*:?\s*", re.IGNORECASE
        )
        self.backup_model = backup_model
        self.backup_api_base = backup_api_base
        self._expensive = expensive

    def bad_result(self, result: Optional[str]) -> bool:
        bad_ideas = [
            "Therefore, the Health Plans denial should be overturned.",
            "I am writing on behalf of",
        ]
        if result is None:
            return True
        for bad in bad_ideas:
            if bad in result:
                return True
        if len(result.strip(" ")) < 5:
            return True
        return False

    def tla_fixer(self, result: Optional[str]) -> Optional[str]:
        """Fix incorrectly picked TLAs from the LLM."""
        if result is None:
            return None
        else:
            m = re.search(
                "([A-Z])\\w+ ([A-Z])\\w+ ([A-Z])\\w+ \\(([A-Z]{3})\\)", result
            )
            if m is not None:
                tla = m.group(1) + m.group(2) + m.group(3)
                if tla != m.group(4):
                    return re.sub(f"(?<=[\\.\\( ]){m.group(4)}", tla, result)
            return result

    common_bad_result = [
        "The page you are trying to reach is not available. Please check the URL and try again.",
        "The requested article is not currently available on this site.",
    ]

    maybe_bad_url_endings = re.compile("^(.*)[\\.\\:\\;\\,\\?\\>]+$")

    def is_valid_url(self, url):
        try:
            result = requests.get(url)
            if result.status_code != 200:
                groups = self.maybe_bad_url_endings.search(url)
                if groups is not None:
                    return self.is_valid_url(groups.group(1))
                else:
                    return False
            if result.status_code == 200 and ".pdf" not in url:
                result_text = result.text.lower()
                for bad_result_text in self.common_bad_result:
                    if bad_result_text.lower() in result_text:
                        raise Exception(f"Found {bad_result_text} in {result_text}")
                    return True
        except Exception as e:
            groups = self.maybe_bad_url_endings.search(url)
            if groups is not None:
                return self.is_valid_url(groups.group(1))
            else:
                return False

    def url_fixer(self, result: Optional[str]) -> Optional[str]:
        """LLMs like to hallucinate URLs drop them if they are not valid"""
        if result is None:
            return None
        else:
            urls = re.findall(r"(https?://\S+)", result)
            for u in urls:
                if not self.is_valid_url(u):
                    result = result.replace(u, "")
            return result

    def note_remover(self, result: Optional[str]) -> Optional[str]:
        """Remove the last line note because we'll put similar content up earlier anyways"""
        if result is None:
            return None
        else:
            return re.sub(r"\n\s*\**\s*Note.*\Z", "", result)

    def parallel_infer(
        self,
        prompt: str,
        patient_context: Optional[str],
        plan_context: Optional[str],
        infer_type: str,
    ) -> List[Future[Tuple[str, Optional[str]]]]:
        print(f"Running inference on {self} of type {infer_type}")
        temperatures = [0.5]
        if infer_type == "full" and not self._expensive:
            # Special case for the full one where we really want to explore the problem space
            temperatures = [0.6, 0.1]
        calls = itertools.chain.from_iterable(
            map(
                lambda temperature: map(
                    lambda system_prompt: (
                        self._checked_infer,
                        {
                            "prompt": prompt,
                            "patient_context": patient_context,
                            "plan_context": plan_context,
                            "infer_type": infer_type,
                            "system_prompt": system_prompt,
                            "temperature": temperature,
                        },
                    ),
                    self.system_prompts[infer_type],
                ),
                temperatures,
            )
        )  # type: Iterable[Tuple[Callable[..., Tuple[str, Optional[str]]], dict[str, Union[Optional[str], float]]]]
        futures = list(map(lambda x: executor.submit(x[0], **x[1]), calls))
        return futures

    @cache
    def _checked_infer(
        self,
        prompt: str,
        patient_context,
        plan_context,
        infer_type,
        system_prompt: str,
        temperature: float,
    ):
        result = self._infer(
            prompt=prompt,
            patient_context=patient_context,
            plan_context=plan_context,
            system_prompt=system_prompt,
            temperature=temperature,
        )
        print(f"Got result {result} from {prompt} on {self}")
        # One retry
        if self.bad_result(result):
            result = self._infer(
                prompt=prompt,
                patient_context=patient_context,
                plan_context=plan_context,
                system_prompt=system_prompt,
                temperature=temperature,
            )
        if self.bad_result(result):
            return []
        return [(infer_type, self.note_remover(self.url_fixer(self.tla_fixer(result))))]

    def _clean_procedure_response(self, response):
        return self.procedure_response_regex.sub("", response)

    def _clean_diagnosis_response(self, response):
        if (
            "Not available in" in response
            or "Not provided" in response
            or "Not specified" in response
            or "Not Applicable" in response
        ):
            return None
        return self.diagnosis_response_regex.sub("", response)

    @cache
    def questions(self, prompt: str, patient_context: str, plan_context) -> List[str]:
        result = self._infer(
            system_prompt=self.system_prompts["questions"],
            prompt=prompt,
            patient_context=patient_context,
            plan_context=plan_context,
        )
        if result is None:
            return []
        else:
            return result.split("\n")

    @cache
    def get_procedure_and_diagnosis(
        self, prompt: str
    ) -> tuple[Optional[str], Optional[str]]:
        print(f"Getting procedure and diagnosis for {self} w/ {prompt}")
        if self.system_prompts["procedure"] is None:
            print(f"No procedure message for {self.model} skipping")
            return (None, None)
        model_response = self._infer(
            system_prompt=self.system_prompts["procedure"], prompt=prompt
        )
        if model_response is None or "Diagnosis" not in model_response:
            print("Retrying query.")
            model_response = self._infer(
                system_prompt=self.system_prompts["procedure"], prompt=prompt
            )
        if model_response is not None:
            responses: list[str] = model_response.split("\n")
            if len(responses) == 2:
                r = (
                    self._clean_procedure_response(responses[0]),
                    self._clean_diagnosis_response(responses[1]),
                )
                return r
            elif len(responses) == 1:
                r = (self._clean_procedure_response(responses[0]), None)
                return r
            elif len(responses) > 2:
                procedure = None
                diagnosis = None
                for ra in responses:
                    if "Diagnosis" in ra:
                        diagnosis = self._clean_diagnosis_response(ra)
                    if "Procedure" in ra:
                        procedure = self._clean_procedure_response(ra)
                return (procedure, diagnosis)
            else:
                print(
                    f"Non-understood response {model_response} for procedure/diagnsosis."
                )
        else:
            print(f"No model response for {self.model}")
        return (None, None)

    def _infer(
        self,
        system_prompt,
        prompt,
        patient_context=None,
        plan_context=None,
        temperature=0.7,
    ) -> Optional[str]:
        r = self.__timeout_infer(
            system_prompt=system_prompt,
            prompt=prompt,
            patient_context=patient_context,
            plan_context=plan_context,
            temperature=temperature,
            model=self.model,
        )
        if r is None and self.backup_model is not None:
            r = self.__timeout_infer(
                system_prompt=system_prompt,
                prompt=prompt,
                patient_context=patient_context,
                plan_context=plan_context,
                temperature=temperature,
                model=self.backup_model,
            )
        else:
            return r
        if r is None and self.backup_api_base is not None:
            r = self.__timeout_infer(
                system_prompt=system_prompt,
                prompt=prompt,
                patient_context=patient_context,
                plan_context=plan_context,
                temperature=temperature,
                model=self.model,
                api_base=self.backup_api_base,
            )
        else:
            return r
        if (
            r is None
            and self.backup_api_base is not None
            and self.backup_model is not None
        ):
            r = self.__timeout_infer(
                system_prompt=system_prompt,
                prompt=prompt,
                patient_context=patient_context,
                plan_context=plan_context,
                temperature=temperature,
                model=self.backup_model,
                api_base=self.backup_api_base,
            )
        else:
            print(f"Skipping fall through")
        return r

    def __timeout_infer(
        self,
        *args,
        **kwargs,
    ) -> Optional[str]:
        if self._timeout is not None:
            with Timeout(self._timeout) as timeout_ctx:
                return self.__infer(*args, **kwargs)
        else:
            return self.__infer(*args, **kwargs)

    def __infer(
        self,
        system_prompt,
        prompt,
        patient_context,
        plan_context,
        temperature,
        model,
        api_base=None,
    ) -> Optional[str]:
        if api_base is None:
            api_base = self.api_base
        print(f"Looking up model {model} using {api_base} and {prompt}")
        if self.api_base is None:
            return None
        if self.token is None:
            print(f"Error no Token provided for {model}.")
        if prompt is None:
            print(f"Error: must supply a prompt.")
            return None
        url = f"{api_base}/chat/completions"
        combined_content = None
        try:
            s = requests.Session()
            # Combine the message, Mistral's VLLM container does not like the system role anymore?
            # despite it still being fine-tuned with the system role.
            context_extra = ""
            if patient_context is not None and len(patient_context) > 3:
                patient_context_max = int(self.max_len / 2)
                max_len = self.max_len - min(len(patient_context), patient_context_max)
                context_extra = f"When answering the following question you can use the patient context {patient_context[0:patient_context_max]}."
            if plan_context is not None and len(plan_context) > 3:
                context_extra += f"For answering the question you can use this context about the plan {plan_context}"
            combined_content = f"<<SYS>>{system_prompt}<</SYS>>{context_extra}{prompt[0 : self.max_len]}"
            print(f"Using {combined_content}")
            result = s.post(
                url,
                headers={"Authorization": f"Bearer {self.token}"},
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": combined_content,
                        },
                    ],
                    "temperature": temperature,
                },
            )
            json_result = result.json()
            if "object" in json_result and json_result["object"] != "error":
                print(f"Response on {self} Looks ok")
            else:
                print(f"***WARNING*** Response {result} on {self} looks _bad_")
        except Exception as e:
            print(f"Error {e} {traceback.format_exc()} calling {api_base}")
            return None
        try:
            r = json_result["choices"][0]["message"]["content"]
            print(f"Got {r} from {model} w/ {api_base} {self}")
            return r
        except Exception as e:
            print(
                f"Error {e} {traceback.format_exc()} processing {json_result} from {api_base} w/ url {url} --  {self} ON -- {combined_content}"
            )
            return None


class RemoteFullOpenLike(RemoteOpenLike):
    def __init__(
        self,
        api_base,
        token,
        model,
        backup_model=None,
        expensive=False,
        backup_api_base=None,
    ):
        systems = {
            "full": [
                """You possess extensive medical expertise and enjoy crafting appeals for health insurance denials as a personal interest. As a patient, not a doctor, you advocate for yourself. Don't assume you have any letter from a physician. Your writing style is direct, akin to patio11 or a bureaucrat, and maintains a professional tone without expressing frustration towards insurance companies. You may consider emphasizing the unique and potentially essential nature of the medical intervention, using "YourNameMagic" as your name, "SCSID" for the subscriber ID, and "GPID" as the group ID. Make sure to write in the form of a letter. Ideally use the communication the style of patio11 / a being a Dangerous Professional means communicating in what might be a slightly adversarial context in a way which suggests that a bureaucracy take one's concerns seriously and escalate them to someone empowered to resolve them swiftly. You can be verbose. Start your response with Dear [Insurance Company];""",
                """You possess extensive medical expertise and enjoy crafting appeals for health insurance denials as a personal interest. As a patient, not a doctor, you advocate for yourself. Don't assume you have any letter from a physician unless absolutely necessary. Your writing style is direct, akin to patio11 or a bureaucrat, and maintains a professional tone without expressing frustration towards insurance companies. You may consider emphasizing the unique and potentially essential nature of the medical intervention, using "YourNameMagic" as your name, "SCSID" for the subscriber ID, and "GPID" as the group ID. Make sure to write in the form of a letter. Do not use the 3rd person when refering to the patient, instead use the first persion (I, my, etc.). You are not a review and should not mention any.""",
            ],
            "procedure": [
                """You must be concise. You have an in-depth understanding of insurance and have gained extensive experience working in a medical office. Your expertise lies in deciphering health insurance denial letters to identify the requested procedure and, if available, the associated diagnosis. Each word costs an extra dollar. Provide a concise response with the procedure on one line starting with "Procedure" and Diagnsosis on another line starting with Diagnosis. Do not say not specified. Diagnosis can also be reason for treatment even if it's not a disease (like high risk homosexual behaviour for prep or preventitive and the name of the diagnosis). Remember each result on a seperated line."""
            ],
            "questions": [
                """Given the appeal and the context what questions should we ask the user to provide context to help generate their appeal? Put each question on a new line."""
            ],
            "medically_necessary": [
                """You have an in-depth understanding of insurance and have gained extensive experience working in a medical office. Your expertise lies in deciphering health insurance denial letters. Each word costs an extra dollar. Please provide a concise response. Do not use the 3rd person when refering to the patient (e.g. don't say "the patient", "patient's", "his", "hers"), instead use the first persion (I, my, mine,etc.) when talking about the patient. You are not a review and should not mention any. Write concisely in a professional tone akin to patio11. Do not say this is why the decission should be overturned. Just say why you believe it is medically necessary (e.g. to prevent X or to treat Y)."""
            ],
            "generic": [
                """You have an in-depth understanding of insurance and have gained extensive experience working in a medical office. Your expertise lies in deciphering health insurance denial letters. Help a patient answer the provided question for their insurance appeal."""
            ],
        }
        return super().__init__(
            api_base,
            token,
            model,
            systems,
            backup_model=backup_model,
            expensive=expensive,
            backup_api_base=backup_api_base,
        )

    def model_type(self) -> str:
        return "full"


class RemoteHealthInsurance(RemoteFullOpenLike):
    def __init__(self):
        self.port = os.getenv("HEALTH_BACKEND_PORT", "80")
        self.host = os.getenv("HEALTH_BACKEND_HOST")
        self.backup_port = os.getenv("HEALTH_BACKUP_BACKEND_PORT", self.port)
        self.backup_host = os.getenv("HEALTH_BACKUP_BACKEND_HOST", self.host)
        self.url = None
        if self.port is not None and self.host is not None:
            self.url = f"http://{self.host}:{self.port}/v1"
        else:
            print(f"Error setting up remote health {self.host}:{self.port}")
        self.backup_url = f"http://{self.backup_host}:{self.backup_port}/v1"
        print(f"Setting backup to {self.backup_url}")
        self.model = os.getenv(
            "HEALTH_BACKEND_MODEL", "TotallyLegitCo/fighthealthinsurance_model_v0.5"
        )
        self.backup_model = os.getenv("HEALTH_BACKUP_BACKEND_MODEL", self.model)
        super().__init__(
            self.url,
            token="",
            model=self.model,
            backup_model=self.backup_model,
            backup_api_base=self.backup_url,
        )


class OctoAI(RemoteFullOpenLike):
    """Use RemotePerplexity for denial magic calls a service"""

    def __init__(self):
        api_base = "https://text.octoai.run/v1/"
        token = os.getenv("OCTOAI_TOKEN")
        model = "meta-llama-3.1-405b-instruct"
        self._expensive = True
        super().__init__(api_base, token, model, expensive=True)


class RemoteTogetherAI(RemoteFullOpenLike):
    """Use RemotePerplexity for denial magic calls a service"""

    def __init__(self):
        api_base = "https://api.together.xyz"
        token = os.getenv("TOGETHER_KEY")
        model = "meta-llama/Llama-3.2-90B-Vision-Instruct-Turbo"
        super().__init__(api_base, token, model)


class RemotePerplexityInstruct(RemoteFullOpenLike):
    """Use RemotePerplexity for denial magic calls a service"""

    def __init__(self):
        api_base = "https://api.perplexity.ai"
        token = os.getenv("PERPLEXITY_API")
        model = "llama-3.1-sonar-huge-128k-online"
        super().__init__(api_base, token, model)


class RemotePerplexityMedReason(RemoteOpenLike):
    """Use RemotePerplexity for denial magic calls a service"""

    def __init__(self):
        api_base = "https://api.perplexity.ai"
        token = os.getenv("PERPLEXITY_API")
        model = "mistral-7b-instruct"
        medical_reason_message = "You are a doctor answering a friends question as to why a procedure is medically necessary."
        super().__init__(api_base, token, model, medical_reason_message)


class RemoteOpen(RemoteFullOpenLike):
    """Use RemoteOpen for denial magic calls a service"""

    def __init__(self):
        api_base = os.getenv("OPENAI_API_BASE")
        token = os.getenv("OPENAI_API_KEY")
        model = "HuggingFaceH4/zephyr-7b-beta"
        super().__init__(api_base, token, model)


class RemoteOpenInst(RemoteFullOpenLike):
    """Use RemoteOpen for denial magic calls a service"""

    def __init__(self):
        api_base = os.getenv("OPENAI_API_BASE")
        token = os.getenv("OPENAI_API_KEY")
        model = "mistralai/Mistral-7B-Instruct-v0.1"
        super().__init__(api_base, token, model)
