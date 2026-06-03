"""
Reads companies from the CSV, queries the three mock providers, and for each
company returns the best decision-maker contact with a confidence score, the
provenance, and an honest needs_human_review flag.

    confidence = entity_gate x identity x channel
    identity   = 1 - product(1 - r) over agreeing name sources  (corroboration)
    below 70   -> blank the contact channel AND flag for human review

Run from the repo root:  python find_contacts.py
"""

import csv
import json
from dataclasses import dataclass

DATA_CSV = "challenge/data/companies.csv"
MOCK_JSON = "challenge/mocks/enrichment_responses.json"

# Tunable weights
R_REGISTRY = 0.85  # registry is authoritative-ish for "who"
R_LISTING = 0.60  # web/maps listing, weaker
R_IDENTITY_UNKNOWN = 0.30  # found a channel but no actual person name
CONFLICT_PENALTY = 0.60  # sources name DIFFERENT people -> trust drops
LISTING_PHONE_R = 0.55  # a generic business line from a listing
ENRICHMENT_PHONE_FACTOR = 0.80  # enrichment phone slightly below its email
GENERIC_EMAIL_PENALTY = 0.50  # info@ / office@ is not a specific person
THRESHOLD = 70

# Priority ladder AP first, then owner/founder, then CFO, then manager;
# "registered agent" is a formation service stand-in, NOT a decision-maker.
ROLE_WEIGHTS = {
    "accounts payable": 1.00,
    "ap manager": 1.00,
    "owner": 1.00,
    "founder": 1.00,
    "president": 1.00,
    "ceo": 1.00,
    "cfo": 0.95,
    "finance": 0.95,
    "manager": 0.85,
    "office manager": 0.85,
    "registered agent": 0.30,
}
ROLE_DEFAULT = 0.70  # role missing or unrecognised
GENERIC_LOCALPARTS = {
    "info",
    "office",
    "contact",
    "sales",
    "admin",
    "hello",
    "support",
    "team",
}
NAME_TITLES = ("dr ", "mr ", "mrs ", "ms ")


@dataclass
class NameClaim:
    name: str
    role: str
    reliability: float


@dataclass
class ChannelOption:
    value: str
    reliability: float


# ---- Helpers --------------------------------------------------------------
def role_weight(role):
    if not role:
        return ROLE_DEFAULT
    return ROLE_WEIGHTS.get(role.strip().lower(), ROLE_DEFAULT)


def surname(name):
    """A cheap, explainable name key: strip titles and parenthetical notes,
    then take the last word. 'Sean Murphy' and 'S. Murphy' both become
    'murphy', so they match. Real systems need fuzzier matching."""
    if not name:
        return ""
    cleaned = name.lower().replace(".", " ")
    for title in NAME_TITLES:
        cleaned = cleaned.replace(title, " ")
    cleaned = cleaned.split("(")[0]  # drop a "(manager)" style note
    words = cleaned.split()  # split() also discards blank pieces
    if not words:
        return ""
    return words[-1]


def combine(reliabilities):
    """1 - product(1 - r): the chance at least one independent source is right."""
    product_wrong = 1.0
    for r in reliabilities:
        product_wrong = product_wrong * (1 - r)
    return 1 - product_wrong


def collect_name_claims(sources):
    """Pull every name the providers gave us, each with its reliability."""
    claims = []
    registry = sources.get("registry")
    if registry and registry.get("name"):
        claims.append(NameClaim(registry["name"], registry.get("role"), R_REGISTRY))
    listing = sources.get("listing")
    if listing and listing.get("name"):
        claims.append(NameClaim(listing["name"], listing.get("role"), R_LISTING))
    return claims


def group_by_surname(claims):
    """Group name claims so the same person (despite spelling) lands together."""
    groups = {}
    for claim in claims:
        key = surname(claim.name)
        if key not in groups:
            groups[key] = []
        groups[key].append(claim)
    return groups


def strongest_group(groups):
    """Return the surname group with the best combined reliability."""
    best_group = None
    best_strength = -1.0
    for group in groups.values():
        strength = combine([claim.reliability for claim in group])
        if strength > best_strength:
            best_strength = strength
            best_group = group
    return best_group, best_strength


def longest_name(group):
    """The fullest spelling we saw, e.g. 'Sean Murphy' over 'S. Murphy'."""
    best = ""
    for claim in group:
        if len(claim.name) > len(best):
            best = claim.name
    return best


