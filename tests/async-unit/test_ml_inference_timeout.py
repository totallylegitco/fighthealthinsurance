"""infer_with_fallback hands its timeout to the transport and waits a little
longer itself, so a hung backend's own timeout fires and is recorded."""

import asyncio

import pytest

from fighthealthinsurance.ml.ml_inference import infer_with_fallback


class _HungModel:
    """Accepts the call and never answers; records how its own timeout
    ended, the way RemoteOpenLike.__timeout_infer does."""

    def __init__(self):
        self.outcomes = []

    async def _infer_no_context(self, system_prompts, prompt, temperature, timeout):
        try:
            async with asyncio.timeout(timeout):
                await asyncio.sleep(60)
        except TimeoutError:
            self.outcomes.append("timeout")
            return None
        except asyncio.CancelledError:
            self.outcomes.append("cancelled")
            raise


class _AnsweringModel:
    async def _infer_no_context(self, system_prompts, prompt, temperature, timeout):
        return "an answer"


@pytest.mark.asyncio
async def test_a_hung_backend_records_its_own_timeout():
    hung = _HungModel()
    result = await infer_with_fallback(
        system_prompts=["s"], prompt="p", timeout=0.05, models=[hung]
    )
    assert result is None
    assert hung.outcomes == ["timeout"]


@pytest.mark.asyncio
async def test_the_next_model_answers_after_a_hung_one():
    hung = _HungModel()
    result = await infer_with_fallback(
        system_prompts=["s"],
        prompt="p",
        timeout=0.05,
        models=[hung, _AnsweringModel()],
    )
    assert result == "an answer"
    assert hung.outcomes == ["timeout"]
