"""A simulated long plan policy, as a member would paste it into the chat.

The policy is invented (Example Health Plan is no real plan) but shaped like
a real clinical pharmacy policy: a purpose statement, definitions, clinical
background per indication, per-indication criteria, the rules a member
actually fights over, a billing-code table, a long reference list and a
revision history. It is hard-wrapped at 78 columns, as text copied out of a
PDF is, so a phrase can break across lines.

The facts the tests look for (the *_RULE constants, BILLING_CODE) sit past
everything a long paste's previews show the model -- its first 2000 and last
500 characters, and the first 24000 its last-resort variant sends -- so only
a search of the stored text can find them. tests/sync/test_document_search.py
checks that placement.
"""

import textwrap

POLICY_NAME = "Example Health Plan CP-0457 Adalimumab Products"

STEP_THERAPY_RULE = (
    "Step therapy: before Humira (adalimumab) is covered, the member must have "
    "tried and failed at least two preferred adalimumab biosimilars, Hyrimoz "
    "(adalimumab-adaz) and Idacio (adalimumab-aacf), for at least 12 weeks "
    "each, unless a step therapy exception applies."
)
QUANTITY_LIMIT_RULE = (
    "Quantity limit: two (2) 40 mg pens per 28 days after the loading dose."
)
EXCEPTION_RULE = (
    "A step therapy exception is granted when a preferred biosimilar is "
    "contraindicated, was tried and discontinued because of an adverse "
    "reaction, or when the member has been stable on Humira for at least 90 "
    "days under another plan."
)
EXCLUSION_RULE = (
    "Adalimumab is not covered in combination with another biologic DMARD or "
    "a Janus kinase (JAK) inhibitor."
)
APPEAL_RULE = (
    "You or your prescriber may request an internal appeal within 180 days of "
    "the denial notice; an expedited appeal is decided within 72 hours."
)
BILLING_CODE = "J0135"

# What a member types under the pasted policy: the question rides in the
# paste's tail, which the model does see.
MEMBER_QUESTION = (
    "My question: does this policy make me try other drugs before Humira? "
    "My doctor wants me on Humira for Crohn's disease."
)

# The member's word for step therapy, which the policy never uses.
MEMBERS_WORD_FOR_STEP_THERAPY = "fail-first protocol"