def first_role(group):
    """The first real role any source gave for this person."""
    for claim in group:
        if claim.role:
            return claim.role
    return ""


def pick_identity(sources):
    """Decide WHO the contact is, and how confident we are in that."""
    claims = collect_name_claims(sources)
    if not claims:
        # No name at all (maybe only a generic enrichment email).
        return "", "", R_IDENTITY_UNKNOWN

    groups = group_by_surname(claims)
    group, strength = strongest_group(groups)

    # If providers named DIFFERENT people, that is a conflict -> trust drops.
    if len(groups) > 1:
        strength = strength * CONFLICT_PENALTY

    person_name = longest_name(group)
    person_role = first_role(group)
    identity = strength * role_weight(person_role)
    return person_name, person_role, identity


def collect_channels(sources):
    """Pull every way-to-reach-them the providers gave us, with reliabilities."""
    options = []
    enrichment = sources.get("enrichment")
    if enrichment:
        provider_conf = enrichment.get("provider_confidence", 0) / 100
        email = enrichment.get("email")
        if email:
            local_part = email.split("@")[0].lower()
            reliability = provider_conf
            if local_part in GENERIC_LOCALPARTS:
                reliability = reliability * GENERIC_EMAIL_PENALTY
            options.append(ChannelOption(email, reliability))
        phone = enrichment.get("phone")
        if phone:
            options.append(
                ChannelOption(phone, provider_conf * ENRICHMENT_PHONE_FACTOR)
            )
    listing = sources.get("listing")
    if listing and listing.get("phone"):
        options.append(ChannelOption(listing["phone"], LISTING_PHONE_R))
    return options


def pick_channel(sources):
    """Decide the best way to reach them, and how confident we are in it."""
    best = ChannelOption("", 0.0)
    for option in collect_channels(sources):
        if option.reliability > best.reliability:
            best = option
    return best.value, best.reliability


def collect_provenance(sources):
    """Every source_url we drew from, for traceability."""
    return [
        provider["source_url"]
        for provider in sources.values()
        if provider.get("source_url")
    ]


def score_company(company_name, sources):
    if not sources:
        return build_row(company_name)  # nothing found -> not resolved -> review

    person_name, person_role, identity = pick_identity(sources)
    contact_value, channel = pick_channel(sources)

    # entity_gate is 1.0 here: the mock is keyed by exact company name, so a hit
    # IS the right business. In production this comes from address matching.
    confidence = round(100 * 1.0 * identity * channel)
    needs_review = confidence < THRESHOLD

    contact_to_emit = contact_value
    if needs_review:
        contact_to_emit = ""  # below threshold -> blank the channel

    return build_row(
        company_name,
        contact_name=person_name,
        contact_role=person_role,
        contact=contact_to_emit,
        confidence=confidence,
        source="; ".join(collect_provenance(sources)),
        needs_review=needs_review,
    )


def build_row(
    company,
    contact_name="",
    contact_role="",
    contact="",
    confidence=0,
    source="",
    needs_review=True,
):
    return {
        "company": company,
        "contact_name": contact_name,
        "contact_role": contact_role,
        "contact_email_or_phone": contact,
        "confidence_score": confidence,
        "source": source,
        "needs_human_review": needs_review,
    }


def load_company_names(path):
    with open(path) as f:
        return [record["company_name"] for record in csv.DictReader(f)]


def main():
    with open(MOCK_JSON) as f:
        mocks = json.load(f)
    company_names = load_company_names(DATA_CSV)

    rows = [score_company(name, mocks.get(name, {})) for name in company_names]
    verified = sum(1 for row in rows if not row["needs_human_review"])

    print(f"{'COMPANY':<28}{'CONTACT':<32}{'SCORE':<7}{'REVIEW'}")
    print("-" * 75)
    for row in rows:
        contact = row["contact_email_or_phone"] or "(blanked)"
        review = "yes" if row["needs_human_review"] else "NO"
        print(f"{row['company']:<28}{contact:<32}{row['confidence_score']:<7}{review}")
    print("-" * 75)
    print(
        f"{verified} verified / {len(rows)} companies "
        f"({len(rows) - verified} routed to human review)"
    )


if __name__ == "__main__":
    main()
