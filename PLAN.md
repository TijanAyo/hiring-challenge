# PLAN.md

The system turns `(company_name, mailing_address)` into a verified decision-maker contact, and treats "cannot verify" as a valid result. Precision is the hard constraint; coverage is maximized under it. In debt collection under a client's brand, a wrong contact is a brand and legal risk, while a missed one is cheap human review. The design is built to abstain before it guesses.

## Architecture

A six-stage pipeline.

1. **Ingest & normalize** — Parse the CSV. Keep the original company name, and build a normalized form (strip `LLC`/`Co`/punctuation) for matching. Split the mailing address into components and derive the state, which routes registry lookups.
2. **Entity resolution** — Match each row to one real business before looking for any person. Query sources by normalized name + state, then score each candidate against the input address. A weak match returns the outcome "company not resolved" rather than a forced guess.
3. **Enrichment fan-out** — Query the source tiers in parallel as queued jobs. Each returns claims tagged with source and timestamp. Per-source rate limits, timeouts, and retries. An idempotency key per `(company, source)` keeps re-runs from duplicating work.
4. **Aggregation** — Merge claims, dedupe people, cross-corroborate, compute the confidence score, attach per-field provenance, and select the best contact by the persona rule.
5. **Decision gate** — Apply the confidence threshold, set `needs_human_review`, and assign an outcome state.
6. **Output & review queue** — Emit one record per input row with the required fields plus provenance. Route uncertain rows to a human queue.

Sources sit behind one interface (`lookup(entity) -> Claim[]`) so mock and real providers swap freely. Results are cached per company to avoid re-querying, and every meaningful step is logged with context.

## Sources & strategy

No single source closes the gap, so the system fans out and cross-corroborates. Every contact has two halves, scored separately: **identity** (who, and their role) and **channel** (how to reach them). A complete contact needs both.

Source tiers, each with its failure mode:

- **A — Official registries** (Secretary of State / OpenCorporates): legal owner and officers. Fails when the registered agent is a formation service, or the entity is mismatched.
- **B — Business directories** (D&B, Google Business Profile, Yelp): a reach channel. Fails with generic `info@` inboxes, front-desk numbers, and stale data.
- **C — The business's own web/social**: often the only place a micro-business names its owner. Fails when there is no site.
- **D — LinkedIn**: people matched to a title (owner, office manager, AP). Fails on thin presence and fuzzy person-to-company matching.
- **E — Email inference + verification**: derives a channel from a known name + domain. Counts only when verification-gated, never as a raw guess.

Persona target: a size-keyed role chain. For micro-businesses with no finance function, the owner is the target. For larger SMBs, the AP or office manager is the target, with the owner as fallback. Every row in the sample dataset is a micro-business, so the working default is owner-first.

Confidence rises with source trust and with independent corroboration. Sources that copy from a shared upstream are treated as one, not several.

## Quality

**Confidence** is two factors multiplied:

`confidence = entity_match_gate × contact_evidence`

The entity gate is a multiplier: if the system is unsure it matched the right business, the whole score collapses. Contact evidence combines independent, credible sources that assert the same value:

`contact_evidence = 1 − ∏(1 − rₛ)`

This reads as the chance that every source is wrong at once. Junk sources barely move it, agreement raises it with diminishing returns, and it never reaches 100, because certainty is never claimed.

Each source's reliability `rₛ = source_prior × per_claim_check`. The prior reflects whether the source is primary or a copy, verifiable, structured, and fresh. The per-claim check tests the actual value: an email passes syntax, mail-server, and deliverability checks and is downgraded on catch-all domains; a phone passes a live line-type lookup; a person-to-company link is recent; the source address agrees with the input. Priors are calibrated against a small set of known-answer companies, not set by feel.

**Provenance**: every output field stores its source(s), timestamp, and an evidence reference. The output `source` column is the flattened view of this.

**Dedupe**: input-side, name and address variants collapse to one entity; output-side, the same person found across sources merges into one contact, which raises confidence through corroboration instead of creating duplicates.

**Cannot-verify states**, all valid and never fabricated: verified contact; found-but-low-confidence (surfaced so the reviewer has a head start); company resolved with no contact; company not resolved.

**False-positive risk** is the failure to avoid: the wrong entity, the right company with the wrong person, or a guessed email that reads as valid on a catch-all domain. Defenses: require corroboration before high confidence, gate channels on verification, and abstain by default. Anything below the threshold, or any unresolved step, sets `needs_human_review`.

## Privacy / compliance

This is debt collection under the client's brand, so the bar stays high even where B2B law is loose.

The system **will** use public business information only, target business contacts in a business capacity, keep full provenance for auditability, respect robots.txt / terms / rate limits, verify before surfacing, honor opt-outs, and store only what is needed to reach the right person.

The system **will not** scrape or store personal PII such as home addresses or personal cell numbers, use breach or grey-market data, bypass terms or auth walls, emit unverified inferred contacts, or contact third parties unrelated to the business.

Allowed sources cap both coverage and confidence, so the compliance line is confirmed before any inference source is relied on.

## Clarifying questions

**1. What is the cost of one wrong contact compared to one row sent to human review?**
- Why it matters: the confidence threshold is arbitrary without the error-cost ratio, and that ratio sets the entire precision-versus-coverage balance.
- Default assumption: a false positive is far more costly than a human review, so the threshold is set high and the system abstains freely.
- What changes if answered: the exact threshold value, and how hard the system chases coverage inside the precision bound.

**2. Are inferred-then-verified emails acceptable, and are personal or direct contacts such as an owner's cell number in or out of bounds?**
- Why it matters: this decides whether the inference source exists at all and where the privacy line sits, which drives both coverage and architecture.
- Default assumption: inference is used only when verification-gated and marked low-confidence; no personal cell numbers; public business data only.
- What changes if answered: whether the inference tier ships, the coverage ceiling, and the channel confidence weights.

**3. Will these contacts be auto-contacted by your AI agents, or queued for a human to send?**
- Why it matters: auto-contact under the client's brand demands a far stricter precision bar and abstain threshold than a human-reviewed send.
- Default assumption: a human reviews before any outreach.
- What changes if answered: how conservative the threshold and the abstain gate are set.
