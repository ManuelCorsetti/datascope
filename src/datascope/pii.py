"""
Heuristic detection of personal and sensitive data in columns:

* PII — personally identifiable information: names, emails, phone
  numbers, addresses, national ID numbers, dates of birth, ...
* PHI — personal health information: medical record numbers, diagnoses,
  medications, health-insurance IDs.
* PCI — payment data: credit card and bank account numbers.

The report calls these "personal & sensitive data" and shows the plain
labels below (GROUP_LABELS / TYPE_LABELS) plus the reasons a column was
flagged; the acronyms stay in the profile dict for programmatic use.

Two independent signals are combined into one confidence score per column:
  1. Column NAME matched against curated keyword patterns per category.
  2. Column CONTENT sampled and matched against regexes (email, phone,
     national ID, IP address, card numbers with a Luhn check, IBAN).

This is heuristic pattern-matching, not a compliance tool — it exists to
surface columns worth a human review, not to make that decision for you.
Categories/patterns are plain data below, so it's easy to extend.

Note on "PSI": the request that generated this module said "PII or PSI" —
there's no standard data-governance acronym "PSI", so this treats it as
almost certainly meaning PHI (Protected Health Information), the standard
pairing with PII. A "PHI" category is included below; rename/extend the
dicts if something else was meant.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

import pandas as pd

def _w(core: str) -> str:
    """Word-boundary wrapper for normalized (underscore-joined) column
    names. Python's \\b treats '_' as a word character, so it will NOT
    match the boundary in e.g. "shipping_address" — only '^', '$', and
    '_' itself are valid token separators here."""
    return r"(?:^|_)(?:" + core + r")(?:_|$)"


# category -> (group, [regex fragments matched against the normalized column name])
# Patterns wrapped in _w() require a whole underscore-delimited token match
# (so "shipping_address" matches "address" but "database" does not).
# Bare patterns are intentionally loose substring matches for compounds
# that already include their own separator, e.g. "credit_?card" also
# catches "credit_card_number".
NAME_PATTERNS: Dict[str, Tuple[str, List[str]]] = {
    # deliberately no bare "name" pattern here — it's too broad (would
    # flag domain_name, file_name, table_name, product_name, ...);
    # only compound forms that plausibly mean a *person's* name count.
    "full_name": ("PII", [_w("full_?name"), _w("first_?name"), _w("last_?name"),
                           _w("sur_?name"), _w("middle_?name"), _w("customer_?name"),
                           _w("client_?name"), _w("contact_?name"), _w("given_?name")]),
    "email": ("PII", [r"e.?mail"]),
    "phone": ("PII", [r"phone", _w("mobile"), _w("telephone"), _w("cell_?number")]),
    # ip_address must come before address: "ip_address" also matches the
    # "address" token, and equal name scores go to the first category listed.
    "ip_address": ("PII", [_w("ip_?address"), r"^ip$"]),
    "address": ("PII", [_w("address"), _w("street"), _w("zip_?code"), _w("postal_?code"),
                         _w("postcode")]),
    "national_id": ("PII", [_w("ssn"), r"social_?security", r"national_?id", _w("tax_?id"),
                             _w("nino"), r"passport", r"driver.?s?_?licen[sc]e"]),
    "date_of_birth": ("PII", [_w("dob"), r"date_?of_?birth", r"birth_?date"]),
    "username_login": ("PII", [r"user_?name", _w("login")]),
    "gender": ("PII", [_w("gender"), _w("sex")]),
    "medical_record": ("PHI", [r"medical_?record", _w("mrn"), r"patient_?id", _w("patient")]),
    "diagnosis": ("PHI", [r"diagnos", _w("icd"), r"condition", _w("symptom")]),
    "medication": ("PHI", [r"medication", _w("drug_?name"), r"prescription", _w("dosage")]),
    "health_plan": ("PHI", [r"health_?plan", r"insurance_?id", _w("policy_?number")]),
    "credit_card": ("PCI", [r"credit_?card", _w("card_?number"), _w("cvv"), _w("pan")]),
    "bank_account": ("PCI", [r"bank_?account", _w("iban"), r"routing_?number",
                              _w("account_?number"), r"sort_?code"]),
}

# category -> (compiled regex, group)
# The phone pattern excludes bare ISO-date shapes (YYYY-MM-DD) via a
# negative lookahead — otherwise a plain date column serialized to text
# ("2024-10-11") is digit-dash-shaped enough to look like a phone number.
# Order matters for ties (equal scores go to the first listed): the
# national-ID shape is a special case of the looser phone shape, so it
# comes first.
CONTENT_PATTERNS: Dict[str, Tuple[re.Pattern, str]] = {
    "email": (re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"), "PII"),
    "national_id": (re.compile(r"^\d{3}-?\d{2}-?\d{4}$"), "PII"),
    "phone": (re.compile(r"^(?!\d{4}-\d{2}-\d{2}$)\+?[\d][\d\-.\s()]{7,16}\d$"), "PII"),
    "ip_address": (re.compile(r"^(\d{1,3}\.){3}\d{1,3}$"), "PII"),
    "credit_card": (re.compile(r"^[\d\-\s]{13,23}$"), "PCI"),
    "bank_account": (re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$"), "PCI"),
}

# Patterns specific enough to look for *inside* free text ("call me at
# ann@x.com"), not just as the whole value. Looser shapes (phone numbers,
# undashed IDs) stay whole-value only: numbers in prose are too common.
EMBEDDED_PATTERNS: Dict[str, re.Pattern] = {
    "email": re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}(?![\w-])"),
    "national_id": re.compile(r"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])"),
}

# Default share of sampled values that must match a pattern for a column
# to be flagged (Settings.sensitive_min_match_pct). Deliberately low:
# a column that is only partly personal data still holds personal data.
DEFAULT_MIN_MATCH_RATE = 0.01

# Plain-language names used in the report, alerts and reasons.
GROUP_LABELS: Dict[str, str] = {"PII": "Personal data", "PHI": "Health data", "PCI": "Payment data"}
TYPE_LABELS: Dict[str, str] = {
    "full_name": "person's name", "email": "email address", "phone": "phone number",
    "address": "postal address", "national_id": "national ID number (e.g. SSN, passport)",
    "date_of_birth": "date of birth", "ip_address": "IP address", "username_login": "username or login",
    "gender": "gender information", "medical_record": "medical record or patient ID", "diagnosis": "diagnosis or condition",
    "medication": "medication or prescription", "health_plan": "health insurance ID",
    "credit_card": "credit card number", "bank_account": "bank account number",
}

NAME_WEIGHT = 0.55
CONTENT_WEIGHT = 0.5
# A passed checksum (currently: Luhn for credit cards) is real corroborating
# evidence a bare shape-regex match doesn't have -- e.g. a pure 16-digit
# string satisfies both the credit_card AND phone patterns (phone's char
# class permits unbroken digit runs too), so without this bonus a category
# with no validation at all could win the tie purely on dict iteration
# order, which is exactly backwards.
CHECKSUM_VALIDATED_BONUS = 0.05


def _luhn_valid(number_str: str) -> bool:
    digits = [int(ch) for ch in number_str if ch.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, d in enumerate(digits):
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _iban_valid(value: str) -> bool:
    """ISO 13616 mod-97 check: random codes that merely look like an IBAN
    (two letters, two digits, ...) almost always fail it."""
    s = value.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    rearranged = s[4:] + s[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


_VALIDATORS = {"credit_card": _luhn_valid, "bank_account": _iban_valid}


def _match_name(col_name: str) -> List[Tuple[str, str]]:
    normalized = re.sub(r"[^a-z0-9]+", "_", col_name.lower()).strip("_")
    matches = []
    for category, (group, patterns) in NAME_PATTERNS.items():
        for p in patterns:
            if re.search(p, normalized):
                matches.append((category, group))
                break
    return matches


def _match_content(series: pd.Series, sample_size: int, random_state: int,
                   min_match_rate: float = DEFAULT_MIN_MATCH_RATE) -> List[Tuple[str, str, float, bool, int, bool]]:
    """-> (category, group, match rate, checksum-validated, values sampled,
    found inside text rather than as the whole value) per matching pattern."""
    non_null = series.dropna().astype(str).str.strip()
    non_null = non_null[non_null != ""]
    if non_null.empty:
        return []
    sample = non_null if len(non_null) <= sample_size else non_null.sample(sample_size, random_state=random_state)

    results = []
    for category, (regex, group) in CONTENT_PATTERNS.items():
        whole = sample.apply(lambda v: bool(regex.match(v)))
        inside = pd.Series(False, index=sample.index)
        if category in EMBEDDED_PATTERNS:
            pattern = EMBEDDED_PATTERNS[category]
            inside = ~whole & sample.apply(lambda v: bool(pattern.search(v)))
        rate = float((whole | inside).mean())
        if rate == 0 or rate < min_match_rate:
            continue
        validated = False
        if category in _VALIDATORS:
            candidates = sample[whole]
            valid_rate = float(candidates.apply(_VALIDATORS[category]).mean()) if len(candidates) else 0.0
            if valid_rate < 0.5:
                continue  # the right shape but fails the checksum -> probably just another code
            validated = True
        results.append((category, group, round(rate, 3), validated, len(sample), bool(inside.sum() > whole.sum())))
    return results


def detect_sensitive_data(series: pd.Series, col_name: str, sample_size: int = 1000,
                           random_state: int = 42, skip_content: bool = False,
                           min_match_rate: float = DEFAULT_MIN_MATCH_RATE) -> Dict[str, Any]:
    """skip_content: set True for columns already known (from semantic
    typing) to be datetime or boolean — their string form isn't
    meaningful input for these content regexes, only the column name is.
    min_match_rate: share of sampled values (0-1) that must match a
    pattern for the values alone to flag the column."""
    name_matches = _match_name(col_name)
    content_matches = [] if skip_content else _match_content(series, sample_size, random_state, min_match_rate)

    if not name_matches and not content_matches:
        return {"is_sensitive": False, "category": None, "type": None, "confidence": 0.0, "detected_by": [],
                "category_label": None, "type_label": None, "reasons": []}

    scores: Dict[str, Dict[str, Any]] = {}
    for category, group in name_matches:
        entry = scores.setdefault(category, {"group": group, "score": 0.0, "by": set()})
        entry["score"] += NAME_WEIGHT
        entry["by"].add("column_name")

    content_detail: Dict[str, Tuple[float, bool, int, bool]] = {}
    for category, group, rate, validated, n_sampled, inside_text in content_matches:
        entry = scores.setdefault(category, {"group": group, "score": 0.0, "by": set()})
        entry["score"] += CONTENT_WEIGHT * rate + (CHECKSUM_VALIDATED_BONUS if validated else 0.0)
        entry["by"].add("content_pattern")
        content_detail[category] = (rate, validated, n_sampled, inside_text)

    best_key = max(scores, key=lambda k: scores[k]["score"])
    best = scores[best_key]
    confidence = min(round(best["score"], 2), 0.99)

    return {
        "is_sensitive": True,
        "category": best["group"],   # PII / PHI / PCI
        "type": best_key,            # e.g. "email", "diagnosis", "credit_card"
        "confidence": confidence,
        "detected_by": sorted(best["by"]),
        "category_label": GROUP_LABELS.get(best["group"], best["group"]),
        "type_label": TYPE_LABELS.get(best_key, best_key.replace("_", " ")),
        "reasons": _reasons(best_key, best["by"], content_detail.get(best_key)),
    }


def _with_article(label: str) -> str:
    if label.endswith("information"):
        return label
    return ("an " if label[0].lower() in "aeio" else "a ") + label


def _reasons(category: str, by: Any, content: Any) -> List[str]:
    """Why a column was flagged, in plain sentences (no values quoted)."""
    label = _with_article(TYPE_LABELS.get(category, category.replace("_", " ")))
    reasons = []
    if "column_name" in by:
        reasons.append(f"Its name suggests it holds {label}.")
    if "content_pattern" in by and content:
        rate, validated, n_sampled, inside_text = content
        pct = f"{rate * 100:.0f}%" if rate >= 0.01 else f"{rate * 100:.1f}%"
        what = f"contain {label}" if inside_text else f"have the format of {label}"
        reasons.append(f"{pct} of {n_sampled:,} sampled values {what}"
                       + (" and pass its checksum." if validated else "."))
    return reasons


# Order statistics are values from individual rows (the minimum of an SSN
# column is somebody's SSN; the IQR fences give back q1 and q3), so a
# flagged column doesn't keep them. Aggregates such as mean, sum, range and
# counts describe no single row and stay.
_NUMERIC_ORDER_STATS = ("min", "q1", "median", "q3", "max", "lower_fence", "upper_fence")


def mask_column_profile(profile: Dict[str, Any]) -> None:
    """Hide a flagged column's row-level values, in place: mask its top
    values and drop its order statistics, its numeric histogram (whose
    outer edges are the min and max) and its earliest / latest date. Call
    it before deriving quality rules or dbt tests from the profile."""
    profile["top_values"] = [{**tv, "value": mask_value(tv["value"])} for tv in profile.get("top_values") or []]
    ns = profile.get("numeric_stats")
    if ns:
        for key in _NUMERIC_ORDER_STATS:
            if key in ns:
                ns[key] = None
    if profile.get("histogram"):
        profile["histogram"] = None
    ds = profile.get("datetime_stats")
    if ds:
        for key in ("min_date", "max_date"):
            if key in ds:
                ds[key] = None


def mask_value(value: Any) -> str:
    """Mask a single value for safe display in the report. Email-aware,
    otherwise shows only the first/last character."""
    s = str(value)
    if s == "" or s.lower() == "nan":
        return s
    if "@" in s:
        local, _, domain = s.partition("@")
        tld = domain.split(".")[-1] if "." in domain else ""
        return (local[0] if local else "*") + "***@***" + (("." + tld) if tld else "")
    if len(s) <= 4:
        return "*" * len(s)
    return s[0] + "*" * (len(s) - 2) + s[-1]
