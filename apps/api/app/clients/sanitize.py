"""Keep only the Crustdata fields DealProof needs, and no personal contact details.

Every response passes through `sanitize_response(endpoint, data)` before it is
returned or cached:

1. **Allowlist.** Each endpoint has a spec of the structured fields its callers read
   (the fields in `app.clients.crustdata_models`, plus the documented ones around
   them). Keys outside the spec are dropped, so a new contact field the API starts
   returning never reaches the database.
2. **Opaque subtrees** (`KEEP`: e.g. ``metadata``, ``education``) are kept, with any
   key naming an email or phone field removed.
3. **Free text** (bios, descriptions, snippets, fetched pages) goes through
   `app.documents.redact.regex_redactor`, which replaces emails and phone numbers
   (and other personal identifiers) with ``[redacted:<kind>]``. Every other string is
   checked for email addresses, and for phone numbers when it reads like prose.
"""

from __future__ import annotations

import re
from typing import Any

from app.documents.redact import regex_redactor

KEEP = "keep"  # any subtree; contact-named keys stripped, strings checked
TEXT = "text"  # free text: always redacted
S = "scalar"  # a scalar; containers are dropped

Spec = Any

_CONTACT_KEY = re.compile(r"e-?mail|phone|mobile|telephone|whatsapp|fax", re.IGNORECASE)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


def strip_contact_fields(value: Any) -> Any:
    """Recursively drop keys that name an email or phone field.

    A boolean flag (e.g. ``has_business_email``) carries no contact detail and stays.
    """
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if _CONTACT_KEY.search(str(key)) and not isinstance(item, bool):
                continue
            cleaned[key] = strip_contact_fields(item)
        return cleaned
    if isinstance(value, list):
        return [strip_contact_fields(item) for item in value]
    return value


def redact_text(text: str) -> str:
    return regex_redactor(text)[0]


def _clean_str(value: str, *, free_text: bool) -> str:
    if free_text or any(ch.isspace() for ch in value.strip()):
        return redact_text(value)
    if "@" in value and _EMAIL.search(value):
        return _EMAIL.sub("[redacted:email]", value)
    return value


def _clean_tree(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean_tree(v) for k, v in strip_contact_fields(value).items()}
    if isinstance(value, list):
        return [_clean_tree(item) for item in value]
    if isinstance(value, str):
        return _clean_str(value, free_text=False)
    return value


def apply_spec(spec: Spec, value: Any) -> Any:
    if value is None:
        return None
    if spec == KEEP:
        return _clean_tree(value)
    if spec in (TEXT, S):
        if isinstance(value, dict | list):
            return None
        if isinstance(value, str):
            return _clean_str(value, free_text=spec == TEXT)
        return value
    if isinstance(spec, list):
        if not isinstance(value, list):
            return None
        return [apply_spec(spec[0], item) for item in value]
    if isinstance(spec, dict):
        if not isinstance(value, dict):
            return None
        return {key: apply_spec(spec[key], item) for key, item in value.items() if key in spec}
    raise ValueError(f"bad sanitizer spec: {spec!r}")


# --- Specs -----------------------------------------------------------------------

COMPANY_BASIC = {
    "crustdata_company_id": S,
    "name": S,
    "primary_domain": S,
    "all_domains": [S],
    "website": S,
    "professional_network_url": S,
    "professional_network_id": S,
    "profile_name": S,
    "description": TEXT,
    "company_type": S,
    "status": S,
    "year_founded": S,
    "employee_count_range": S,
    "markets": [S],
    "industries": [S],
}

INVESTOR = {
    "name": S,
    "type": S,
    "uuid": S,
    "permalink": S,
    "crunchbase_profile_url": S,
    "categories": [S],
}

FUNDING = {
    "total_investment_usd": S,
    "last_round_amount_usd": S,
    "last_fundraise_date": S,
    "last_round_type": S,
    "num_funding_rounds": S,
    "investors": [S],
    "investors_detailed": [INVESTOR],
    "milestones": [
        {
            "round_type": S,
            "date": S,
            "funding_date": S,
            "amount_usd": S,
            "investors": [S],
            "lead_investors": KEEP,
            "investors_detailed": [INVESTOR],
            "is_fund": S,
            "permalink": S,
        }
    ],
    "acquisitions": KEEP,
    "acquired_by": KEEP,
}

HEADCOUNT = {
    "total": S,
    "largest_headcount_country": S,
    "timeseries": [{"date": S, "employee_count": S}],
    "growth_percent": KEEP,
    "growth_absolute": KEEP,
}

LOCATIONS = {
    "country": S,
    "headquarters": S,
    "state": S,
    "street_address": S,
    "all_office_addresses": [S],
}