_INDICATIONS = [
    (
        "Rheumatoid arthritis",
        "RA",
        "is a chronic, symmetric inflammatory polyarthritis that leads to "
        "joint erosion, functional decline and excess cardiovascular risk "
        "when it is not controlled.",
        "randomized trials showed reduced radiographic progression when "
        "adalimumab was added to methotrexate compared with methotrexate "
        "alone",
        "recommends a conventional synthetic DMARD, usually methotrexate, as "
        "the first treatment and a biologic when the target is not reached",
        18,
        "rheumatologist",
        "the member had an inadequate response to at least 3 months of "
        "methotrexate at 15 mg or more weekly, or methotrexate is "
        "contraindicated",
    ),
    (
        "Psoriatic arthritis",
        "PsA",
        "is an inflammatory arthritis associated with psoriasis that can "
        "involve peripheral joints, the axial skeleton, entheses and digits.",
        "adalimumab improved joint and skin outcomes and slowed structural "
        "damage in placebo-controlled studies",
        "supports a TNF inhibitor for active disease despite a conventional "
        "agent, and as a first option for severe disease",
        18,
        "rheumatologist or dermatologist",
        "the member had an inadequate response to a conventional synthetic "
        "DMARD such as methotrexate, leflunomide or sulfasalazine",
    ),
    (
        "Ankylosing spondylitis",
        "AS",
        "is an axial spondyloarthritis that causes inflammatory back pain, "
        "stiffness and, over time, fusion of the spine.",
        "adalimumab reduced disease activity scores and improved spinal "
        "mobility compared with placebo",
        "recommends a TNF inhibitor after two NSAIDs at full dose fail to "
        "control symptoms",
        18,
        "rheumatologist",
        "the member had an inadequate response to two NSAIDs taken at the "
        "maximum tolerated dose over 4 weeks in total",
    ),
    (
        "Crohn's disease",
        "CD",
        "is a transmural inflammatory bowel disease that may affect any part "
        "of the gastrointestinal tract and can cause strictures and fistulas.",
        "induction and maintenance studies showed higher remission rates with "
        "adalimumab than with placebo, including in members who lost response "
        "to infliximab",
        "supports anti-TNF therapy for moderate to severe disease and for "
        "fistulizing disease",
        6,
        "gastroenterologist",
        "the member has moderately to severely active disease and had an "
        "inadequate response to corticosteroids or an immunomodulator",
    ),
    (
        "Ulcerative colitis",
        "UC",
        "is a chronic inflammatory disease of the colonic mucosa that "
        "typically begins in the rectum and extends proximally.",
        "adalimumab induced and maintained clinical remission in a subset of "
        "members with moderately to severely active disease",
        "supports a biologic for moderate to severe disease after an "
        "inadequate response to conventional therapy",
        5,
        "gastroenterologist",
        "the member had an inadequate response to a 5-aminosalicylate, a "
        "corticosteroid or an immunomodulator",
    ),
    (
        "Hidradenitis suppurativa",
        "HS",
        "is a chronic inflammatory skin disease with painful nodules, "
        "abscesses and draining tunnels in intertriginous areas.",
        "adalimumab was the first agent to show efficacy for moderate to "
        "severe disease in phase 3 trials",
        "recommends adalimumab for moderate to severe disease that has not "
        "responded to oral antibiotics",
        12,
        "dermatologist",
        "the member has Hurley stage II or III disease and had an inadequate "
        "response to at least 90 days of an oral antibiotic",
    ),
    (
        "Plaque psoriasis",
        "PsO",
        "is a chronic immune-mediated skin disease with well-demarcated, "
        "scaly plaques that can cover a large body surface area.",
        "adalimumab produced a 75 percent improvement in the psoriasis area "
        "and severity index in most members at week 16",
        "supports a biologic for moderate to severe disease when phototherapy "
        "or a systemic agent is inadequate or inappropriate",
        18,
        "dermatologist",
        "psoriasis covers at least 10 percent of body surface area, or "
        "sensitive areas, and phototherapy or a systemic agent was inadequate",
    ),
    (
        "Non-infectious uveitis",
        "UV",
        "is intraocular inflammation without an infectious cause that can "
        "lead to vision loss when it is recurrent or chronic.",
        "adalimumab lowered the risk of treatment failure in active and "
        "inactive non-infectious intermediate, posterior and panuveitis",
        "supports adalimumab as a corticosteroid-sparing agent",
        2,
        "ophthalmologist",
        "the member has intermediate, posterior or panuveitis and cannot "
        "taper systemic corticosteroids without a flare",
    ),
]

_DEFINITIONS = [
    (
        "Biosimilar",
        "a biological product that is highly similar to an FDA-licensed "
        "reference product, with no clinically meaningful differences in "
        "safety, purity or potency.",
    ),
    (
        "Interchangeable biosimilar",
        "a biosimilar that the FDA has determined may be substituted for the "
        "reference product at the pharmacy, where state law allows, without "
        "the prescriber's intervention.",
    ),
    (
        "Preferred product",
        "a drug on the plan formulary that is covered at the lowest cost "
        "share for the indication and that the plan requires before "
        "non-preferred alternatives.",
    ),
    (
        "Prior authorization",
        "the plan's review of a request before a drug is dispensed, to "
        "confirm that the policy criteria are met.",
    ),
    (
        "Step therapy",
        "a requirement that a member try one or more preferred drugs before "
        "a non-preferred drug is covered.",
    ),
    (
        "Loading dose",
        "a higher initial dose given at the start of treatment to reach a "
        "therapeutic level quickly.",
    ),
    (
        "Biologic DMARD",
        "a disease-modifying antirheumatic drug made from a living source, "
        "such as a TNF inhibitor, an interleukin inhibitor or a T-cell "
        "costimulation modulator.",
    ),
    (
        "Targeted synthetic DMARD",
        "a small-molecule drug designed to block a specific pathway, such as "
        "a Janus kinase inhibitor.",
    ),
    (
        "Inadequate response",
        "failure to reach the treatment goal after an adequate dose for an "
        "adequate time, as documented in the medical record.",
    ),
    (
        "Contraindication",
        "a condition that makes a particular drug inadvisable for the member, "
        "documented by the prescriber.",
    ),
    (
        "Medically necessary",
        "health care services that a prudent physician would provide to "
        "diagnose or treat an illness, in accordance with generally accepted "
        "standards of medical practice, and not primarily for convenience.",
    ),
]

