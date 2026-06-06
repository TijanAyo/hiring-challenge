# ABOUT.md

## Why this role

First off what AgentCollect is building is an awesome application of voice AI, one I haven't really seen before. I'm currently building something similar in the voice AI space myself, using an adjacent version of the tools the team is working with (more on this in *Your last project* below, I've also attached a Loom of what I built).

What also brought this role to my attention is that I've got prior experience working at a startup in loan collection, we worked with mandates and the payment infrastructure to process loans/debts. AgentCollect taking an agent approach to this genuinely grabbed my attention.

While I was there, I worked on a system called Karma, an internal service that checks whether a user taking a loan has a bad record. Those records were kept up to date by a network of businesses using the tool, once it went public.

Bringing all of these together, I believe I'd be a good fit for this role.

## How you work with AI tools

I treat AI like a partner, part fast junior/senior dev that writes solid code most of the time, and part solutions engineer to think problems through with.

My approach is plan-first. Faced with a problem, I make myself understand it before anything else, then write out a detailed plan that covers the edge cases — rather than prompting and patching on the go. Spending that time up front keeps me in control and gives me real oversight on what the agent is actually doing.

I have a mantra for this: **you can outsource your thinking, but you can't outsource your understanding.** The moment that breaks down is when people stop understanding their own codebase — and I see it happening a lot.

I won't be a hypocrite about it — there are times I just tell the agent "LFG 🚀" and let it run, but those are the low-stakes tasks. Even then, the systems part of my brain won't let me commit until I've read and understood what it wrote.

## Your last project — AyveeAI

AyveeAI is a voice-AI platform. The aim right now is to let businesses spin up agents without the usual hassle — agents that handle inbound calls so they're not stuck answering repetitive ones, plus automations for their workflows. (Short Loom walkthrough: [https://www.loom.com/share/23156854d71144848c1c487761807f9f]

- **One ambiguity I faced and how I resolved it:** I needed a safeguard to stop someone deleting a template that agents still reference. Two options: enforce it at the database level with a foreign-key constraint, or check at the application level. A DB constraint is impossible to bypass, but it throws an opaque error with no useful context. An app-level check lets me tell the user exactly how many agents are blocking the deletion and prompt them to reassign first. I chose the application-level check — an event where the Agents module responds with a count — so the error is actionable instead of cryptic.

- **One tradeoff I made and why:** When an agent is created from a template, I copy the `system_prompt` directly onto the agent rather than referencing the template by foreign key. That makes each agent independent and customisable without affecting anyone else. The cost is that template updates don't propagate automatically — I use an event-driven cascade to sync agents, and that cascade currently updates every linked agent unconditionally, so any manual prompt customisation gets overwritten when the template changes. I accepted that tradeoff because independent customisation matters more to the product at this stage, and I can add a "customised" flag to gate propagation later.

- **One mistake I made and what I changed:** Initially the Templates module imported the Agents module directly to handle two cross-module concerns — cascading prompt updates to every agent on a template, and checking whether any agents referenced a template before allowing deletion. That created tight coupling: any change to the Agents module rippled into Templates. I refactored to an event-driven pattern — Templates now emits `template.prompt.updated` and `template.can.delete`, and Agents handles them independently via `@OnEvent` listeners. The modules no longer know about each other. The coupling isn't fully eliminated — the event contracts are shared — but the direct dependency is gone.

- **One review comment that made me change my mind:** A reviewer flagged that `audit_logs` stored `actor_email` alongside `actor_id`, calling it unnecessary denormalisation. I initially agreed — you can always join to `users` for the email. But their point was the opposite: audit logs record history, so if the user later changes their email or is deleted, the join breaks. Storing the email as a snapshot at action time is the correct pattern for immutable audit records. I kept the column and updated the schema documentation to explain why.

> A note on naming: "Templates" and "Agents" above are **modules inside the core service**, not separate microservices. NestJS follows a modular (MVC-style) architecture, so each domain lives in its own module — hence the naming.

**Stack:** Next.js, NestJS, PostgreSQL, Redis, Vapi, Twilio.

## Anything you'd improve about THIS challenge or your CLAUDE.md

### The challenge
- The `challenge/` and `tickets/` separation isn't obvious from the outside — a one-line note in CLAUDE.md pointing to where the ticket specs live would orient a new engineer faster.
- There's no linting or static-analysis step in the "Before Submitting" checklist (e.g. phpstan / pint) — easy to let style or type issues slip through.

### CLAUDE.md
- The cancelled/recovered invariant at the bottom feels buried. It's a business-critical rule, so it would be safer at the top or in a dedicated `## Critical Invariants` section.
- "Follow existing code patterns — read before writing" is a good convention, but vague rules tend to get ignored — naming a concrete reference would help, e.g. "Follow existing code patterns — see `app/Modules/Payments/` as a reference."
