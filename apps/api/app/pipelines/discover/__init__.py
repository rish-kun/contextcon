"""Discover pipeline: thesis → criteria → Crustdata search → gate → enrich → shortlist.

Importing this package registers its step handlers (`discover.search`, `discover.gate`,
`discover.enrich`, `discover.score`, `discover.explain`) with the job runner.
"""

from app.pipelines.discover import steps  # noqa: F401  (registers the step handlers)
from app.pipelines.discover.service import (
    InvalidCriteria,
    SearchInProgress,
    create_thesis,
    replace_criteria,
    start_search,
)

__all__ = [
    "InvalidCriteria",
    "SearchInProgress",
    "create_thesis",
    "replace_criteria",
    "start_search",
]
