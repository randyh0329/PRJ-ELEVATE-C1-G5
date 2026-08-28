---
type: Reference
title: Source defect register
description: Twenty-three defects found in the Altostrat Singapore handbook - contradictions, structural faults, corrupted text, authoring artifacts, unresolved placeholders and gaps - with the concepts affected by each.
tags: [reference, defects, errata, contradictions, provenance, data-quality]
status: stable
generated: { by: claude-code/opus-5, at: 2026-08-27T00:00:00Z }
stale_after: 2027-07-01T00:00:00Z
sources:
  - id: hb
    resource: https://github.com/randyh0329/PRJ-ELEVATE-C1-G5/blob/main/ALTOSTRAT%20SINGAPORE%20EMPLOYEE%20POLICY%20HANDBOOK%20%26%20CONDUCT%20GUIDELINES.md
    title: "ALTOSTRAT SINGAPORE EMPLOYEE POLICY HANDBOOK & CONDUCT GUIDELINES (whole document)"
    last_modified: 2026-07-01T00:00:00Z
---

Every defect below was found by reading the source in full and is reproduced with enough
detail to be checked against it.[^hb] Line numbers refer to the handbook file as checked out
on 2026-08-27. Because every entry cites the source by line and quotes it directly, the
per-claim footnotes used elsewhere in this bundle would be noise here; the single source
below covers the whole register.

**None of these has been resolved.** This bundle does not invent answers. Where a defect
makes a question unanswerable, the affected concept says so and routes the reader to People
Ops.

# Severity key

* **Blocking** - an employee acting on the handbook alone could take the wrong amount of
  leave, seek the wrong approval, or miss an entitlement.
* **Material** - the reader is misdirected or the rule is unusable, but the consequence is
  recoverable.
* **Cosmetic** - visible damage to the document that does not change any rule.

# Contradictions

## D1 - Baby bonding leave and SPL: three incompatible statements

**Blocking.** Lines 68-71 (§2.2), 846-850 (§26.3), 879-885 (§27.2).

| Source | Says |
|--------|------|
| §2.2 | "Your baby bonding leave **remains at 18 weeks regardless of the SPL sharing arrangement**" - then, in the same bullet: "if both parents are Altostrat employees and the father allocates SPL to his partner, **his BBL must be reduced to 16 or 17 weeks**" |
| §26.3 | "If the birthing parent utilizes SPL to extend their Maternity Leave, **the father's Baby Bonding Leave remains 18 weeks and is not reduced.** Conversely, if the birthing parent donates SPL to the father, the father's Baby Bonding Leave **remains 18 weeks**" |
| §27.2 | "employee fathers allocating 9 or 10 weeks of SPL to their partner **will need to reduce their Baby Bonding Leave to 16 or 17 weeks**, subject to periodic audits" |

§2.2 contradicts **itself** inside a single bullet. §26.3 and §27.2 then contradict each
other on the same fact pattern - both parents employed, father donates SPL.

An employee-father who donates 10 weeks of SPL cannot determine from the handbook whether he
has 18 weeks or 16. **Affects:** [baby bonding](/leave/baby-bonding.md),
[maternity](/leave/maternity.md).

## D2 - Personal leave upper bound: 92 days or under 90

**Blocking.** Lines 105 (§3.3), 558-560 (§18.3), 708 (§21.5).

§3.3 and §18.3 both say **"up to 92 calendar days"** of continuous unpaid personal leave.
§21.5 defines personal leave as **"31 calendar days or more, but less than 90 calendar
days"**.

Days 90, 91 and 92 are simultaneously permitted and outside the definition. §18.3 is the
detail-layer section and is stated twice, so it is the better-supported figure - but the
bundle does not treat that as resolving it. **Affects:**
[unpaid and personal leave](/leave/unpaid-and-personal.md),
[global leaves overview](/leave/global-leaves-overview.md).

## D3 - Personal leave prerequisites: binding or discretionary

**Material.** Lines 106 (§3.3), 562 (§18.3).

§3.3: "You **typically need** at least 2 years of tenure and to have received a 'Significant
Impact' or higher rating in your last GRAD performance cycle **to qualify**." That reads as
an eligibility gate.

§18.3: "Managers and directors **may consider** factors such as having at least 2 years of
tenure, receiving a 'Significant Impact' or higher rating…" That reads as non-binding
guidance.

Whether an employee with 18 months' tenure may apply at all is unanswerable. **Affects:**
[unpaid and personal leave](/leave/unpaid-and-personal.md).