# Per indication: its dosing, then (trial, population, finding) per study.
_DOSING_AND_TRIALS = {
    "RA": (
        "40 mg subcutaneously every other week; members not taking "
        "methotrexate may increase to 40 mg every week or 80 mg every other "
        "week.",
        [
            (
                "ARMADA",
                "who had an inadequate response to methotrexate",
                "Adding adalimumab to methotrexate improved the proportion "
                "reaching an ACR20 response at week 24.",
            ),
            (
                "DE019",
                "on a stable dose of methotrexate",
                "Radiographic progression over one year was lower with "
                "adalimumab than with placebo.",
            ),
            (
                "PREMIER",
                "with early, methotrexate-naive disease",
                "Combination therapy outperformed either monotherapy on "
                "clinical and radiographic outcomes at two years.",
            ),
        ],
    ),
    "PsA": (
        "40 mg subcutaneously every other week.",
        [
            (
                "ADEPT",
                "with moderately to severely active disease",
                "Joint and skin responses at week 12 favored adalimumab, and "
                "structural progression was slowed at week 24.",
            ),
        ],
    ),
    "AS": (
        "40 mg subcutaneously every other week.",
        [
            (
                "ATLAS",
                "with active disease despite NSAIDs",
                "The ASAS20 response at week 12 was higher with adalimumab, "
                "with benefits maintained through two years of open-label "
                "follow-up.",
            ),
        ],
    ),
    "CD": (
        "160 mg on day 1, 80 mg on day 15, then 40 mg every other week "
        "starting on day 29.",
        [
            (
                "CLASSIC I",
                "naive to anti-TNF therapy",
                "Induction with the higher dose regimen produced more "
                "remissions at week 4 than placebo.",
            ),
            (
                "CHARM",
                "who responded to open-label induction",
                "Maintenance dosing every other week or every week kept more "
                "members in remission through week 56.",
            ),
            (
                "GAIN",
                "who had lost response to or could not tolerate infliximab",
                "Induction remission rates at week 4 were higher than with "
                "placebo.",
            ),
        ],
    ),
    "UC": (
        "160 mg on day 1, 80 mg on day 15, then 40 mg every other week "
        "starting on day 29; continue only in members who show clinical "
        "remission by week 8.",
        [
            (
                "ULTRA 1",
                "naive to anti-TNF therapy",
                "Remission at week 8 was more frequent with the higher "
                "induction regimen.",
            ),
            (
                "ULTRA 2",
                "including members previously treated with anti-TNF agents",
                "Remission at weeks 8 and 52 favored adalimumab over placebo.",
            ),
        ],
    ),
    "HS": (
        "160 mg on day 1, 80 mg on day 15, then 40 mg every week or 80 mg "
        "every other week starting on day 29.",
        [
            (
                "PIONEER I",
                "with moderate to severe disease",
                "A clinical response at week 12 was reached by more members "
                "on weekly adalimumab than on placebo.",
            ),
            (
                "PIONEER II",
                "with moderate to severe disease, some on oral antibiotics",
                "The week 12 response confirmed the first study's result.",
            ),
        ],
    ),
    "PsO": (
        "80 mg initial dose, then 40 mg every other week starting one week "
        "after the initial dose.",
        [
            (
                "REVEAL",
                "with moderate to severe chronic plaque psoriasis",
                "Most members reached a PASI 75 response at week 16, and "
                "responses were maintained with continued dosing.",
            ),
            (
                "CHAMPION",
                "who were candidates for systemic therapy",
                "Adalimumab outperformed both methotrexate and placebo at "
                "week 16.",
            ),
        ],
    ),
    "UV": (
        "80 mg initial dose, then 40 mg every other week starting one week "
        "after the initial dose.",
        [
            (
                "VISUAL I",
                "with active non-infectious uveitis despite corticosteroids",
                "Time to treatment failure was longer with adalimumab than "
                "with placebo.",
            ),
            (
                "VISUAL II",
                "with inactive, corticosteroid-dependent disease",
                "Adalimumab lowered the risk of flare during the "
                "corticosteroid taper.",
            ),
        ],
    ),
}

