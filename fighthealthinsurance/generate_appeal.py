import random
import concurrent
import csv
import itertools
import os
import time
import traceback
from concurrent.futures import Future
from functools import cache, lru_cache
from typing import List, Optional, Tuple, Iterator

import icd10
import requests
from typing_extensions import reveal_type

from fighthealthinsurance.exec import *
from fighthealthinsurance.ml_models import *
from fighthealthinsurance.models import (
    AppealTemplates,
    DenialTypes,
    Diagnosis,
    PlanType,
    Procedures,
    Regulator,
)
from fighthealthinsurance.process_denial import *
from fighthealthinsurance.utils import as_available


class AppealTemplateGenerator(object):
    def __init__(self, prefaces, main, footer):
        self.prefaces = prefaces
        self.main = main
        self.footer = footer
        self.combined = str("\n".join(prefaces + main + footer))

    def generate_static(self):
        if "{medical_reason}" not in self.combined and self.combined != "":
            return self.combined
        else:
            return None

    def generate(self, medical_reason):
        result = self.combined.replace("{medical_reason}", medical_reason)
        if result != "":
            return result
        else:
            return None


class AppealGenerator(object):
    def __init__(self):
        self.regex_denial_processor = ProcessDenialRegex()
        self.anyscale = RemoteOpen()
        self.anyscale2 = RemoteOpenInst()
        self.remotehealth = RemoteHealthInsurance()
        self.together = RemoteTogetherAI()
        self.palm = PalmAPI()
        self.octoai = OctoAI()
        self.perplexity = RemotePerplexityInstruct()

    def get_procedure_and_diagnosis(self, denial_text=None, use_external=False):
        prompt = self.make_open_procedure_prompt(denial_text)
        models_to_try = [
            self.regex_denial_processor,
            self.remotehealth,
        ]
        if use_external:
            models_to_try.append(self.together)
        procedure = None
        diagnosis = None
        for model in models_to_try:
            print(f"Exploring model {model}")
            procedure_diagnosis = model.get_procedure_and_diagnosis(denial_text)
            if procedure_diagnosis is not None:
                if len(procedure_diagnosis) > 1:
                    procedure = procedure or procedure_diagnosis[0]
                    diagnosis = diagnosis or procedure_diagnosis[1]
                else:
                    print(
                        f"Unexpected procedure diagnosis len on {procedure_diagnosis}"
                    )
                if procedure is not None and diagnosis is not None:
                    print(f"Return with procedure {procedure} and {diagnosis}")
                    return (procedure, diagnosis)
                else:
                    print(f"So far infered {procedure} and {diagnosis}")
        print(f"Fell through :/ could not fully populate.")
        return (procedure, diagnosis)

    def make_open_procedure_prompt(self, denial_text=None):
        if denial_text is not None:
            return f"What was the procedure/treatment and what is the diagnosis from the following denial (remember to provide two strings seperated by MAGIC as your response): {denial_text}"
        else:
            return None

    def make_open_prompt(
        self,
        denial_text=None,
        procedure=None,
        diagnosis=None,
        is_trans=False,
    ) -> Optional[str]:
        if denial_text is None:
            return None
        base = ""
        if is_trans:
            base = "While answering the question keep in mind the patient is trans."
        start = f"Write a health insurance appeal for the following denial:"
        if (
            procedure is not None
            and procedure != ""
            and diagnosis is not None
            and diagnosis != ""
        ):
            start = f"Write a health insurance appeal for procedure {procedure} with diagnosis {diagnosis} given the following denial:"
        elif procedure is not None and procedure != "":
            start = f"Write a health insurance appeal for procedure {procedure} given the following denial:"
        return f"{base}{start}\n{denial_text}"

    def make_open_med_prompt(
        self, procedure=None, diagnosis=None, is_trans=False
    ) -> Optional[str]:
        base = ""
        if is_trans:
            base = "While answering the question keep in mind the patient is trans."
        if procedure is not None and len(procedure) > 3:
            if diagnosis is not None and len(diagnosis) > 3:
                return f"{base}Why is {procedure} medically necessary for {diagnosis}?"
            else:
                return f"{base}Why is {procedure} is medically necessary?"
        else:
            return None

    def make_appeals(
        self, denial, template_generator, medical_reasons=[], non_ai_appeals=[]
    ) -> Iterator[str]:
        open_prompt = self.make_open_prompt(
            denial_text=denial.denial_text,
            procedure=denial.procedure,
            diagnosis=denial.diagnosis,
        )
        open_medically_necessary_prompt = self.make_open_med_prompt(
            procedure=denial.procedure,
            diagnosis=denial.diagnosis,
        )

        # TODO: use the streaming and cancellable APIs (maybe some fancy JS on the client side?)

        # For any model that we have a prompt for try to call it and return futures
        def get_model_result(
            model: RemoteModel,
            prompt: str,
            patient_context: Optional[str],
            plan_context: Optional[str],
            infer_type: str,
        ) -> List[Future[Tuple[str, Optional[str]]]]:
            print(f"Looking up on {model}")
            if prompt is None:
                print(f"No prompt for {model} skipping")
                return []
            # If the model has parallelism use it
            results = None
            try:
                if isinstance(model, RemoteOpenLike):
                    print(f"Using {model}'s parallel inference")
                    reveal_type(model)
                    results = model.parallel_infer(
                        prompt=prompt,
                        patient_context=patient_context,
                        plan_context=plan_context,
                        infer_type=infer_type,
                    )
                else:
                    print(f"Using system level parallel inference for {model}")
                    results = [
                        executor.submit(
                            model.infer,
                            prompt=prompt,
                            patient_context=patient_context,
                            plan_context=plan_context,
                            infer_type=infer_type,
                        )
                    ]
            except Exception as e:
                print(
                    f"Error {e} {traceback.format_exc()} submitting to {model} falling back"
                )
                results = [
                    executor.submit(
                        model.infer,
                        prompt=prompt,
                        patient_context=patient_context,
                        plan_context=plan_context,
                        infer_type=infer_type,
                    )
                ]
            print(
                f"Infered {results} for {model}-{infer_type} using {prompt} w/ {patient_context}"
            )
            print("Yay!")
            return results

        medical_context = ""
        if denial.qa_context is not None:
            medical_context += denial.qa_context
        if denial.health_history is not None:
            medical_context += denial.health_history
        plan_context = denial.plan_context
        calls = [
            {
                "model": self.remotehealth,
                "prompt": open_prompt,
                "patient_context": medical_context,
                "plan_context": plan_context,
                "infer_type": "full",
            },
        ]

        if denial.use_external:
            calls.extend(
                [
                    {
                        "model": self.perplexity,
                        "prompt": open_prompt,
                        "patient_context": medical_context,
                        "infer_type": "full",
                        "plan_context": plan_context,
                    }
                ]
            )
            calls.extend(
                [
                    {
                        "model": self.together,
                        "prompt": open_prompt,
                        "patient_context": medical_context,
                        "infer_type": "full",
                        "plan_context": plan_context,
                    }
                ]
            )

        # TODO: Add another external backup for external models.
        backup_calls: List[Any] = []
        # If we need to know the medical reason ask our friendly LLMs
        static_appeal = template_generator.generate_static()
        initial_appeals = non_ai_appeals
        if static_appeal is None:
            calls.extend(
                [
                    {
                        "model": self.remotehealth,
                        "prompt": open_medically_necessary_prompt,
                        "patient_context": medical_context,
                        "infer_type": "medically_necessary",
                        "plan_context": plan_context,
                    },
                ]
            )
        else:
            # Otherwise just put in as is.
            initial_appeals.append(static_appeal)
        for reason in medical_reasons:
            print(f"Using reason {reason}")
            appeal = template_generator.generate(reason)
            initial_appeals.append(appeal)

        print(f"Initial appeal {initial_appeals}")
        # Executor map wants a list for each parameter.

        def make_async_model_calls(calls) -> List[Future[Iterable[str]]]:
            print(f"Calling models: {calls}")
            model_futures = itertools.chain.from_iterable(
                map(lambda x: get_model_result(**x), calls)
            )

            def generated_to_appeals_text(k_text_future):
                model_results = k_text_future.result()
                if model_results is None:
                    return []
                for k, text in model_results:
                    if text is None:
                        pass
                    # It's either full or a reason to plug into a template
                    if k == "full":
                        yield text
                    else:
                        yield template_generator.generate(text)

            # Python lack reasonable future chaining (ugh)
            generated_text_futures = list(
                map(
                    lambda f: executor.submit(generated_to_appeals_text, f),
                    model_futures,
                )
            )
            return generated_text_futures

        generated_text_futures: List[Future[Iterable[str]]] = make_async_model_calls(
            calls
        )

        # Since we publish the results as they become available
        # we want to add some randomization to the initial appeals so they are
        # not always appearing in the first position.
        def random_delay(appeal) -> List[str]:
            time.sleep(random.randint(0, 15))
            return [appeal]

        delayed_initial_appeals: List[Future[Iterable[str]]] = list(
            map(lambda appeal: executor.submit(random_delay, appeal), initial_appeals)
        )
        appeals_futures: List[Future[Iterable[str]]] = (
            delayed_initial_appeals + generated_text_futures
        )
        appeals: Iterator[str] = itertools.chain.from_iterable(
            as_available(appeals_futures)
        )
        # Check and make sure we have a result
        try:
            appeals = itertools.chain([appeals.__next__()], appeals)
        except StopIteration:
            appeals = itertools.chain.from_iterable(
                as_available(make_async_model_calls(backup_calls))
            )
        print(f"Sending back {appeals}")
        return appeals
