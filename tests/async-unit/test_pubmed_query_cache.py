"""Tests for the Django-cache layer on find_pubmed_article_ids_for_query.

The test config defaults to DummyCache, so cache assertions are scoped to a
LocMemCache override per test.
"""

import json
from unittest.mock import patch

import pytest

from fighthealthinsurance.models import PubMedQueryData
from fighthealthinsurance.pubmed_tools import PubMedTools

_LOCMEM_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "pubmed-test",
    }
}


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_find_pubmed_ids_positive_cache_hit_skips_db_and_api():
    from django.core.cache import cache
    from django.test.utils import override_settings

    with override_settings(CACHES=_LOCMEM_CACHES):
        await cache.aclear()
        tools = PubMedTools()
        cache_key = tools._pubmed_query_cache_key("Asthma trial", "2022")
        await cache.aset(cache_key, ["11111111"], timeout=60)

        with patch(
            "fighthealthinsurance.pubmed_tools.pubmed_fetcher.pmids_for_query"
        ) as fetch_mock:
            result = await tools.find_pubmed_article_ids_for_query(
                "Asthma trial", since="2022"
            )
        assert result == ["11111111"]
        fetch_mock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_find_pubmed_ids_negative_cache_hit_returns_empty():
    from django.core.cache import cache
    from django.test.utils import override_settings

    with override_settings(CACHES=_LOCMEM_CACHES):
        await cache.aclear()
        tools = PubMedTools()
        cache_key = tools._pubmed_query_cache_key("No matches", "2021")
        await cache.aset(cache_key, [], timeout=60)

        with patch(
            "fighthealthinsurance.pubmed_tools.pubmed_fetcher.pmids_for_query"
        ) as fetch_mock:
            result = await tools.find_pubmed_article_ids_for_query(
                "No matches", since="2021"
            )
        assert result == []
        fetch_mock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_find_pubmed_ids_cache_miss_then_db_hit_writes_through_cache():
    from django.core.cache import cache
    from django.test.utils import override_settings

    with override_settings(CACHES=_LOCMEM_CACHES):
        await cache.aclear()
        tools = PubMedTools()
        await PubMedQueryData.objects.acreate(
            query="COPD treatment",
            since="2020",
            articles=json.dumps(["22222222", "33333333"]),
        )
        cache_key = tools._pubmed_query_cache_key("COPD treatment", "2020")
        assert await cache.aget(cache_key) is None

        with patch(
            "fighthealthinsurance.pubmed_tools.pubmed_fetcher.pmids_for_query"
        ) as fetch_mock:
            result = await tools.find_pubmed_article_ids_for_query(
                "COPD treatment", since="2020"
            )
        assert result == ["22222222", "33333333"]
        assert await cache.aget(cache_key) == ["22222222", "33333333"]
        fetch_mock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
async def test_find_pubmed_ids_cache_miss_then_api_fetch_writes_db_and_cache():
    from django.core.cache import cache
    from django.test.utils import override_settings

    with override_settings(CACHES=_LOCMEM_CACHES):
        await cache.aclear()
        tools = PubMedTools()
        cache_key = tools._pubmed_query_cache_key("heart failure beta blocker", "2023")

        with patch(
            "fighthealthinsurance.pubmed_tools.pubmed_fetcher.pmids_for_query",
            return_value=["44444444"],
        ) as fetch_mock:
            result = await tools.find_pubmed_article_ids_for_query(
                "heart failure beta blocker", since="2023"
            )
        assert result == ["44444444"]
        assert await cache.aget(cache_key) == ["44444444"]
        fetch_mock.assert_called_once_with("heart failure beta blocker", since="2023")
        row = await PubMedQueryData.objects.filter(
            query="heart failure beta blocker",
            since="2023",
            denial_id__isnull=True,
        ).alatest("internal_id")
        assert json.loads(row.articles) == ["44444444"]
