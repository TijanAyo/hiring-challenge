# Contact Finder

Given a list of small businesses (company name + mailing address), find the best
decision-maker to contact about an unpaid invoice, and, just as importantly,
say "I don't know" when the evidence isn't good enough.

This is built **precision-first**: it would rather route a row to a human than
hand over a confident-looking wrong contact. In branded debt collection a wrong
contact is a legal and reputational risk; a missed one is cheap human review.

## Run it

From the repo root:

```bash
python find_contacts.py
```

It reads `challenge/data/companies.csv` and the mock providers in
`challenge/mocks/enrichment_responses.json`, then prints one row per company plus
a summary (how many were verified vs routed to human review).

No external dependencies — standard library only.

## How confidence works

Each contact gets a 0–100 score:

```
confidence = entity_gate x identity x channel
```

- **identity** (who the person is): `1 - product(1 - r)` across the sources that
  agree on the name. Independent agreement raises it; it never reaches 100.
  Conflicting names trigger a penalty instead of a boost.
- **channel** (how to reach them): the strongest available email/phone. Generic
  inboxes (`info@`, `office@`) are penalised; the enrichment provider's
  self-reported confidence feeds in but is never trusted blindly.
- **entity_gate**: 1.0 here, because the mock is keyed by exact company name, so
  a hit is the right business. In production this would be address matching.

Below the **70** threshold, the contact channel is blanked and
`needs_human_review` is set — the name/role are kept as a head start for the
reviewer, but no unverified contact is emitted.

Every weight lives at the top of `find_contacts.py`, so the whole trust model is
readable and tunable in one place.

## Key decisions

- **Precision over recall.** A high `needs_human_review` rate on genuinely hard
  rows is the intended result, not a failure.
- **Never fabricate.** A value is only emitted if it traces back to at least one
  `source_url`; uncertain rows are blanked, not guessed.
- **Corroboration drives trust.** The same person from independent sources scores
  higher. Name variants merge (e.g. "Bob Kowalski" / "Robert Kowalski",
  "S. Murphy" / "Sean Murphy") via a surname key; conflicting names lower the score.
- **Decision-maker priority ladder.** AP / accounts payable → owner/founder →
  CFO/finance → office manager
- **Provenance throughout.** Every value carries its source through to the output.

## Output fields

| field | meaning |
|---|---|
| `contact_name`, `contact_role` | who we believe to contact (kept even when unsure) |
| `contact_email_or_phone` | the channel — blank when `needs_human_review` is true |
| `confidence_score` | 0–100, computed as above |
| `source` | the `source_url`s the answer was drawn from |
| `needs_human_review` | true when confidence is below the threshold |
