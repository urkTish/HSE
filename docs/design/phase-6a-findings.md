# Phase 6a design pass: UX findings

Scope: the Phase 6a screens in the "Occupational health" nav section:
- Worker health (lookup and the worker page: fitness status, requirements, health profile), fitness gaps, medical plan.
- Fitness assessments (list, new, detail with sign / submit / accept / verify / scan), holds, referrals, medical imports.
- Fitness catalogue (codes, clinics, examiners), medical settings and the Health KPIs page.

Shared components were changed only where a 6a screen needed it, and they stay consistent with Phases 0–5 (`CertStatePanel` from Phase 4, `StatusBadge`, the responsive table cards).

## Method

- **Setup.** The p6a e2e setup: real backend on a fresh, migrated and seeded database (`hse_e2e`, `app.seed` incl. the 6a seed), shared e2e clock at the PTW seed instant (2026-10-06 10:00 Riyadh), production build of the frontend.
- **Users.** Dr. Huda Al-Mansour (OH Practitioner, tier 3) for the case screens; Faisal Al-Harbi (HSE Manager) for settings and KPIs. Tier-dependent rendering was not changed; `p6a-health` covers tiers 1–3.
- **Records.** WKR-000034 (on a fitness hold after referral MFR-…-00031, GEN-FIT gap), WKR-000009 (fit with restrictions, WAH-FIT restriction gap), MFA-ANIA-EXP-2026-00398, holds MFH-…-00027 / 00028 / 00011, the 119 open gaps.
- **Screenshots.** The 15 Phase 6a screens in EN and AR (1440 px) before and after; two new phone screens (390 px) added to `screenshots-p6a.spec.ts` (16 worker health, 17 holds). Before / after pairs in `docs/screenshots/phase-6a/design/`:

| Files | Screen |
|---|---|
| 01/02 | Worker health WKR-000034, EN desktop |
| 03/04 | Worker health WKR-000034, AR desktop |
| 05/06 | Fitness gaps, EN desktop |
| 07/08 | Fitness holds, EN desktop |
| 09/10 | Fitness referrals, AR desktop |
| 11/12 | Assessment detail MFA-…-00398, AR desktop |

Phone results: `docs/screenshots/phase-6a/16-worker-health-phone-{en,ar}.png`, `17-fitness-holds-phone-{en,ar}.png`.

Effort: **S** < 1 h · **M** ≤ 1 day · **L** a redesign or a contract change that needs the user's approval.

## Ranked findings

