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
        denials = []
        for d in self.denialTypes:
            if (d.regex.match(text) is not None and
                d.negative_regex.match(text) is None):
                denials.push(d)
        return denials


    def get_regulator(self, text):
        regulators = []
        for r in self.regulators:
            if (r.regex.match(text) is not None and
                r.negative_regex.match(text) is None):
                regulators.push(r)
        return regulators


    def get_plan_type(self, text):
        plans = []
        for p in self.planTypes:
            if (p.regex.match(text) is not None and
                p.negative_regex.match(text) is None):
                plans.push(p)
        return plans
