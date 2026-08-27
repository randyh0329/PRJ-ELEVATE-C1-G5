---
type: Corpus Datasheet
title: Altostrat Singapore Employee Policy Handbook - corpus datasheet
description: How this bundle was built from the source handbook, which layer governs when sections disagree, the trust tier of every concept, and what must not be answered from this corpus.
tags: [datasheet, orientation, singapore, hr-policy, handbook, provenance, limitations]
status: stable
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
stale_after: 2027-07-01T00:00:00Z
sources:
  - id: handbook
    resource: https://github.com/randyh0329/PRJ-ELEVATE-C1-G5/blob/main/ALTOSTRAT%20SINGAPORE%20EMPLOYEE%20POLICY%20HANDBOOK%20%26%20CONDUCT%20GUIDELINES.md
    title: "ALTOSTRAT SINGAPORE EMPLOYEE POLICY HANDBOOK & CONDUCT GUIDELINES (Confidential - Internal Use Only)"
    last_modified: 2026-07-01T00:00:00Z
  - id: hb-header
    resource: https://github.com/randyh0329/PRJ-ELEVATE-C1-G5/blob/main/ALTOSTRAT%20SINGAPORE%20EMPLOYEE%20POLICY%20HANDBOOK%20%26%20CONDUCT%20GUIDELINES.md
    title: "Handbook front matter: applicability and last-updated statement"
    last_modified: 2026-07-01T00:00:00Z
---

# What this bundle is

This bundle is a structured re-presentation of one source document: the Altostrat
Singapore Employee Policy Handbook & Conduct Guidelines.[^handbook] Nothing here is
new policy. Every claim in every concept traces back to a numbered section of that
handbook through the `sources` frontmatter and footnote labels.

The source is marked **Confidential - Internal Use Only** and applies to all
Altostrat Singapore employees, interns, and the extended workforce - temps, vendors
and contractors.[^hb-header] Its stated last-updated date is **July 2026**; the day
is not given, so every `last_modified` in this bundle uses `2026-07-01` as a
deliberate floor, not a known date.

# The single most important thing to know: the source has two layers

The handbook restates most of its leave and ethics content twice, at two different
levels of detail:

| Layer | Sections | Character |
|-------|----------|-----------|
| **Summary layer** | Sections 1-5 | Short, compressed, written as an overview |
| **Detail layer** | Sections 8-9, 13-14, 18-28 | Long-form, with eligibility, exclusions, proration and system-entry rules |

Fourteen topics appear in both layers. Where they disagree, **this bundle treats the
detail layer as governing** and records the summary-layer wording as a secondary
source on the same concept.

**This precedence rule is a producer decision, not a statement from the source.** The
handbook nowhere says which layer wins. The rule was adopted because the detail
sections consistently carry the eligibility carve-outs and procedural steps the
summary sections omit, so following the summary alone produces answers that are
incomplete rather than merely terser. Where the two layers state materially different
*numbers* or *obligations* rather than different levels of detail, the concept says so
in the body and the conflict is listed in the
[source defect register](/references/source-defects.md). Those cases are not resolved
by the precedence rule and must be escalated, not answered.

Two topics exist **only** in the summary layer and therefore have no detail-layer
backing:

* [Travel and expense](/workplace/travel-and-expense.md) - Section 4 only.
* [Remote and hybrid work](/workplace/remote-and-hybrid-work.md) - Section 5.4 only.

# Layer map

