from django.db.models.signals import pre_save
from django.dispatch import receiver
from fhi_users.models import ProfessionalDomainRelation

@receiver(pre_save, sender=ProfessionalDomainRelation)
def professional_domain_relation_presave(
    sender: type, instance: ProfessionalDomainRelation, **kwargs: dict
) -> None:
    """Dynamically set the active field based on pending/suspended/rejected."""
    instance.active = (
        not instance.pending and not instance.suspended and not instance.rejected
    )
