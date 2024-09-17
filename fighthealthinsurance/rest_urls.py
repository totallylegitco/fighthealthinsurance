from fighthealthinsurance import rest_views
from django.urls import path

rest_urls = [
    path("removedata", rest_views.RemoveData.as_view(), name="api_delete"),
    path("findnextsteps", rest_views.FindNextSteps.as_view(), name="api_findnextsteps"),
    path("denialcreator", rest_views.DenialCreator.as_view(), name="api_denialcreator"),
]