| # | Impact | Problem | Where / evidence | Fix | Effort | Status |
|---|---|---|---|---|---|---|
| 1 | High | **No one-glance "may this worker work today?".** A worker on a fitness hold showed a 12 px "On fitness hold" pill next to the worker number; the hard stop was a second small pill inside the table. A cleared worker looked the same as one with a gap | `01-before`, `03-before` | Worker page opens with the Phase 4 state panel (`CertStatePanel`): red "Removed from work" (on hold), red "Not eligible — stops work" + the hard-stop codes, amber "Fitness check needed" + the codes not cleared, green "Cleared for work", grey "No fitness requirements". Worded from server fields only (`on_hold`, each item's `band`, `hard_stop`, `required`) and in the P6-7 words, so a tier-1 user sees nothing medical. The header pill is gone (the panel carries `data-testid="on-hold"` when on hold). "Stops work" pill gets an octagon icon | M | Done |
| 2 | High | **Referrals table crashed a column header.** `t("raised")` is the "Referral {no} raised." toast, so the header threw a missing-argument error (Next "2 issues" overlay) and AR showed the raw key `medical.referrals.raised` | `09-before` | New key `medDesign.raisedOn` ("Raised" / "تاريخ الإحالة") for the header and the phone card label | S | Done |
| 3 | High | **Privacy of medical data was a 12 px grey line.** "You see the full fitness record (clinical administration)." did not say the data is confidential or that each read is audited (OH-2 `sensitive_field_read`) | `01-before`, `05-before` | `TierNote` is a bordered note with a lock icon: the tier sentence in medium weight, and for tiers 2–3 "Confidential health data: each view is recorded." Same component on every tier-aware screen (worker, gaps, assessments, holds, referrals) | S | Done |
| 4 | Medium | **Dates broke dense tables.** Hold start / end and referral raised / due cells wrapped to 5–6 lines ("06 Oct 2026 10:02 · 25 Rabiʻ II 1448 AH" in a narrow column); gap and assessment dates to 2–3 | `07-before`, `09-before` | `StackedDate`: Gregorian date (and time) on one unbroken line, the Hijri date muted underneath (Phase 4 tag-board rule). Used in holds, referrals, gaps, the assessments list and the worker page. | S | Done |
| 5 | Medium | **Gap category was plain text.** "Missing", "Expired", "On hold", "Restriction" read alike in the gap register | `05-before` | `GapCategoryBadge`: red + triangle for missing / expired / unfit / revoked / verification failed, red + person-x for on hold, amber for restriction or review due, blue clock for pending review / unverified. `data-testid="gap-category"` kept | S | Done |
| 6 | Medium | **An active hold was amber in the holds list but red on the worker page.** `active` used the Phase 3 "suspended" tone (pause, amber), although a hold removes the worker from all work | `07-before` | New `StatusBadge` status `fitness_hold_active` (red, person-x icon), used by `HoldStatusBadge` and the "On hold" gap badge | S | Done |
| 7 | Medium | **Arabic pages reversed punctuation in typed text.** Referral notes and hold reasons in English rendered as ".Looked pale at the morning briefing" in AR | `09-before` | `FreeText` (`dir="auto"`) for hold reason / cancel reason, referral note / cancel reason, assessment status reason and revoke reason | S | Done |
| 8 | Medium | **"Revoke" read "Cancel" in Arabic.** The assessment action was إلغاء, the same word as the dialog's cancel buttons, on an irreversible action | `11-before` | Action label "إلغاء التقييم" (status "ملغى" unchanged, as the spec) | S | Done |
| 9 | Low | **Outcome badges were colour only** (Fit green, Fit with restrictions amber, Unfit red) while every other status badge has an icon | `05-assessment-detail-*` | Tick / triangle / octagon icons on `OutcomeBadge` | S | Done |
| 10 | Low | **Arrows did not mirror and empty history read "— · —".** Health-profile history, plan versions and the verification log used "→" (points backwards in RTL); a history row with no groups and no user ended "now: — · —" | `01-before` | Mirrored arrow (`rtl:-scale-x-100`), "No exposure groups." in words, the user omitted when absent | S | Done |
| 11 | Low | **Generic empty states.** Holds, referrals and assessments said "No records match the current filters" with no filter set | — | "No fitness holds on this project.", "No fitness referrals on this project.", "No fitness assessments on this project yet."; the filter message stays when a filter is on | S | Done |
| 12 | Medium | **The page combines item flags into a worker verdict.** Finding 1 shows server fields, but "cleared / check / stop" is the UI reading the items together. Gate, field check and permit screens will need the same verdict | Worker page | **P18.** A server `work_state` (`removed` / `stop` / `check` / `cleared` / `none`) and its codes on `WorkerFitnessRead`, in P6-7 words, reused by the panel and later by the field check | L | Proposal P18 |
| 13 | Medium | **Health KPIs page has tiles and a table but no trend.** K-89…K-96 show one month with no comparison; C22–C24 (§8.1) are not built (backend data parked) | `15-occupational-health-kpi-*` | **P19.** When the C22–C24 data exists: C22 lines with the E14 threshold, C23 holds bars + K-94 line, C24 90-day expiry profile; each tile with the previous month and its direction. Follow the dataviz rules (Phase 1 series colours, MK-3 small-cell suppression) | L | Proposal P19 |
| 14 | Medium | **Health data on shared screens.** Tier-3 users work in site offices with shared monitors; the worker page and registers show outcomes, restrictions and reasons in full | Worker page, registers | **P20.** A per-user "Hide health details" switch (outcome, restrictions and reasons masked until clicked, each reveal still audited) and no tier-2/3 content on the TV / kiosk modes (P17) | L | Proposal P20 |
| 15 | Medium | **Phone: actions before the state, two-calendar dates.** On the phone the worker page puts four action buttons above the state panel; dates outside the 6a tables still use one two-calendar line | `16-worker-health-phone-*` | Phase 0 proposals **P2** (sticky phone action bar) and **P1** (two-line dates platform-wide) apply unchanged | L | Proposals P1, P2 |

## Not changed on purpose

- Business logic, API calls, permissions, tiers and the data shown are unchanged. No request was added. Tier gating still comes from the server's `tier` field and the existing capabilities.
- Tier-1 wording: the state panel uses the P6-7 texts ("Removed from work … pending HSE check", "Fitness requirement not met") and fitness codes only, never outcomes, restrictions, reasons or clinics.
- The server's tier-1 band text ("Not eligible — HSE check") is shown as sent.
- The free-text hints ("Never record a diagnosis…") and the new-assessment banner are unchanged.
- E2E selectors are unchanged: `on-hold` now sits on the state panel, `fitness-tier` on the tier note, `gap-category` on the gap badge, `referral-note` on the note text.

## Design system additions (Phase 6a)

- **`CertStatePanel`** takes an optional `label` (accessible name); the worker page uses "Fitness for work".
- **`StatusBadge` `fitness_hold_active`**: red, person-x icon; an active fitness hold.
- **`components/medical/common.tsx`**: `TierNote` (lock note + confidentiality line), `StackedDate`, `FreeText`, `GapCategoryBadge`; `OutcomeBadge` with icons.
- Strings: `medDesign.*` and the AR `enums.assessmentAction.revoke`, in `scripts/i18n/p6-design.py`.
