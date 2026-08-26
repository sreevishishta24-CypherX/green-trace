import re

DIST_RE = re.compile(r"(\d+(?:[\.,]\d+)?)\s*(m|metre|meters|metres|km)\b", re.IGNORECASE)
WITHIN_RE = re.compile(r"within\s*(\d+(?:[\.,]\d+)?)\s*(m|metre|meters|metres|km)\b", re.IGNORECASE)
FEATURE_RE = re.compile(r"\b(river|stream|waterbody|wetland|drain|drainage|lake)\b", re.IGNORECASE)
QUAL_RE_LIST = [
    (re.compile(r"adequate measures", re.IGNORECASE), "adequate measures"),
    (re.compile(r"no discharge|prevent discharge|prohibit discharge", re.IGNORECASE), "no discharge"),
    (re.compile(r"avoid alteration|alteration of natural drainage", re.IGNORECASE), "avoid alteration"),
    (re.compile(r"no development|no activity", re.IGNORECASE), "no development")
]


def _normalize_number(s: str) -> float:
    return float(s.replace(',', '.'))


def extract_clause_info(text: str) -> dict:
    """Extract simple buffer-related fields from a clause text.

    Returns: {numeric_distance: float|None, distance_unit: str|None, feature: str|None, qualitative_flag: str|None}
    """
    if not text:
        return {"numeric_distance": None, "distance_unit": None, "feature": None, "qualitative_flag": None}

    # Try direct distance matches
    m = DIST_RE.search(text)
    if not m:
        m = WITHIN_RE.search(text)

    numeric = None
    unit = None
    if m:
        try:
            numeric = _normalize_number(m.group(1))
            unit = m.group(2).lower()
        except Exception:
            numeric = None

    f = None
    fm = FEATURE_RE.search(text)
    if fm:
        f = fm.group(1).lower()

    q = None
    for pat, tag in QUAL_RE_LIST:
        if pat.search(text):
            q = tag
            break

    return {"numeric_distance": numeric, "distance_unit": unit, "feature": f, "qualitative_flag": q}


if __name__ == "__main__":
    samples = [
        "The project shall maintain a 100 metre buffer from the perennial river.",
        "No activity shall be carried out within 50 m of the stream.",
        "Adequate measures shall be taken to prevent discharge into nearby waterbodies."
    ]
    for s in samples:
        print(s)
        print(extract_clause_info(s))