_PRODUCTS = [
    ("Humira", "adalimumab", "non-preferred"),
    ("Amjevita", "adalimumab-atto", "non-preferred"),
    ("Cyltezo", "adalimumab-adbm", "non-preferred"),
    ("Hadlima", "adalimumab-bwwd", "non-preferred"),
    ("Hulio", "adalimumab-fkjp", "non-preferred"),
    ("Hyrimoz", "adalimumab-adaz", "preferred"),
    ("Idacio", "adalimumab-aacf", "preferred"),
    ("Simlandi", "adalimumab-ryvk", "non-preferred"),
    ("Yuflyma", "adalimumab-aaty", "non-preferred"),
    ("Yusimry", "adalimumab-aqvh", "non-preferred"),
]
_PRESENTATIONS = [
    "40 mg/0.4 mL prefilled pen",
    "40 mg/0.8 mL prefilled pen",
    "40 mg/0.4 mL prefilled syringe",
    "20 mg/0.2 mL prefilled syringe",
]

_REFERENCE_AUTHORS = [
    "Smolen JS",
    "Burmester GR",
    "Mease PJ",
    "Colombel JF",
    "Sandborn WJ",
    "Kimball AB",
    "Gordon KB",
    "Jaffe GJ",
    "van der Heijde D",
    "Sieper J",
    "Feagan BG",
    "Menter A",
    "Papp KA",
    "Reich K",
    "Genovese MC",
]
_REFERENCE_TOPICS = [
    "Long-term safety of adalimumab",
    "Switching from originator adalimumab to a biosimilar",
    "Comparative effectiveness of TNF inhibitors",
    "Interchangeability of adalimumab biosimilars",
    "Immunogenicity and drug survival of anti-TNF agents",
    "Treat-to-target outcomes with biologic agents",
    "Dose escalation and therapeutic drug monitoring",
    "Real-world persistence on biologic therapy",
]
_REFERENCE_JOURNALS = [
    "Ann Rheum Dis",
    "Arthritis Rheumatol",
    "Gastroenterology",
    "J Am Acad Dermatol",
    "Lancet",
    "N Engl J Med",
    "Ophthalmology",
    "J Crohns Colitis",
    "BioDrugs",
    "Rheumatology (Oxford)",
]

_ICD10_CODES = [
    ("M05.79", "Rheumatoid arthritis with rheumatoid factor, multiple sites"),
    ("M06.09", "Rheumatoid arthritis without rheumatoid factor, multiple sites"),
    ("M06.4", "Inflammatory polyarthropathy"),
    ("L40.50", "Arthropathic psoriasis, unspecified"),
    ("L40.52", "Psoriatic arthritis mutilans"),
    ("L40.59", "Other psoriatic arthropathy"),
    ("M45.9", "Ankylosing spondylitis of unspecified sites in spine"),
    ("M45.A9", "Non-radiographic axial spondyloarthritis, multiple sites"),
    ("K50.00", "Crohn's disease of small intestine without complications"),
    ("K50.10", "Crohn's disease of large intestine without complications"),
    ("K50.80", "Crohn's disease of both small and large intestine"),
    ("K50.90", "Crohn's disease, unspecified, without complications"),
    ("K51.00", "Ulcerative (chronic) pancolitis without complications"),
    ("K51.20", "Ulcerative (chronic) proctitis without complications"),
    ("K51.50", "Left sided colitis without complications"),
    ("K51.90", "Ulcerative colitis, unspecified, without complications"),
    ("L73.2", "Hidradenitis suppurativa"),
    ("L40.0", "Psoriasis vulgaris"),
    ("H20.10", "Chronic iridocyclitis, unspecified eye"),
    ("H30.90", "Unspecified chorioretinal inflammation, unspecified eye"),
    ("H44.119", "Panuveitis, unspecified eye"),
]


def _paragraph(text: str) -> str:
    return textwrap.fill(" ".join(text.split()), width=78)


def _section(title: str, *paragraphs: str) -> str:
    return "\n\n".join([title.upper(), *(_paragraph(p) for p in paragraphs)])


def _criteria_block(number: int, indication: tuple) -> str:
    name, abbr, _, _, _, min_age, specialist, prior_treatment = indication
    lines = [
        f"{number}. {name} ({abbr})",
        _paragraph(
            f"Authorization of 6 months may be granted for members {min_age} "
            f"years of age or older when all of the following criteria are "
            f"met:"
        ),
        _paragraph(f"a. The diagnosis is confirmed by a {specialist};"),
        _paragraph(f"b. {prior_treatment};"),
        _paragraph(
            "c. The prescriber attests that the member has no active serious "
            "infection; and"
        ),
        _paragraph(
            "d. A tuberculosis screening test was negative within 6 months "
            "before the first dose."
        ),
    ]
    return "\n".join(lines)


