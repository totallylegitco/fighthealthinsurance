import re
from abc import ABC, abstractmethod
from fighthealthinsurance.models import PlanType, Regulator, DenialTypes

class DenialBase(ABC):
    @abstractmethod
    def get_denialtype(self, text):
        pass

    @abstractmethod
    def get_regulator(self, text):
        pass

    @abstractmethod
    def get_plan_type(self, text):
        pass

class ProcessDenialRegex(DenialBase):
    def __init__(self):
        self.planTypes = PlanType.objects.all()
        self.regulators = Regulator.objects.all()
        self.denialTypes = DenialTypes.objects.all()
        
    def get_denialtype(self, text):
        print(f"Getting denial types for {text}")
        denials = []
        for d in self.denialTypes:
            print(f"Exlporing {d} w/ {d.regex} & {d.negative_regex}")
            if (d.regex.pattern != '' and d.regex.search(text) is not None):
                print("positive regex match")
                if (d.negative_regex.pattern == '' or d.negative_regex.search(text) is None):
                    print("no negative regex match!")
                    denials.append(d)
        print(f"Collected: {denials}")
        return denials


    def get_regulator(self, text):
        regulators = []
        for r in self.regulators:
            if (r.regex.search(text) is not None and
                r.negative_regex.search(text) is None):
                regulators.push(r)
        return regulators


    def get_plan_type(self, text):
        plans = []
        for p in self.planTypes:
            if (p.regex.search(text) is not None and
                p.negative_regex.search(text) is None):
                plans.push(p)
        return plans
