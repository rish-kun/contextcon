import json

from app.clients.crustdata import (
    COMPANY_ENRICH,
    COMPANY_IDENTIFY,
    COMPANY_SEARCH,
    JOB_SEARCH,
    PERSON_SEARCH,
    WEB_FETCH_LIVE,
    estimate_credits,
)
from app.clients.sanitize import sanitize_response


def test_person_search_keeps_only_allowlisted_fields_and_redacts_bios() -> None:
    data = {
        "profiles": [
            {
                "crustdata_person_id": 7,
                "basic_profile": {
                    "name": "R. Founder",
                    "headline": "CEO. Reach me at r.founder@corp.test or +91 98765 43210",
                    "current_title": "CEO",
                    # Not a contact-named key, so a key-name check alone kept it.
                    "reach": "r.founder@corp.test",
                },
                "contact_channels": {"primary": "+91 98765 43210"},
                "social_handles": {
                    "professional_network_identifier": {"profile_url": "https://pn.test/in/rf"},
                    "twitter_identifier": {"handle": "@rf"},
                },
                "experience": {
                    "employment_details": {
                        "current": [
                            {"name": "Acme", "crustdata_company_id": 4, "title": "CEO", "x": 1}
                        ],
                        "past": [],
                    }
                },
            }
        ],
        "next_cursor": None,
        "total_count": 1,
        "debug": {"owner_email": "ops@crustdata.test"},
    }
    out = sanitize_response(PERSON_SEARCH, data)
    dumped = json.dumps(out)
    assert "r.founder@corp.test" not in dumped
    assert "98765" not in dumped
    assert "debug" not in out and "contact_channels" not in out["profiles"][0]
    profile = out["profiles"][0]
    assert profile["basic_profile"]["headline"].startswith("CEO. Reach me at [redacted:email]")
    assert "reach" not in profile["basic_profile"]
    assert profile["social_handles"] == {
        "professional_network_identifier": {"profile_url": "https://pn.test/in/rf"}
    }
    assert profile["experience"]["employment_details"]["current"][0] == {
        "name": "Acme",
        "crustdata_company_id": 4,
        "title": "CEO",
    }


def test_fetched_pages_and_descriptions_are_redacted() -> None:
    pages = [
        {
            "success": True,
            "url": "https://acme.test/team",
            "title": "Team",
            "content": "<p>Write to ceo@acme.test or call +91 91234 56789.</p>",
            "raw_headers": {"x": "y"},
        }
    ]
    out = sanitize_response(WEB_FETCH_LIVE, pages)
    assert out[0]["url"] == "https://acme.test/team"
    assert "ceo@acme.test" not in out[0]["content"] and "91234" not in out[0]["content"]
    assert "raw_headers" not in out[0]

    company = [
        {
            "matches": [
                {
                    "company_data": {
                        "basic_info": {
                            "name": "Acme",
                            "primary_domain": "acme.test",
                            "description": "Founded 2014. Sales: sales@acme.test",
                        },
                        "people": {
                            "founders": [
                                {"name": "A", "title": "CEO", "contact": "a@acme.test", "x": 1}
                            ]
                        },
                        "unlisted_group": {"anything": 1},
                    }
                }
            ]
        }
    ]
    out = sanitize_response(COMPANY_ENRICH, company)
    data = out[0]["matches"][0]["company_data"]
    assert data["basic_info"]["primary_domain"] == "acme.test"
    assert "sales@acme.test" not in data["basic_info"]["description"]
    assert data["people"]["founders"] == [{"name": "A", "title": "CEO"}]
    assert "unlisted_group" not in data


def test_opaque_subtrees_lose_contact_keys_and_emails() -> None:
    data = {
        "job_listings": [
            {
                "crustdata_job_id": 1,
                "content": {"description": "Apply via hr@acme.test, ph +91 99887 76655"},
                "company": {"recruiter_phone": "1234", "basic_info": {"name": "Acme"}},
            }
        ]
    }
    out = sanitize_response(JOB_SEARCH, data)
    dumped = json.dumps(out)
    assert "hr@acme.test" not in dumped and "99887" not in dumped and "1234" not in dumped
    assert out["job_listings"][0]["company"] == {"basic_info": {"name": "Acme"}}


def test_credit_estimates_are_upper_bounds_from_published_prices() -> None:
    assert estimate_credits(COMPANY_IDENTIFY, {"domains": ["a", "b"]}) == 0.4
    assert estimate_credits(COMPANY_ENRICH, {"crustdata_company_ids": [1, 2, 3]}) == 6.0
    assert estimate_credits(WEB_FETCH_LIVE, {"urls": ["a", "b"]}) == 2.0
    assert estimate_credits(JOB_SEARCH, {"limit": 10}) == 0.3
    search = {"limit": 50, "fields": ["basic_info", "locations", "taxonomy"]}
    assert estimate_credits(COMPANY_SEARCH, search) == 50 * 0.13
