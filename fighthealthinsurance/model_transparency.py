"""The data behind the About Our AI page: which models write appeal letters,
and what each test of them found.

Two kinds of files in static/model_transparency/, so the page changes by
editing data, never page code:

* ``models.json``: one entry per model, with what it does and where it runs.
  A model is retired by setting ``retired`` (a date) and ``retired_reason``;
  entries are never deleted, so the page can always say what changed.
* ``runs/<id>.json``: one file per test run, never edited after it is
  published: what was tested, how, and the results, as totals only.

Both are public. They carry scores, timings and costs, never a letter, a
denial or anything about a person; ``load_runs`` refuses any field it does
not know, so nothing else can reach the page by accident.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional

from fighthealthinsurance.static_data import read_static_text

DATA_DIR = "model_transparency"

MODEL_FIELDS = frozenset(
    {
        "id",
        "name",
        "maker",
        "role",
        "runs_on",
        "setup",
        "trained_by_us",
        "tested_in",
        "retired",
        "retired_reason",
    }
)
RESULT_FIELDS = frozenset(
    {
        "rank",
        "name",
        "setup",
        "quality",
        "quality_is_estimate",
        "opus",
        "jev",
        "median_seconds",
        "cost_per_letter_usd",
        "cost_is_assumed",
        "decision",
    }
)
JUDGE_FIELDS = frozenset(
    {
        "name",
        "agreed_of_20",
        "strictness",
        "letters_scored",
        "flagged_made_up_facts",
        "in_use",
    }
)
METHOD_FIELDS = frozenset(
    {
        "cases",
        "case_sources",
        "models_tested",
        "setups_tested",
        "setups_listed",
        "letters_written",
        "judgments",
        "quality",
        "cost",
        "writeup_url",
        "notes",
        "summary",
    }
)
RUN_FIELDS = frozenset(
    {
        "id",
        "title",
        "task",
        "date",
        "comparable_with",
        "method",
        "results",
        "judges",
    }
)


class DataError(ValueError):
    """A data file has a field the page doesn't know."""


def _only(fields: frozenset, row: Dict[str, Any], where: str) -> Dict[str, Any]:
    unknown = set(row) - fields
    if unknown:
        raise DataError(f"{where}: unknown fields {sorted(unknown)}")
    return row


def _of_100(score: Optional[float]) -> str:
    return "not scored" if score is None else str(round(score * 100))


@dataclass(frozen=True)
class Result:
    rank: int
    name: str
    setup: str
    quality: float
    quality_is_estimate: bool
    opus: float
    jev: float
    median_seconds: float
    cost_per_letter_usd: Optional[float]
    cost_is_assumed: bool
    decision: str

    @property
    def quality_text(self) -> str:
        return _of_100(self.quality)

    @property
    def opus_text(self) -> str:
        return _of_100(self.opus)

    @property
    def jev_text(self) -> str:
        return _of_100(self.jev)

    @property
    def cost_text(self) -> str:
        cost = self.cost_per_letter_usd
        if cost is None:
            return "not recorded"
        if cost < 0.001:
            return "under $0.001"
        return f"${cost:.3f}"


@dataclass(frozen=True)
class Judge:
    name: str
    agreed_of_20: int
    strictness: str
    letters_scored: int
    flagged_made_up_facts: Optional[float]
    in_use: bool

    @property
    def flagged_text(self) -> str:
        rate = self.flagged_made_up_facts
        if rate is None:
            return "not counted"
        return f"{round(rate * 100)} of 100"


@dataclass(frozen=True)
class Run:
    id: str
    title: str
    task: str
    date: str
    comparable_with: List[str]
    method: Dict[str, Any]
    results: List[Result]
    judges: List[Judge]

    @property
    def letters_written_text(self) -> str:
        return f"{int(self.method.get('letters_written', 0)):,}"

    @property
    def judgments_text(self) -> str:
        return f"{int(self.method.get('judgments', 0)):,}"

    @property
    def chosen(self) -> Optional[Result]:
        return next((r for r in self.results if r.decision.startswith("Chosen")), None)


@dataclass(frozen=True)
class Model:
    id: str
    name: str
    maker: str
    role: str
    runs_on: str
    setup: str
    trained_by_us: bool
    tested_in: Optional[str]
    retired: Optional[str]
    retired_reason: str


@dataclass(frozen=True)
class Transparency:
    models: List[Model]
    changes: List[Dict[str, str]]
    runs: List[Run] = field(default_factory=list)

    @property
    def in_use(self) -> List[Model]:
        return [m for m in self.models if not m.retired]

    @property
    def retired(self) -> List[Model]:
        return [m for m in self.models if m.retired]

    @property
    def latest_run(self) -> Optional[Run]:
        return self.runs[-1] if self.runs else None


def _read(name: str) -> Any:
    text = read_static_text(f"{DATA_DIR}/{name}")
    if text is None:
        raise FileNotFoundError(f"{DATA_DIR}/{name}")
    return json.loads(text)


def parse_run(data: Dict[str, Any]) -> Run:
    where = f"run {data.get('id', '?')}"
    _only(RUN_FIELDS, data, where)
    _only(METHOD_FIELDS, data.get("method", {}), f"{where} method")
    results = [
        Result(**_only(RESULT_FIELDS, r, f"{where} result"))
        for r in data.get("results", [])
    ]
    judges = [
        Judge(**_only(JUDGE_FIELDS, j, f"{where} judge"))
        for j in data.get("judges", [])
    ]
    return Run(
        id=data["id"],
        title=data["title"],
        task=data["task"],
        date=data["date"],
        comparable_with=list(data.get("comparable_with", [])),
        method=data.get("method", {}),
        results=sorted(results, key=lambda r: r.rank),
        judges=judges,
    )


# The published runs, oldest first. A new run is a new file plus a line here.
RUN_FILES = ("runs/2026-09-letter-test.json",)


@lru_cache(maxsize=1)
def load() -> Transparency:
    """Everything the page shows. Cached: the files change only on deploy."""
    data = _read("models.json")
    models = [
        Model(**_only(MODEL_FIELDS, m, "models.json")) for m in data.get("models", [])
    ]
    runs = sorted((parse_run(_read(name)) for name in RUN_FILES), key=lambda r: r.date)
    return Transparency(models=models, changes=data.get("changes", []), runs=runs)