## D4 - RCI pre-approval channel stated three ways

**Blocking.** Lines 150 (§5.1), 421 (§13.3), 994 (§30 Onboarding Phase 2).

| Source | Channel |
|--------|---------|
| §5.1 | `go/governmentapproval` |
| §13.3 | "via case in ITSM" |
| §30, Phase 2 | the literal placeholder `email` |

Pre-approval is mandatory before anything of value goes to a government official, and the
handbook gives three different destinations for it. **Affects:**
[anti-bribery](/ethics/anti-bribery.md), [onboarding](/workplace/onboarding.md).

## D5 - Gift approval tiers overlap at their boundaries

**Blocking.** Lines 161-164 (§5.2) against 470-473 (§14.4).

§5.2 states the tiers **inclusive at both ends**:

* "US$100 to US$250" → Manager
* "US$250 to US$500" → Director
* "Over US$500" → VP

A gift of **exactly US$250** falls in both the Manager and Director tiers; **exactly
US$500** falls in both the Director and VP tiers.

§14.4 states the same tiers precisely - "**Over** US$100 **up to** US$250", "**Over**
US$250 **up to** US$500" - which resolves the boundaries. The two sections do not disagree
on intent, but an employee reading only the summary layer will under-approve at exactly the
two boundary values. **Affects:** [commercial gifts](/ethics/commercial-gifts.md).

## D6 - WorkWeek versus Workday

**Blocking.** Lines 1026, 1032 (§30 Onboarding Phase 4) against §19.4, §20.4, §22.3,
§23.3, §24.3, §25.3, §26.4, §27.4, §28.4.

