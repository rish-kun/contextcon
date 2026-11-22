"""Country values: Crustdata filters on country names ("India") but returns ISO 3166
alpha-3 codes ("IND") in `locations.country` (seen live, 2026-11-22).

`country_name` maps a code to the name the filter and autocomplete use. A code that is
not in the table is reported as unknown (None), so it can never produce a verified
must-have fail.
"""

from __future__ import annotations

import re

ISO3: dict[str, str] = {
    "ARE": "United Arab Emirates",
    "ARG": "Argentina",
    "AUS": "Australia",
    "AUT": "Austria",
    "BEL": "Belgium",
    "BGD": "Bangladesh",
    "BGR": "Bulgaria",
    "BHR": "Bahrain",
    "BRA": "Brazil",
    "BTN": "Bhutan",
    "CAN": "Canada",
    "CHE": "Switzerland",
    "CHL": "Chile",
    "CHN": "China",
    "COL": "Colombia",
    "CZE": "Czechia",
    "DEU": "Germany",
    "DNK": "Denmark",
    "EGY": "Egypt",
    "ESP": "Spain",
    "EST": "Estonia",
    "FIN": "Finland",
    "FRA": "France",
    "GBR": "United Kingdom",
    "GHA": "Ghana",
    "GRC": "Greece",
    "HKG": "Hong Kong",
    "HRV": "Croatia",
    "HUN": "Hungary",
    "IDN": "Indonesia",
    "IND": "India",
    "IRL": "Ireland",
    "ISR": "Israel",
    "ITA": "Italy",
    "JPN": "Japan",
    "KEN": "Kenya",
    "KOR": "South Korea",
    "KWT": "Kuwait",
    "LKA": "Sri Lanka",
    "LTU": "Lithuania",
    "LUX": "Luxembourg",
    "LVA": "Latvia",
    "MAR": "Morocco",
    "MEX": "Mexico",
    "MMR": "Myanmar",
    "MUS": "Mauritius",
    "MYS": "Malaysia",
    "NGA": "Nigeria",
    "NLD": "Netherlands",
    "NOR": "Norway",
    "NPL": "Nepal",
    "NZL": "New Zealand",
    "OMN": "Oman",
    "PAK": "Pakistan",
    "PER": "Peru",
    "PHL": "Philippines",
    "POL": "Poland",
    "PRT": "Portugal",
    "QAT": "Qatar",
    "ROU": "Romania",
    "RUS": "Russia",
    "SAU": "Saudi Arabia",
    "SGP": "Singapore",
    "SRB": "Serbia",
    "SVK": "Slovakia",
    "SVN": "Slovenia",
    "SWE": "Sweden",
    "THA": "Thailand",
    "TUR": "Turkey",
    "TWN": "Taiwan",
    "TZA": "Tanzania",
    "UGA": "Uganda",
    "UKR": "Ukraine",
    "USA": "United States",
    "VNM": "Vietnam",
    "ZAF": "South Africa",
}

_CODE = re.compile(r"^[A-Z]{2,3}$")


def country_name(value: object) -> str | None:
    """The country name for a provider value; None when it is an unknown code."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if _CODE.match(text):
        return ISO3.get(text)
    return text
