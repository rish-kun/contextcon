from datetime import date

from app.domain import Compatibility, FundingKind, FundingRecord, SearchScope
from app.rules.investors import funding_kind, rank_investors

SCOPE = SearchScope(
    sectors=["warehousing"], geographies=["India"], as_of=date(2026, 11, 22), companies_examined=20
)


def rec(
    id,
    investor_name=None,
    *,
    investor_id=None,
    when=date(2025, 6, 1),
    round_type="series_a",
    company="Co",
    sectors=("Warehousing",),
    country="India",
    domain=None,
    inv_country=None,
    inv_type=None,
    amount=1e6,
):
    return FundingRecord(
        id=id,
        company_id=f"cid-{company}",
        company_name=company,
        company_sectors=list(sectors),
        company_country=country,
        round_type=round_type,
        date=when,
        amount_usd=amount,
        investor_id=investor_id,
        investor_name=investor_name,
        investor_domain=domain,
        investor_country=inv_country,
        investor_type=inv_type,
        evidence_id=f"ev-{id}",
    )


def test_round_without_date_or_investor_excluded():
    r = rank_investors([rec("a", "Alpha", when=None), rec("b", None), rec("c", "Gamma")], SCOPE)
    assert {(x.record_id, x.reason) for x in r.excluded_records} == {
        ("a", "funding round has no date"),
        ("b", "no named investor"),
    }
    assert [i.name for i in r.investors] == ["Gamma"]


def test_merge_on_id_and_on_exact_name_with_corroboration():
    r = rank_investors(
        [
            rec("1", "Blue River Capital", investor_id="inv-1", domain="blueriver.vc", company="A"),
            rec("2", "Blue River Capital LLP", investor_id="inv-1", company="B"),
            # No id, exact name and same domain: merges into the id group.
            rec("3", "Blue River Capital", domain="https://www.blueriver.vc/", company="C"),
        ],
        SCOPE,
    )
    assert len(r.investors) == 1
    inv = r.investors[0]
    assert inv.investor_id == "inv-1"
    assert inv.comparable_count == 3
    assert inv.possible_duplicates == []


def test_same_name_without_corroboration_is_flagged_not_merged():
    r = rank_investors(
        [
            rec("1", "Orbit Ventures", investor_id="inv-9", domain="orbit.vc", company="A"),
            rec("2", "Orbit Ventures", domain="orbit-capital.in", company="B"),
            rec("3", "Orbit", company="C"),
        ],
        SCOPE,
    )
    assert len(r.investors) == 3
    flagged = {i.key: set(i.possible_duplicates) for i in r.investors}
    assert flagged["id:inv-9"] == {"rec:2", "rec:3"}
    assert all("not merged" in u for i in r.investors for u in i.unknowns if "May be" in u)


def test_recency_weighting():
    # Three rounds in 2021 lose to two recent rounds.
    r = rank_investors(
        [
            rec("old1", "Old Fund", investor_id="o", when=date(2021, 1, 1), company="A"),
            rec("old2", "Old Fund", investor_id="o", when=date(2021, 2, 1), company="B"),
            rec("old3", "Old Fund", investor_id="o", when=date(2021, 3, 1), company="C"),
            rec("new1", "New Fund", investor_id="n", when=date(2025, 9, 1), company="D"),
            rec("new2", "New Fund", investor_id="n", when=date(2026, 3, 1), company="E"),
        ],
        SCOPE,
    )
    assert [(i.name, i.comparable_count) for i in r.investors] == [
        ("New Fund", 2),
        ("Old Fund", 3),
    ]
    assert r.investors[0].score > r.investors[1].score


def test_outside_scope_is_not_comparable():
    r = rank_investors(
        [
            rec("a", "Fund", investor_id="f", when=date(2018, 1, 1), company="Too old"),
            rec("b", "Fund", investor_id="f", sectors=["Fintech"], company="Other sector"),
            rec("c", "Fund", investor_id="f", country="Kenya", company="Other country"),
            rec("d", "Fund", investor_id="f", when=date(2027, 1, 1), company="Future"),
        ],
        SCOPE,
    )
    assert r.investors == []


def test_latest_sector_investment_reports_scope():
    r = rank_investors(
        [
            rec("a", "Fund", investor_id="f", when=date(2024, 5, 1), company="A"),
            rec("b", "Fund", investor_id="f", when=date(2026, 2, 1), company="B", amount=None),
        ],
        SCOPE,
    )
    latest = r.investors[0].latest_sector_investment
    assert latest.date == date(2026, 2, 1) and latest.company_name == "B"
    assert "20 comparable companies" in latest.scope_note
    assert "warehousing" in latest.scope_note
    assert "Cheque size unknown for some rounds" in r.investors[0].unknowns


def test_funding_kind_compatibility():
    records = [
        rec("a", "Equity Fund", investor_id="e", round_type="Series B", company="A"),
        rec("b", "Debt Fund", investor_id="d", round_type="venture debt", company="B"),
        rec("c", "Mystery Fund", investor_id="m", round_type=None, company="C"),
    ]
    r = rank_investors(records, SCOPE, sought=FundingKind.VENTURE_EQUITY)
    compat = {i.name: i.compatibility for i in r.investors}
    assert compat == {
        "Equity Fund": Compatibility.COMPATIBLE,
        # Only debt rounds found: that is incomplete evidence, not a refusal.
        "Debt Fund": Compatibility.UNKNOWN,
        "Mystery Fund": Compatibility.UNKNOWN,
    }
    no_ask = rank_investors(records, SCOPE)
    assert {i.compatibility for i in no_ask.investors} == {Compatibility.UNKNOWN}