def _build_policy() -> str:
    sections = [
        "\n".join(
            [
                "EXAMPLE HEALTH PLAN",
                "CLINICAL PHARMACY POLICY CP-0457",
                "Adalimumab Products (Humira and Biosimilars)",
                "Effective date: January 1, 2026      Next review: January 1, 2027",
            ]
        ),
        _section(
            "Purpose",
            "This policy states the prior authorization criteria Example "
            "Health Plan applies to adalimumab products for commercial, "
            "exchange and self-funded group members. It applies to the "
            "pharmacy benefit and to adalimumab billed under the medical "
            "benefit. Criteria are reviewed at least once a year by the "
            "Pharmacy and Therapeutics Committee.",
            "Coverage is subject to the member's benefit plan. Where the "
            "benefit plan and this policy conflict, the benefit plan "
            "controls. State mandates that require different criteria take "
            "precedence for members in that state.",
        ),
        _section(
            "Definitions",
            *(f"{term}: {meaning}" for term, meaning in _DEFINITIONS),
        ),
        "PRODUCTS COVERED UNDER THIS POLICY\n\n"
        + "Brand | Nonproprietary name | Presentation | Formulary status\n"
        + "\n".join(
            f"{brand} | {nonproprietary} | {presentation} | {status}"
            for brand, nonproprietary, status in _PRODUCTS
            for presentation in _PRESENTATIONS
        ),
        _section(
            "Clinical background",
            *(
                f"{name} ({abbr}) {about} Adalimumab is a fully human "
                f"monoclonal antibody that binds tumor necrosis factor alpha "
                f"and blocks its interaction with the p55 and p75 cell surface "
                f"TNF receptors. In {abbr}, {evidence}. Professional society "
                f"guidance {guidance}. Members starting therapy should be "
                f"screened for latent tuberculosis and hepatitis B, and live "
                f"vaccines should be avoided during treatment. Serious "
                f"infections, malignancy, heart failure, demyelinating disease "
                f"and lupus-like syndrome have been reported with TNF "
                f"blockers, and the prescriber should weigh these risks for "
                f"each member."
                for name, abbr, about, evidence, guidance, *_ in _INDICATIONS
            ),
        ),
        _section(
            "Dosage and administration",
            *(
                f"{name} ({abbr}): {_DOSING_AND_TRIALS[abbr][0]}"
                for name, abbr, *_ in _INDICATIONS
            ),
            "Adalimumab is supplied as single-dose prefilled pens and "
            "syringes. The first injection should be given under the "
            "supervision of a health care professional, after which a member "
            "or caregiver who has been trained may inject at home. Injection "
            "sites should be rotated, and injections should not be given "
            "into skin that is tender, bruised, red or hard.",
        ),
        _section(
            "Summary of clinical evidence",
            *(
                f"The {trial} study enrolled adults with {name.lower()} "
                f"{population}. {finding} Adverse events were consistent with "
                f"the known safety profile of TNF blockers, with injection "
                f"site reactions and upper respiratory infections reported "
                f"most often, and discontinuation because of adverse events "
                f"was uncommon. The committee rated the quality of this "
                f"evidence as high for the {abbr} indication."
                for name, abbr, *_ in _INDICATIONS
                for trial, population, finding in _DOSING_AND_TRIALS[abbr][1]
            ),
        ),
        _section(
            "Safety considerations",
            "TNF blockers carry a boxed warning for serious infections, "
            "including tuberculosis, invasive fungal infections and "
            "opportunistic infections, some of which have been fatal. Members "
            "should be tested for latent tuberculosis before treatment and "
            "monitored for active tuberculosis during treatment, even when "
            "the initial test was negative.",
            "Lymphoma and other malignancies, some fatal, have been reported "
            "in children and adolescents treated with TNF blockers. "
            "Hepatosplenic T-cell lymphoma has occurred in adolescents and "
            "young adults with inflammatory bowel disease, most of whom were "
            "also taking azathioprine or 6-mercaptopurine.",
            "Other reported risks include hepatitis B reactivation, new or "
            "worsening heart failure, demyelinating disease, cytopenias and a "
            "lupus-like syndrome. Treatment should be stopped if a serious "
            "infection, a serious allergic reaction or one of these "
            "conditions develops.",
        ),
        "INITIAL AUTHORIZATION CRITERIA\n\n"
        + _paragraph(
            "Adalimumab is considered medically necessary when the criteria "
            "for the member's indication below are met and the step therapy "
            "and quantity limit requirements of this policy are satisfied. "
            "Requests for indications not listed are reviewed under the "
            "plan's off-label use policy."
        )
        + "\n\n"
        + "\n\n".join(
            _criteria_block(number, indication)
            for number, indication in enumerate(_INDICATIONS, start=1)
        ),
        _section(
            "Step therapy requirements",
            STEP_THERAPY_RULE,
            "Trials of a preferred biosimilar paid for by another plan count "
            "toward this requirement when they are documented in the medical "
            "record or in pharmacy claims. A trial that ended because the "
            "drug was not available is not counted as a failure.",
        ),
        _section(
            "Quantity limits",
            QUANTITY_LIMIT_RULE,
            "The loading dose for Crohn's disease, ulcerative colitis and "
            "hidradenitis suppurativa may be dispensed as a starter package "
            "once per course of therapy. Requests above the quantity limit "
            "require documentation of an inadequate response at the standard "
            "dose and a trough level or antibody test where one is available.",
        ),
        _section(
            "Continuation of therapy",
            "Reauthorization of 12 months may be granted when the prescriber "
            "documents a positive clinical response, such as improvement in "
            "a validated disease activity measure or a reduction in "
            "corticosteroid use, compared with baseline. Members who were "
            "approved under the step therapy exception continue under it "
            "while they remain stable.",
        ),
        _section(
            "Exclusions",
            EXCLUSION_RULE,
            "Adalimumab is not covered for any indication when it is "
            "prescribed for convenience, for an indication considered "
            "experimental or investigational, or when it is not medically "
            "necessary under this policy.",
        ),
        _section(
            "Step therapy exceptions",
            EXCEPTION_RULE,
            "The prescriber requests an exception by submitting the "
            "exception form with supporting chart notes. A standard "
            "exception request is decided within 72 hours, and an urgent "
            "request within 24 hours.",
        ),
        _section(
            "Appeal rights",
            APPEAL_RULE,
            "If the internal appeal upholds the denial, the member may "
            "request an external review by an independent review "
            "organization within 4 months of the final internal decision. "
            "The plan pays for the external review, and its decision is "
            "binding on the plan.",
        ),
        "CODING\n\nHCPCS\n"
        + f"{BILLING_CODE} | Injection, adalimumab, 20 mg\n"
        + "J3590 | Unclassified biologics\n\nICD-10-CM\n"
        + "\n".join(f"{code} | {label}" for code, label in _ICD10_CODES),
        "REFERENCES\n\n"
        + "\n".join(
            _paragraph(
                f"{index + 1}. {_REFERENCE_AUTHORS[index % 15]}, "
                f"{_REFERENCE_AUTHORS[(index * 7 + 3) % 15]}, et al. "
                f"{_REFERENCE_TOPICS[index % 8]} in "
                f"{_INDICATIONS[(index * 3) % 8][0].lower()}. "
                f"{_REFERENCE_JOURNALS[(index * 5) % 10]}. "
                f"{2008 + index % 17};{20 + index % 60}({1 + index % 12}):"
                f"{100 + index * 7}-{110 + index * 7}."
            )
            for index in range(110)
        ),
        "REVISION HISTORY\n\n"
        + "\n".join(
            f"{date} | {change}"
            for date, change in [
                ("01/2026", "Annual review; criteria unchanged"),
                ("07/2025", "Added interchangeable biosimilar definition"),
                ("01/2025", "Updated preferred biosimilars"),
                ("07/2024", "Added hidradenitis suppurativa loading dose"),
                ("01/2024", "Annual review; references updated"),
                ("07/2023", "Policy created"),
            ]
        ),
    ]
    return "\n\n\n".join(sections) + "\n"


POLICY_TEXT = _build_policy()

# The paste a member sends: the whole policy, then their question.
PASTED_POLICY_WITH_QUESTION = f"{POLICY_TEXT}\n{MEMBER_QUESTION}"

RULES = [
    STEP_THERAPY_RULE,
    QUANTITY_LIMIT_RULE,
    EXCEPTION_RULE,
    EXCLUSION_RULE,
    APPEAL_RULE,
]


def squash(text: str) -> str:
    """Collapse whitespace, so a rule matches the policy's wrapped copy."""
    return " ".join(text.split())
