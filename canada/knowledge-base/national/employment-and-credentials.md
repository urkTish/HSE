# Employment and credential recognition

Agent 01 · researched 2026-10-30 · jurisdiction: occupational regulation is provincial or
territorial (a few occupations are federal); labour-market information is federal (ESDC Job Bank) ·
next review 2027-01-30, or as soon as the user's occupation is known.

**Status note.** The user's occupation, experience, credentials and National Occupational
Classification (NOC) code are unknown. `USER-PROFILE.md` notes the repository *suggests*
engineering, software or HSE management, but that is unconfirmed (question 2). Section 5 is a
placeholder until then.

---

## 1. Regulated or not: the first question

- **Regulated occupations** are controlled by provincial or territorial (sometimes federal) law and
  governed by a regulatory body. About **20% of jobs in Canada** are regulated. They include
  professions such as nursing, medicine, engineering and law, and skilled trades such as plumbing
  and electrical work. You cannot practise, or use the protected title, without a licence or
  certificate from the regulator in **the province where you will work**.
- **Non-regulated occupations** have no legal licensing requirement. Employers judge your
  credentials themselves. Voluntary certification may still help.
- **Regulation differs by province.** An occupation can be regulated in one province and not in
  another. A licence in one province does not automatically transfer before you arrive.

Source: Canadian Information Centre for International Credentials (CICIC), terminology guide and
"Find out if your occupation is regulated or not" (cicic.ca, accessed 2026-10-30).

## 2. How to find the regulator

1. Find the occupation's **NOC 2021 code and TEER level**. The TEER level also decides Express Entry
   eligibility (`nat-ca-express-entry-2026`).
2. Search **CICIC's Directory of Occupational Profiles** (cicic.ca). Each profile shows, for each
   province, whether the occupation is regulated, whether certification is mandatory or voluntary,
   whether the title is reserved or practice is exclusive, and the regulator's name and link.
3. Confirm on the **regulator's own site**: requirements, fees, exams, timelines, and any
   language-proficiency requirement. In Quebec, the Charter of the French language links
   professional licensing to knowledge of French. The exact provision was not read in this pass
   (see `quebec-language-rules.md`).
4. For immigration, an **Educational Credential Assessment** from an IRCC-designated organisation is
   needed for foreign education under the Federal Skilled Worker programme. It is **not** a licence.
   Regulators run their own assessments.

## 3. The typical licensing process: steps, cost and time

The federal Foreign Credential Recognition guidance (ESDC) and the *Pan-Canadian Framework for the
Assessment and Recognition of Foreign Qualifications* describe a common sequence:

1. **Document verification.** Transcripts and diplomas are often sent directly by the issuing
   institution, and translated.
2. **Credential and competency assessment by the regulator**, which may include a gap assessment.
3. **Application to the regulator, with fees.**
4. **Exams.** These may cover a technical or national exam, law and ethics, and language.
5. **Supervised practice or Canadian experience**, where required. Engineering and many health
   professions require it.
6. **Full registration or licence.**

- **Cost:** ESDC says the process "takes time and can be costly". Fees are set by each regulator and
  were not catalogued in Phase 1. A figure will be recorded per regulator once the occupation is
  known.
- **Duration:** the Pan-Canadian Framework's goal is that, within **one year**, an applicant knows
  whether their qualifications will be recognised or what more is required. Full licensure often
  takes longer where exams and supervised experience apply. This is a professional reading; the
  framework is an older intergovernmental document.
- **Start before arriving.** ESDC advises contacting the regulator in the destination province
  before arrival.

Sources: ESDC *Foreign Credential Recognition* page; the Pan-Canadian Framework (Forum of Labour
Market Ministers); both accessed 2026-10-30 through search extracts.

## 4. How to read Job Bank employment outlooks

Job Bank (ESDC) publishes a **3-year outlook** for about 516 NOC occupations, by province or
territory and economic region. The method:

- **Four indicators:** employment growth, replacement needs (retirements), an index of experienced
  unemployed workers, and a composite net-needs indicator. Each is ranked 1–6 against roughly
  10 years of history.
- **Score:** the four ranks are summed (4–24) and mapped to a rating: 4–7 Very good (5 stars),
  8–11 Good (4), 12–16 Moderate (3), 17–20 Limited (2), 21–24 Very limited (1). "Undetermined" is
  used when the data are too thin, for example for small occupations.
- **Review:** regional economists review the results before publication.
- **Updates:** yearly, usually in November or December. The current cycle covers 2025–2027.

**How to use it:**

- Compare **within a province, not across provinces**. Job Bank says outlooks are not comparable
  nationally.
- An outlook measures **the prospect of finding a job, not a labour shortage**.
- Read it together with wages (Job Bank wage pages) and the occupation's regulation status.
- From 3 November 2026, whether an occupation is **high-wage** (national median wage at least 1.3×
  the average median) also affects Express Entry points
  (`nat-ca-express-entry-crs-changes-2026-11-03`).

Source: Job Bank, *3-year Employment Outlooks — Methodology* and *Questions and Answers*
(jobbank.gc.ca, accessed 2026-10-30 through search extracts).

## 5. The user's occupation (placeholder)

To be filled once `USER-PROFILE.md` names the occupation (question 2).

| Item | Value | Source / record |
|---|---|---|
| Occupation and NOC 2021 code (TEER) | unknown | — |
| Regulated? In which provinces? | unknown | CICIC profile |
| Regulator per shortlisted province, with fees and steps | unknown | regulator sites |
| Express Entry category fit (2026 categories) | unknown | `nat-ca-express-entry-2026` |
| High-wage occupation under the 3 November 2026 rules? | unknown | IRCC list (not yet captured) |
| Job Bank outlook in each shortlisted province | unknown | Job Bank |
| Median wage by province | unknown | Job Bank wages |
| PNP streams that target it | unknown | `nat-<prov>-provincial-nominee-program` |

Hypotheses to test with CICIC once the occupation is known. None of these was checked in this pass:

- Professional engineering may be a regulated profession with a protected title.
- Many software roles may be non-regulated, while "engineer" in a job title may be restricted.
- Occupational health and safety roles may be non-regulated, with voluntary designations.

## 6. Labour-market context relevant to newcomers (in force)

- **Low-wage employer-specific work permits are blocked in high-unemployment cities.** ESDC does not
  process low-wage LMIAs in 30 of 42 census metropolitan areas with unemployment of 6% or more. The
  list runs from 9 October 2026 to 7 January 2027 and includes Toronto, Montréal, Vancouver, Calgary,
  Edmonton and Halifax. The LMIA unemployment figures in that list (for example Oshawa 9.8%, London
  9.1%, Kelowna 8.6%, Moncton 8.1%) are a rough signal of local labour slack. Source:
  `nat-ca-work-permits-and-study-to-work-2026`.
- **Remote work for a foreign employer and self-employment** were not researched in Phase 1. They
  depend on question 7.