| Topic | Summary | Detail | Concept |
|-------|---------|--------|---------|
| Sick and hospitalisation leave | 1.1 | 19 | [sick-and-hospitalisation](/leave/sick-and-hospitalisation.md) |
| Vacation leave | 1.2 | 20 | [vacation](/leave/vacation.md) |
| Childcare leave | 1.3 | 24 | [childcare](/leave/childcare.md) |
| Time off in lieu | 1.4 | 25 | [time-off-in-lieu](/leave/time-off-in-lieu.md) |
| Maternity leave | 2.1 | 27 | [maternity](/leave/maternity.md) |
| Baby bonding leave | 2.2 | 26 | [baby-bonding](/leave/baby-bonding.md) |
| Ramp-back time | 2.3 | 28 | [ramp-back](/leave/ramp-back.md) |
| Bereavement leave | 3.1 | 22 | [bereavement](/leave/bereavement.md) |
| Carer's leave | 3.2 | 23 | [carers](/leave/carers.md) |
| Unpaid time off and personal leave | 3.3 | 18, 21.5 | [unpaid-and-personal](/leave/unpaid-and-personal.md) |
| Anti-bribery and government ethics | 5.1 | 13 | [anti-bribery](/ethics/anti-bribery.md) |
| Commercial gifts and entertainment | 5.2 | 14 | [commercial-gifts](/ethics/commercial-gifts.md) |
| Workplace personal relationships | 5.3 | 8 | [personal-relationships](/conduct/personal-relationships.md) |
| Community guidelines | 5.5 | 9 | [community-guidelines](/conduct/community-guidelines.md) |

Single-layer topics: Section 4 (travel and expense), 5.4 (remote work), 6
(confidentiality and assets), 7 (harassment and discrimination), 10 (alcohol,
smoking and drugs), 12 (conflicts of interest), 16 (employee privacy), 17 (flexible
work requests), 21 (global leaves overview), 29 (exit), 30 (onboarding), 30 again
(performance and discipline), 31 (compensation and payroll), 32 (health insurance),
33 (IT and social media), 34 (health and safety), 35 (grievance).

# Routing a question

| If the question is about | Go to |
|--------------------------|-------|
| How much leave am I entitled to, and can I book it | [leave/](/leave/) |
| How do I behave, and what happens if I do not | [conduct/](/conduct/) |
| Can I give, accept or approve this | [ethics/](/ethics/) |
| Where do I work, how do I travel, what do I claim | [workplace/](/workplace/) |
| What does the company hold about me, and what am I paid | [people-ops/](/people-ops/) |
| Compute an entitlement figure | [computations/](/computations/) |

# What must not be answered from this bundle

1. **Anything the source contradicts itself on.** Twelve substantive conflicts are
   catalogued in the [source defect register](/references/source-defects.md). Where a
   concept body carries a **Conflict** heading, the correct response is to state that
   the handbook is inconsistent and route to People Ops - not to pick a side.
2. **Extended workforce leave entitlements.** Temps, vendors and contractors are
   explicitly excluded from every Singapore leave policy in the source and are told to
   contact their direct employer. The handbook carries no substitute figures.
3. **Anything for which the source only has a placeholder.** Several escalation
   channels resolve to literal strings such as `email`, `company intranet` and
   `abc@altostrat.com`. These are unresolved in the source and must not be presented
   as real contact routes.
4. **Statutory minima as of any date other than the source's.** The Singapore Shared
   Parental Leave figures reflect the scheme effective 1 April 2026 as described in
   July 2026. They are not a live read of MOM or LifeSG guidance.
5. **Anything absent.** Handbook Sections 11 and 15 do not exist. Their subject matter
   is unknown; the gap is not evidence that the topic is unregulated.

# Trust posture

No concept in this bundle carries a `verified` entry, so every concept sits at the
**unverified** tier under OKF v0.2 §5.3. The bundle was machine-extracted from a
single document and has had no human review. `status: draft` marks the concepts whose
source content is internally contradictory; `status: stable` marks the rest. Neither
value implies review has happened.

`usage_count` and `usage_window` are absent throughout, because no usage telemetry for
the source document was available. They are omitted rather than estimated.

[^handbook]: ALTOSTRAT SINGAPORE EMPLOYEE POLICY HANDBOOK & CONDUCT GUIDELINES (Confidential - Internal Use Only)
[^hb-header]: Handbook front matter: applicability and last-updated statement
