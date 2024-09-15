from fighthealthinsurance import rest_views
from django.urls import path

rest_urls = [
    path("removedata", rest_views.RemoveData.as_view(), name="api_delete"),
]
