"""Investor discovery pipeline (PRD 1b, design §6.2, plan CP-18).

A business profile becomes a search for comparable companies that have raised money.
Their dated funding rounds are grouped by investor under the identity guard and ranked
by comparable investments found in the record, weighted toward recent ones. The
ranking describes past behaviour; it does not predict investment. Only rounds with a
date and a named investor count, personal contact details are never stored, and v1
stops at the shortlist (no outreach).

Importing this package registers the step handlers in `app.jobs.registry`.
"""

from app.pipelines.investors import steps
from app.pipelines.investors.service import (
    list_investor_searches,
    load_investor_search,
    start_investor_search,
)

__all__ = ["list_investor_searches", "load_investor_search", "start_investor_search", "steps"]
