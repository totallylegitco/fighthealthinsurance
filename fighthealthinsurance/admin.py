# type: ignore
from django.apps import apps
from django.contrib import admin

from fighthealthinsurance.models import *
from fhi_users.models import User
from django.contrib.auth.admin import UserAdmin

# Auto magic
models = apps.get_models()


@admin.register(Denial)
class DenialAdmin(admin.ModelAdmin):
    list_filter = [
        ("raw_email", admin.EmptyFieldListFilter),
        "plan_source__name",
        "plan_type__name",
        "denial_type__name",
    ]


# for model in models:
#     # A bit ugly but auto register everything which has not exploded when auto registering cauze I'm lazy
#     if (
#         "django.contrib" not in model.__module__
#         and "newsletter" not in model.__module__
#         and "cookie_consent" not in model.__module__
#         and "celery" not in model.__module__
#     ):
#         try:
#             admin.site.register(model)
#         except Exception:
#             pass


# Note: Register seprate for avoide Security and Maintainability
# Let me know if we need to add any fields into list or search
@admin.register(InterestedProfessional)
class InterestedProfessionalAdmin(admin.ModelAdmin):
    list_display = ("name", "business_name", "email", "phone_number", "signup_date", "paid")
    search_fields = ("name", "email", "business_name")


@admin.register(MailingListSubscriber)
class MailingListSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "signup_date")
    search_fields = ("email", "name")


@admin.register(FollowUpType)
class FollowUpTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "subject", "duration")
    search_fields = ("name", "subject")


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ("hashed_email", "denial_id", "more_follow_up_requested", "response_date")
    search_fields = ("hashed_email", "denial_id")


@admin.register(FollowUpSched)
class FollowUpSchedAdmin(admin.ModelAdmin):
    list_display = ("email", "follow_up_date", "follow_up_sent")
    search_fields = ("email", "follow_up_date")


@admin.register(PlanType)
class PlanTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "alt_name")
    search_fields = ("name", "alt_name")


@admin.register(Regulator)
class RegulatorAdmin(admin.ModelAdmin):
    list_display = ("name", "website", "alt_name")
    search_fields = ("name", "website")


@admin.register(PlanSource)
class PlanSourceAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Diagnosis)
class DiagnosisAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(Procedures)
class ProceduresAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(DenialTypes)
class DenialTypesAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "form")
    search_fields = ("name", "parent")


@admin.register(AppealTemplates)
class AppealTemplatesAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')

@admin.register(PlanDocuments)
class PlanDocumentsAdmin(admin.ModelAdmin):
    list_display = ('plan_document_id', 'denial')

@admin.register(FollowUpDocuments)
class FollowUpDocumentsAdmin(admin.ModelAdmin):
    list_display = ('document_id', 'denial')

@admin.register(PubMedArticleSummarized)
class PubMedArticleSummarizedAdmin(admin.ModelAdmin):
    list_display = ('pmid', 'title', 'publication_date')

@admin.register(PubMedQueryData)
class PubMedQueryDataAdmin(admin.ModelAdmin):
    list_display = ('internal_id', 'query', 'query_date')

@admin.register(FaxesToSend)
class FaxesToSendAdmin(admin.ModelAdmin):
    list_display = ('fax_id', 'email', 'sent', 'fax_success')

@admin.register(DenialTypesRelation)
class DenialTypesRelationAdmin(admin.ModelAdmin):
    list_display = ('denial', 'denial_type', 'src')

@admin.register(PlanTypesRelation)
class PlanTypesRelationAdmin(admin.ModelAdmin):
    list_display = ('denial', 'plan_type', 'src')

@admin.register(PlanSourceRelation)
class PlanSourceRelationAdmin(admin.ModelAdmin):
    list_display = ('denial', 'plan_source', 'src')

@admin.register(DenialQA)
class DenialQAAdmin(admin.ModelAdmin):
    list_display = ('id', 'denial', 'question', 'bool_answer')

@admin.register(ProposedAppeal)
class ProposedAppealAdmin(admin.ModelAdmin):
    list_display = ('id', 'for_denial', 'chosen', 'editted')

@admin.register(Appeal)
class AppealAdmin(admin.ModelAdmin):
    list_display = ('id', 'for_denial', 'sent', 'patient_visible')