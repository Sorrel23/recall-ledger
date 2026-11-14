import json
import os
import re
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico",
}
# Two-letter codes that are also common English words; only trusted inside a code list.
AMBIGUOUS = {"IN", "OR", "ME", "OK", "HI", "DE", "PA", "MA", "AL", "CO", "ID", "LA", "MO", "OH", "SD", "ND"}
NAME_TO_CODE = {v.lower(): k for k, v in STATES.items()}
NATIONWIDE_RE = re.compile(r"nation\s?wide|nationally|throughout the (u\.?s\.?|united states)|all (50 )?states|\bus-wide", re.I)


def load_config():
    with open(os.path.join(ROOT, "config.json")) as f:
        return json.load(f)


def slugify(s, maxlen=90):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:maxlen].rstrip("-") or "item"


def extract_states(text):
    """Return (sorted state codes, nationwide flag) from an FDA distribution_pattern."""
    if not text:
        return [], False
    found = set()
    low = text.lower()
    for name, code in NAME_TO_CODE.items():
        if re.search(r"\b" + re.escape(name) + r"\b", low):
            # 'washington' alone could be DC; accept as WA unless 'washington, dc'/'d.c.'
            if code == "WA" and re.search(r"washington,?\s*d\.?c", low):
                continue
            if code == "VA" and "west virginia" in low and not re.search(r"(?<!west )\bvirginia\b", low):
                continue
            if code == "KS" and "arkansas" in low and not re.search(r"(?<!ar)kansas\b", low):
                continue
            found.add(code)
    # code lists like "VA, NY, NJ, MI" or "AL AK AZ"
    toks = [(m.group(), m.start(), m.end()) for m in re.finditer(r"\b[A-Z]{2}\b", text)]
    for i, (c, s, en) in enumerate(toks):
        if c not in STATES:
            continue
        if c in AMBIGUOUS:
            # trust only when a neighbouring token is another state code, joined by a
            # list separator (or by a space when the neighbour is unambiguous)
            ok = False
            for j in (i - 1, i + 1):
                if 0 <= j < len(toks) and toks[j][0] in STATES:
                    a, b = (toks[j][2], s) if j < i else (en, toks[j][1])
                    sep = text[a:b]
                    if re.fullmatch(r"\s*([,;/&]|and)\s*(and\s+)?", sep, re.I) or (
                            sep.strip() == "" and toks[j][0] not in AMBIGUOUS):
                        ok = True
            if not ok:
                continue
        found.add(c)
    nationwide = bool(NATIONWIDE_RE.search(text))
    return sorted(found), nationwide
