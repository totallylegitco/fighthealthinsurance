"""Refresh the condition and treatment rankings' vocabulary verdicts.

The chooser refill actor does this on its own once an hour; the command is
for a first fill after deploy, or for spending a larger lookup budget by
hand. Only k-anonymous terms are ever looked up (see condition_rankings.py).
"""

from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand

from fighthealthinsurance import condition_rankings


class Command(BaseCommand):
    help = "Check the most-appealed conditions and treatments against the medical vocabularies"

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--budget",
            type=int,
            default=None,
            help="Outside lookups to spend (default: CONDITION_RANKING_LOOKUP_BUDGET)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        stats = async_to_sync(condition_rankings.refresh_term_checks)(
            budget=options["budget"]
        )
        self.stdout.write(f"Refreshed: {stats}")
        for kind in condition_rankings.KINDS:
            rows = condition_rankings.ranked_terms(kind, limit=10)
            self.stdout.write(f"Top {kind}s:")
            for row in rows:
                self.stdout.write(f"  {row.public_count}+  {row.display}")