def test_funding_kind_mapping():
    assert funding_kind("Series A") is FundingKind.VENTURE_EQUITY
    assert funding_kind("Private Equity") is FundingKind.GROWTH_EQUITY
    assert funding_kind("Debt Financing") is FundingKind.DEBT
    assert funding_kind("grant") is FundingKind.GRANT
    assert funding_kind("undisclosed") is None


def test_ranking_is_deterministic_regardless_of_input_order():
    records = [
        rec("a", "A Fund", investor_id="a", company="X"),
        rec("b", "B Fund", investor_id="b", company="Y"),
        rec("c", "C Fund", company="Z"),
    ]
    one = rank_investors(records, SCOPE)
    two = rank_investors(list(reversed(records)), SCOPE)
    assert one == two
    assert [i.name for i in one.investors] == ["A Fund", "B Fund", "C Fund"]


# --- Merges: name and corroboration on the same record; identifiers decide -----


def test_name_and_corroboration_on_different_records_do_not_merge():
    r = rank_investors(
        [
            rec("1", "Blue River", investor_id="inv-1", company="A"),
            rec(
                "2",
                "Blue River Partners",
                investor_id="inv-1",
                inv_country="India",
                inv_type="VC",
                company="B",
            ),
            # Name matches record 1, country and type match record 2: not enough.
            rec("3", "Blue River", inv_country="India", inv_type="VC", company="C"),
        ],
        SCOPE,
    )
    assert sorted(i.key for i in r.investors) == ["id:inv-1", "rec:3"]


def test_name_and_corroboration_on_the_same_record_merge():
    r = rank_investors(
        [
            rec("1", "Blue River", investor_id="inv-1", inv_country="India", inv_type="VC"),
            rec("2", "Blue River", inv_country="India", inv_type="VC", company="B"),
        ],
        SCOPE,
    )
    assert [(i.key, i.comparable_count) for i in r.investors] == [("id:inv-1", 2)]


def test_conflicting_domain_in_the_group_blocks_a_name_merge():
    r = rank_investors(
        [
            rec(
                "1",
                "Blue River",
                investor_id="inv-1",
                domain="blueriver.vc",
                inv_country="India",
                inv_type="VC",
                company="A",
            ),
            rec(
                "2",
                "Blue River",
                domain="blueriver.in",
                inv_country="India",
                inv_type="VC",
                company="B",
            ),
        ],
        SCOPE,
    )
    assert sorted(i.key for i in r.investors) == ["id:inv-1", "rec:2"]
    flagged = {i.key: i.possible_duplicates for i in r.investors}
    assert flagged["rec:2"] == ["id:inv-1"]


def test_shared_domain_merges_directly_whatever_the_name():
    r = rank_investors(
        [
            rec("1", "Blue River Capital", investor_id="inv-1", domain="blueriver.vc"),
            rec("2", "BRC Fund II", domain="https://blueriver.vc/team", company="B"),
            rec("3", "BRC", domain="www.blueriver.vc", company="C"),
        ],
        SCOPE,
    )
    assert [(i.key, i.comparable_count) for i in r.investors] == [("id:inv-1", 3)]


# --- Compatibility: in-scope dated evidence only, never negative on gaps --------


def test_debt_search_on_a_seed_only_investor_is_unknown_not_incompatible():
    r = rank_investors(
        [rec("a", "Seed Fund", investor_id="s", round_type="seed")], SCOPE, FundingKind.DEBT
    )
    [inv] = r.investors
    assert inv.compatibility is Compatibility.UNKNOWN
    assert "compatibility with debt unknown" in inv.compatibility_reason


def test_compatibility_ignores_rounds_outside_the_scope():
    records = [
        rec("in", "Fund", investor_id="f", round_type="seed", company="A"),
        # Matching kind, but future-dated, too old, or outside the sector/geography.
        rec("future", "Fund", investor_id="f", round_type="venture debt", when=date(2027, 1, 1)),
        rec("old", "Fund", investor_id="f", round_type="venture debt", when=date(2018, 1, 1)),
        rec("sector", "Fund", investor_id="f", round_type="debt", sectors=["Fintech"]),
        rec("geo", "Fund", investor_id="f", round_type="debt", country="Kenya"),
    ]
    [inv] = rank_investors(records, SCOPE, FundingKind.DEBT).investors
    assert inv.compatibility is Compatibility.UNKNOWN
    in_scope_debt = [*records, rec("ok", "Fund", investor_id="f", round_type="venture debt")]
    [inv] = rank_investors(in_scope_debt, SCOPE, FundingKind.DEBT).investors
    assert inv.compatibility is Compatibility.COMPATIBLE
    assert inv.compatibility_reason.startswith(
        "1 debt round in the searched scope, latest 2025-06-01"
    )