Onboarding Phase 4 names **Workday** for logging approved time off and for submitting
Medical Certificates. **Every other section of the handbook** names **WorkWeek** (with
**gTime** for hourly employees' timecards).

A new hire following the onboarding guide would submit their MC to the wrong system, inside
a 48-hour deadline. **Affects:** [onboarding](/workplace/onboarding.md),
[sick and hospitalisation](/leave/sick-and-hospitalisation.md),
[vacation](/leave/vacation.md).

## D7 - Travel booking channel: ITSM or TRIPS

**Material.** Lines 115 (§4.1), 1040 (§30 Onboarding Phase 5).

§4.1: "create a ticket request as **Travel from ITSM**". Onboarding Phase 5: book "**through
the TRIPS portal**". Both state the 3-week advance rule, so only the system is in doubt.
**Affects:** [travel and expense](/workplace/travel-and-expense.md),
[onboarding](/workplace/onboarding.md).

## D8 - Bereavement leave eligibility: exclusions or none

**Blocking.** Lines 87-90 (§3.1) against 716-717 (§22.1).

§22.1: "**Apprentices and interns are not eligible** under this policy, but may be entitled
to statutory bereavement leave based on their location. Temps, vendors and contractors are
not eligible."

§3.1 states the 4-week entitlement with **no eligibility carve-out of any kind**.

An intern reading the summary layer would believe they have 20 paid days. **Affects:**
[bereavement](/leave/bereavement.md).

## D9 - Conflict of interest escalation splits in two

**Material.** Lines 380-383 (§12.2).

Employees are told to disclose to their manager and **seek review from EBI**. Managers who
receive that same disclosure are told to **seek guidance from VP**. The handbook does not
say whether the VP consultation **replaces** EBI review, **precedes** it, or runs alongside
it - so the same disclosure has two destinations depending on who holds it. **Affects:**
[conflicts of interest](/ethics/conflicts-of-interest.md).

## D10 - Baby bonding "per year" against a single 12-month window

**Material.** Lines 70, 841-843 (§2.2, §26.2).

BBL is described as "up to 18 weeks (90 work days) of paid leave **per year**", while the
same passages say only **one** 18-week period may be claimed for multiple children and that
all 18 weeks must be used **within 12 months of the birth or placement date** or be
forfeited.

"Per year" implies an annually renewing entitlement; the timeline rules describe a
single, event-bound, expiring one. Two children in successive years is the case that
exposes it, and the source does not address it. **Affects:**
[baby bonding](/leave/baby-bonding.md).

## D11 - Who Baby Bonding Leave is for

**Material.** Lines 68 (§2.2) against 833-837 (§26.1).

§2.2 scopes BBL to "**parents who do not take maternity leave**". §26.1 frames the
distinction around **birth-giving** parents. These are different sets: an adoptive mother
takes no maternity leave and is not birth-giving; a birth-giving parent who declines
maternity leave is in the first set but not the second. **Affects:**
[baby bonding](/leave/baby-bonding.md), [maternity](/leave/maternity.md).

## D12 - Intern maternity leave: "up to 26 weeks" or "by up to 26 weeks"

**Blocking.** Lines 63 (§2.1) against 891 (§27.3).

§2.1: interns whose spouses donate SPL "can extend their leave **up to** 26 weeks."

§27.3: "Interns whose spouse donates SPL can extend their Maternity Leave **by up to** 26
weeks."

Read literally, §27.3 gives 16 + 26 = **42 weeks** - which is impossible, since SPL provides
a maximum of 10 weeks and the equivalent employee calculation caps at 26. The one-word
difference changes the answer by 16 weeks. **Affects:** [maternity](/leave/maternity.md).

# Structural defects

## D13 - Sections 11 and 15 do not exist; there are two Section 30s

**Material.** Section headers at lines 339 (§10) → 371 (§12), and 448 (§14) → 481 (§16);
duplicate headers at 970 and 1054.

The document jumps from Section 10 to Section 12, and from Section 14 to Section 16. No
content is visibly truncated at either seam - the numbering simply skips.

**Section 30 appears twice** with entirely different content:

* Line 970 - "SECTION 30: New Employee Onboarding Guidelines"
* Line 1054 - "SECTION 30: PERFORMANCE MANAGEMENT & DISCIPLINARY PROCESS"

Any citation of the form "Section 30" is ambiguous. This bundle disambiguates them as
[onboarding](/workplace/onboarding.md) and
[performance and discipline](/conduct/performance-and-discipline.md), and every footnote
that cites either says which one it means.

Whether Sections 11 and 15 are missing content or a numbering error cannot be determined
from the document.

## D14 - Relocation, badging and ITSM rules misfiled under Community Guidelines

**Material.** Lines 199-200 (§5.5).

Section 5.5 is titled "Community Guidelines (Conversational Boundaries)". After two bullets
about workplace discussion, it contains, without any transition:

* the **US$10,000 international relocation allowance**;
* **destination-office badging pre-configuration** (Facilities ticket, Priority 3);
* the **ITSM ticket lifecycle** rule (New → In Progress → Resolved → Closed, no state
  skipping);
* the **ITSM priority definitions** rule.

None is a conversational boundary. A reader searching for relocation entitlements would
never look here. This bundle relocates them to
[travel and expense](/workplace/travel-and-expense.md) and
[IT acceptable use](/workplace/it-acceptable-use.md), noting the origin in both.

## D15 - Section 5.4 states the same rules twice

**Cosmetic.** Lines 176-177 against 186-187.

The public-settings restriction and the privacy-screen/headphones/secured-documents list
each appear twice in Section 5.4, in near-identical wording. The content does not conflict.
**Affects:** [remote and hybrid work](/workplace/remote-and-hybrid-work.md).

# Corrupted and leftover text

## D16 - Whitespace loss in §13.3

**Cosmetic.** Line 424.

> "Before offering anything of value that exceeds US$100,orifcumulativecourtesiestothatofficialexceed\ US$200 within a rolling 6-month period."

Reconstructed: "exceeds US$100, **or if cumulative courtesies to that official exceed**
US$200 within a rolling 6-month period." §5.1 line 152 states the same rule intact, which
confirms the reading. **Affects:** [anti-bribery](/ethics/anti-bribery.md).

## D17 - Escaped-space corruption in §14.4

**Cosmetic.** Lines 472-473.

> "**Over US$100\ upto\ US$250**" and "**Over US$250\ upto\ US$500**"

Stray backslashes and lost word breaks. The meaning is recoverable and is what resolves D5.
**Affects:** [commercial gifts](/ethics/commercial-gifts.md).

## D18 - "career's leave" for "carer's leave"

**Cosmetic.** Line 694 (§21.3).

> "Employees can use other leaves or flexibility arrangements to extend their **career's
> leave** if necessary."

A homophone error. Notable mainly because it defeats a literal search for "carer's leave".
**Affects:** [carer's leave](/leave/carers.md).

## D19 - LLM authoring artifacts left in the published document

**Material.** Lines 304, 635, 913.

Three passages of drafting instructions survive in the handbook body:

> "Here is the drafted text for the new section based on the Community Guidelines. You can
> insert this into your Altostrat Singapore handbook as the next section (e.g., Section 9)
> to maintain the consistent formatting and tone." (line 304)

The same construction appears before Section 20 (line 635) and Section 28 (line 913).

These are not policy. They are evidence that Sections 9, 20 and 28 were machine-drafted and
pasted in without review - which bears directly on how much weight to place on the rest of
those sections.

## D20 - "Googler" in §26.3

**Material.** Lines 848-850.

The Baby Bonding SPL scenarios are headed **"Googler Father + Non-Googler Mother"**,
**"Non-Googler Father + Googler Mother"** and **"Both Parents are Googlers"**.

Altostrat is not Google. The text was lifted from another company's handbook and the
employer name was not replaced. Read together with D19, this is the clearest evidence that
the source is an unreviewed composite. §26.3 is also one of the two sections at the centre of
D1 - the same passage is both textually and substantively unreliable. **Affects:**
[baby bonding](/leave/baby-bonding.md).

# Unresolved placeholders

## D21 - Contact details that are not contact details

**Blocking.** Throughout.

The handbook routes employees to destinations that were never filled in:

| Placeholder | Where | Should be |
|-------------|-------|-----------|
| `abc@altostrat.com` | §16.7 | The Data Protection Officer's address |
| `email` | §30 Phase 2 | The RCI government-approval channel |
| `email` | §30 Phase 3 | The anonymous Compliance Helpline |
| `company intranet` | §30 Phase 2 | EBI, for conflict-of-interest review |
| `company intranet` | §30 Phase 4, Next Steps | Benefits and leave entitlement details |
| `ITSM and open a case` | §30 Next Steps | A link to ITSM |
| `Company Website` | §§31.3, 32.2, 33.1, 34.3, 34.4, 35.2 | Benefits portal, claims portal, hardware requests, incident reporting, ergonomic assessments, HR escalation |

`abc@altostrat.com` is the worst of these: it looks like a real address, so an employee
exercising a data-protection right would send mail into a void rather than notice the gap.

`Company Website` is doing the most work - six distinct destinations across five sections,
all named identically, at least one of which (hardware requests) conflicts with the ITSM
route given in §5.4 and §30.

# Gaps

## D22 - Vacation: proration, rounding and year zero unspecified

**Material.** Line 650 (§20.2).

§20.2 gives three service tiers starting at "1 to 6 years", says first-year employees are
"prorated **based on your start date**", and says part-time and fixed-term employees are
prorated by FTE. It does not state:

* which tier applies in year **zero** - the tiers begin at 1 year;
* the **proration formula** - by calendar day, completed month, pay period, or working day;
* any **rounding rule**, even though §20.2 separately restricts booking to half- and
  full-days, so an unrounded result may be unbookable.

These are the four assumptions the [vacation entitlement
computation](/computations/vacation-entitlement.md) had to invent to be executable, and
they are labelled as assumptions there.

## D23 - No payout rule for TOIL or bereavement on separation

**Material.** Lines 951-958 (§29.2).

§29.2 enumerates the separation treatment of vacation, floating holidays, sick,
hospitalisation, childcare, maternity, baby bonding and carer's leave. It omits **time off
in lieu** and **bereavement leave**.

TOIL matters: it is *earned* time, banked against hours already worked. The handbook does
not say whether unused TOIL is paid out, forfeited, or must be consumed before the End Date.
**Affects:** [exit](/workplace/exit.md),
[time off in lieu](/leave/time-off-in-lieu.md).

# How this register is used

Each affected concept links here and states the defect in its own **Conflict** or gaps
section rather than picking a winner.

A defect in the source does **not** change the affected concept's `status`. Under OKF
v0.2 §5.4, `status` describes the concept document - `draft` means "not yet reviewed;
possibly incomplete" - so a concept that faithfully and completely records a
contradiction is `stable`. Concepts affected by a Blocking defect instead open with a
callout naming the unsettled point and pointing at their **Conflict** section.

The counts: **12 contradictions, 3 structural defects, 5 text defects, 1 placeholder
cluster, 2 gaps** - 23 numbered entries covering the 21 distinct problems identified on the
first pass, D15 and D23 having been split out during writing.

Six of the twelve contradictions are between the handbook's **summary layer** (Sections 1-5)
and its **detail layer** (Sections 13-14, 18-28). That pattern is the reason the
[corpus datasheet](/corpus-datasheet.md) adopts a precedence rule - and the reason it flags that rule as a
producer decision the source does not authorise.

[^hb]: ALTOSTRAT SINGAPORE EMPLOYEE POLICY HANDBOOK & CONDUCT GUIDELINES, complete document, as checked out from `randyh0329/PRJ-ELEVATE-C1-G5@main` on 2026-08-27