HIRING = {
    "openings_count": S,
    "recent_titles_csv": S,
    "openings_growth_percent": KEEP,
    "open_jobs_timeseries": KEEP,
    "recent_openings": KEEP,
    "by_function_qoq_pct": KEEP,
}

# Founders / CXOs / decision makers inside enrich's `people` group. Identity and role
# only; whatever contact fields the API adds are not on this list.
PERSON_REF = {
    "basic_profile": {"name": S, "headline": TEXT, "current_title": S, "location": KEEP},
    "social_handles": {"professional_network_identifier": KEEP},
    "name": S,
    "title": S,
    "crustdata_person_id": S,
    "person_id": S,
    "professional_network_profile_url": S,
    "profile_url": S,
    "headline": TEXT,
    "seniority_level": S,
    "function_category": S,
    "start_date": S,
    "end_date": S,
}

TAXONOMY = {
    "professional_network_industry": S,
    "professional_network_industries": [S],
    "categories": [S],
    "primary_naics_detail": KEEP,
    "sic_detail_list": KEEP,
}

NEWS = {
    "article_title": TEXT,
    "article_url": S,
    "article_publish_date": S,
    "article_publisher_name": S,
    "publisher_domain": S,
    "confidence_score": S,
    "source": S,
}

COMPANY_RECORD = {
    "crustdata_company_id": S,
    "updated_at": S,
    "indexed_at": S,
    "basic_info": COMPANY_BASIC,
    "headcount": HEADCOUNT,
    "funding": FUNDING,
    "locations": LOCATIONS,
    "hiring": HIRING,
    "people": {"founders": [PERSON_REF], "cxos": [PERSON_REF], "decision_makers": [PERSON_REF]},
    "taxonomy": TAXONOMY,
    "news": [NEWS],
    "social_profiles": KEEP,
    "metadata": KEEP,
}

EMPLOYMENT = {
    "name": S,
    "crustdata_company_id": S,
    "company_id": S,
    "title": S,
    "start_date": S,
    "end_date": S,
    "seniority_level": S,
    "function_category": S,
    "employment_type": S,
    "company_website": S,
    "company_professional_network_profile_url": S,
    "years_at_company_raw": S,
    "description": TEXT,
}

PERSON_PROFILE = {
    "crustdata_person_id": S,
    "basic_profile": {
        "name": S,
        "headline": TEXT,
        "current_title": S,
        "summary": TEXT,
        "location": KEEP,
    },
    "experience": {"employment_details": {"current": [EMPLOYMENT], "past": [EMPLOYMENT]}},
    "education": KEEP,
    # The professional-network profile URL is an identity key (§5.4); other social
    # handles are contact channels and are dropped.
    "social_handles": {"professional_network_identifier": KEEP},
}

JOB_LISTING = {
    "crustdata_job_id": S,
    "job_details": {
        "title": S,
        "category": S,
        "workplace_type": S,
        "url": S,
        "number_of_openings": S,
    },
    "company": KEEP,
    "location": KEEP,
    "content": KEEP,
    "metadata": {"date_added": S, "date_updated": S},
}

ENDPOINT_SPECS: dict[str, Spec] = {
    "/company/identify": [
        {
            "matched_on": S,
            "match_type": S,
            "matches": [
                {
                    "confidence_score": S,
                    "company_data": {
                        "crustdata_company_id": S,
                        "basic_info": COMPANY_BASIC,
                        "social_profiles": KEEP,
                    },
                }
            ],
        }
    ],
    "/company/enrich": [
        {
            "matched_on": S,
            "match_type": S,
            "matches": [{"confidence_score": S, "company_data": COMPANY_RECORD}],
        }
    ],
    "/company/search": {"companies": [COMPANY_RECORD], "next_cursor": S, "total_count": S},
    "/person/search": {"profiles": [PERSON_PROFILE], "next_cursor": S, "total_count": S},
    "/job/search": {"job_listings": [JOB_LISTING], "next_cursor": S, "total_count": S},
    "/web/search/live": {
        "success": S,
        "query": S,
        "timestamp": S,
        "results": [
            {
                "source": S,
                "title": TEXT,
                "url": S,
                "snippet": TEXT,
                "position": S,
                "metadata": KEEP,
                "content": TEXT,
            }
        ],
        "metadata": KEEP,
    },
    "/web/enrich/live": [
        {"success": S, "url": S, "timestamp": S, "title": TEXT, "content": TEXT},
    ],
}


def sanitize_response(endpoint: str, data: Any) -> Any:
    """Allowlisted, contact-free view of one endpoint's response body."""
    spec = ENDPOINT_SPECS.get(endpoint)
    if spec is None:
        return _clean_tree(data)
    return apply_spec(spec, data)
