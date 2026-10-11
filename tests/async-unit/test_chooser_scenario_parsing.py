"""The chooser's scenario parsing: case facts and the appeal prompt built
from them. No database, no models."""

from fighthealthinsurance.chooser_tasks import (
    CHOOSER_MAX_FACTS,
    _build_appeal_prompt,
    _facts_from_response,
    _scenario_prompt,
)
from fighthealthinsurance.condition_rankings import SeedPair

_SCENARIO = (
    "Procedure: MRI of lumbar spine\n"
    "Diagnosis: chronic lower back pain\n"
    "Insurance Company: Fictional Mutual\n"
    "Denial Reason: not medically necessary.\n"
)


def test_facts_on_one_line_split_on_semicolons():
    text = _SCENARIO + (
        "Case Facts: Patient in their 40s; symptoms for 8 months; "
        "six weeks of physical therapy with no improvement; "
        "clinician documented radiating leg pain.\n"
    )
    assert _facts_from_response(text) == [
        "Patient in their 40s",
        "symptoms for 8 months",
        "six weeks of physical therapy with no improvement",
        "clinician documented radiating leg pain",
    ]


def test_facts_as_a_bullet_list_under_the_label():
    text = _SCENARIO + (
        "**Case Facts:**\n"
        "- Patient in their 50s\n"
        "* Symptoms for two years.\n"
        "1. Tried NSAIDs and physical therapy\n"
    )
    assert _facts_from_response(text) == [
        "Patient in their 50s",
        "Symptoms for two years",
        "Tried NSAIDs and physical therapy",
    ]


def test_facts_stop_at_the_next_labelled_field():
    text = (
        "Case Facts:\n- Patient in their 30s\n- Symptoms for a year\n"
        "Denial Reason: not medically necessary.\n"
    )
    assert _facts_from_response(text) == ["Patient in their 30s", "Symptoms for a year"]


def test_no_facts_label_means_no_facts():
    assert _facts_from_response(_SCENARIO) == []


def test_facts_are_deduped_and_capped():
    facts = "; ".join(f"fact {i}" for i in range(CHOOSER_MAX_FACTS + 4))
    text = _SCENARIO + f"Case Facts: fact 0; {facts}\n"
    parsed = _facts_from_response(text)
    assert len(parsed) == CHOOSER_MAX_FACTS
    assert len(set(parsed)) == CHOOSER_MAX_FACTS


def test_seeded_scenario_prompt_names_the_pair_and_asks_for_facts():
    prompt = _scenario_prompt(SeedPair("MRI", "Lower back pain", 12))
    assert "Procedure: MRI\n" in prompt
    assert "Diagnosis: Lower back pain\n" in prompt
    assert "Case Facts:" in prompt
    assert "copy them verbatim" in prompt


def test_unseeded_scenario_prompt_lets_the_writer_invent_the_pair():
    prompt = _scenario_prompt(None)
    assert "Procedure: [a specific real medical procedure name" in prompt
    assert "Case Facts:" in prompt


def test_appeal_prompt_lists_facts_and_evidence_and_forbids_inventing():
    prompt = _build_appeal_prompt(
        {
            "procedure": "MRI",
            "diagnosis": "Lower back pain",
            "facts": ["Patient in their 40s", "Eight months of symptoms"],
            "evidence": [
                {"pmid": "123", "title": "MRI for low back pain", "url": "u"},
                {"pmid": "", "title": "", "url": ""},
            ],
        }
    )
    assert "- Patient in their 40s" in prompt
    assert "- MRI for low back pain (PMID 123)" in prompt
    assert "the only studies you may cite" in prompt
    assert "if nothing on file fits, cite nothing" in prompt
    assert "Never invent a study" in prompt


def test_appeal_prompt_without_evidence_says_to_cite_nothing():
    prompt = _build_appeal_prompt({"procedure": "MRI", "diagnosis": "Lower back pain"})
    assert "Case facts" not in prompt
    assert "there is none on file, so cite no studies" in prompt
