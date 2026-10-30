# Climate comparison across Canadian cities

Agent 04 · researched 2026-10-30 · Phase 1

This page compares the long-term climate of 34 cities and towns in all ten provinces and three
territories. Every number comes from Environment and Climate Change Canada (ECCC) climate
normals, stored as one `clim` record per station under `climate/`. The tables below were
generated from those records and were not typed by hand.

**Read this first**

- **Normals are 30-year averages of observed weather.** They describe what a typical year looked
  like in 1991–2020, or in 1981–2010 where marked. They are not forecasts and say nothing about any
  coming season. Recent single events are covered in `hazards.md`.
- **Period flag on every row.** Most rows use the **1991–2020** normals. Three cities use
  **1981–2010** as their main record, because ECCC's 1991–2020 normals for the local station do not
  publish precipitation: Kelowna `clim-bc-kelowna-a`, Castlegar (West Kootenay)
  `clim-bc-castlegar-a` and Kingston `clim-on-kingston-pumping-station`.
- **Sunshine is 1981–2010 only.** ECCC stopped measuring bright sunshine at most sites, so the
  1991–2020 normals contain no sunshine. Sunshine figures therefore come from separate
  *supplementary* 1981–2010 records (ids ending `-1981-2010`), shown in their own table (Table B).
  Do not read them as 1991–2020 values.
- **Stations are not cities.** Each row names the station type and its distance from the city's
  reference point in NRCan's Canadian Geographical Names Database. For Toronto, Ottawa, Greater
  Sudbury and St. John's the municipal reference point is a centroid of the amalgamated
  municipality, so a downtown proxy is used; the reason is in each record's `notes`.
- **Missing means missing.** A dash (—) means ECCC does not publish that value for that station and
  period (for example, 1991–2020 snowfall for Toronto, London, Québec city and Inuvik). Nothing has
  been estimated to fill a gap.
- **ECCC data-quality codes.** These run from A (meets the WMO "3 and 5" completeness rule) to D
  (at least 15 of the 30 years). The code for each element is in the record's `notes`. Records whose
  main elements are only code C or D have `verification.confidence` = `medium`.

## Table A: winter and summer temperatures, precipitation and snow

The Jan low is the mean daily minimum for January and the Jul high is the mean daily maximum for
July. Units are °C, mm and cm.

| City | Record | Period | Station type · km from centre · elev. m | Jan mean °C | Jul mean °C | Jan low °C | Jul high °C | Annual precip mm | Annual snow cm |
|---|---|---|---|---|---|---|---|---|---|
| Castlegar (BC) | `clim-bc-castlegar-a` | 1981–2010 | airport · 4.0 · 496 | -1.6 | 20.2 | -3.7 | 28.1 | 751 | 201 |
| Cranbrook (BC) | `clim-bc-cranbrook-a` | 1991–2020 | airport · 11.9 · 940 | -6.1 | 19.2 | -10.1 | 26.9 | 386 | 133 |
| Kamloops (BC) | `clim-bc-kamloops-a` | 1991–2020 | airport · 7.8 · 345 | -2.7 | 21.9 | -5.7 | 29.3 | 273 | 63 |
| Kelowna (BC) | `clim-bc-kelowna-a` | 1981–2010 | airport · 11.3 · 430 | -2.5 | 19.5 | -5.8 | 27.9 | 387 | 89 |
| Nelson (BC) | `clim-bc-nelson-cs` | 1991–2020 | in town · 0.7 · 535 | -0.7 | 20.7 | -2.9 | 28.5 | — | — |
| Penticton (BC) | `clim-bc-penticton-a` | 1991–2020 | airport · 4.3 · 344 | -0.8 | 21.4 | -3.2 | 29.2 | 344 | 62 |
| Prince George (BC) | `clim-bc-prince-george-a` | 1991–2020 | airport · 5.5 · 691 | -7.8 | 15.9 | -11.7 | 22.6 | 590 | 204 |
| Vancouver (BC) | `clim-bc-vancouver-harbour-cs` | 1991–2020 | in town · 3.9 · 2 | 5.3 | 19.0 | 3.3 | 23.0 | 1537 | — |
| Vancouver (BC) | `clim-bc-vancouver-intl-a` | 1991–2020 | airport · 9.0 · 4 | 4.1 | 18.2 | 1.4 | 22.4 | 1160 | 37 |
| Victoria (BC) | `clim-bc-victoria-gonzales-cs` | 1991–2020 | in town · 3.4 · 70 | 5.8 | 16.3 | 3.8 | 20.6 | 675 | — |
| Victoria (BC) | `clim-bc-victoria-intl-a` | 1991–2020 | airport · 24.8 · 20 | 4.6 | 17.2 | 1.6 | 22.7 | 901 | 39 |
| Banff (AB) | `clim-ab-banff-cs` | 1991–2020 | in town · 2.3 · 1397 | -8.5 | 14.7 | -13.5 | 22.5 | 454 | 184 |
| Calgary (AB) | `clim-ab-calgary-intl-a` | 1991–2020 | airport · 9.1 · 1099 | -7.6 | 16.9 | -13.5 | 23.5 | 445 | 139 |
| Edmonton (AB) | `clim-ab-edmonton-blatchford` | 1991–2020 | in town · 4.6 · 671 | -10.3 | 18.1 | -14.7 | 23.5 | 422 | 124 |
| Edmonton (AB) | `clim-ab-edmonton-intl-a` | 1991–2020 | airport · 25.0 · 723 | -12.3 | 16.2 | -18.1 | 23.0 | 434 | 127 |
| Lethbridge (AB) | `clim-ab-lethbridge-a` | 1991–2020 | airport · 7.7 · 929 | -6.0 | 18.4 | -12.1 | 26.3 | 372 | 108 |
| Regina (SK) | `clim-sk-regina-intl-a` | 1991–2020 | airport · 4.9 · 578 | -14.7 | 18.6 | -20.0 | 25.6 | 390 | 105 |
| Saskatoon (SK) | `clim-sk-saskatoon-intl-a` | 1991–2020 | airport · 3.7 · 504 | -15.4 | 18.3 | -20.7 | 25.0 | 357 | 91 |
| Winnipeg (MB) | `clim-mb-winnipeg-intl-a` | 1991–2020 | airport · 7.2 · 239 | -16.3 | 19.5 | -21.2 | 25.8 | 519 | 126 |
| Greater Sudbury (ON) | `clim-on-sudbury-a` | 1991–2020 | airport · 19.5 · 348 | -12.7 | 19.1 | -17.5 | 25.0 | 912 | 263 |
| Kingston (ON) | `clim-on-kingston-pumping-station` | 1981–2010 | in town · 2.6 · 76 | -7.0 | 21.5 | -11.4 | 25.9 | 951 | 160 |
| London (ON) | `clim-on-london-a` | 1991–2020 | airport · 9.8 · 278 | -5.4 | 21.0 | -9.1 | 26.6 | 962 | — |
| Ottawa (ON) | `clim-on-ottawa-cda` | 1991–2020 | in town · 3.9 · 79 | -9.6 | 21.3 | -14.0 | 26.7 | 938 | 184 |
| Ottawa (ON) | `clim-on-ottawa-intl-a` | 1991–2020 | airport · 10.5 · 114 | -10.0 | 21.2 | -14.3 | 27.0 | 930 | 232 |
| Thunder Bay (ON) | `clim-on-thunder-bay-a` | 1991–2020 | airport · 5.2 · 199 | -13.4 | 18.0 | -19.2 | 24.9 | — | — |
| Toronto (ON) | `clim-on-toronto-city` | 1991–2020 | in town · 4.3 · 112 | -3.5 | 22.5 | -6.7 | 27.0 | 823 | — |
| Montréal (QC) | `clim-qc-montreal-trudeau-intl-a` | 1991–2020 | airport · 16.0 · 36 | -9.2 | 21.7 | -13.5 | 26.7 | 1041 | 217 |
| Québec (QC) | `clim-qc-quebec-jean-lesage-intl-a` | 1991–2020 | airport · 13.4 · 74 | -11.9 | 19.5 | -16.7 | 25.0 | 1173 | — |
| Sherbrooke (QC) | `clim-qc-lennoxville` | 1991–2020 | in town · 6.7 · 181 | -9.5 | 19.7 | -14.9 | 25.7 | 1015 | — |
| Sherbrooke (QC) | `clim-qc-sherbrooke-a` | 1991–2020 | airport · 16.2 · 241 | -10.8 | 18.8 | -16.5 | 25.3 | — | — |
| Fredericton (NB) | `clim-nb-fredericton-a` | 1991–2020 | airport · 13.5 · 21 | -9.2 | 19.7 | -14.6 | 25.9 | 1022 | 241 |
| Moncton (NB) | `clim-nb-moncton-a` | 1991–2020 | airport · 9.0 · 71 | -8.4 | 19.3 | -13.3 | 25.1 | 1203 | 310 |
| Saint John (NB) | `clim-nb-saint-john-a` | 1991–2020 | airport · 13.7 · 109 | -7.9 | 17.3 | -13.2 | 23.0 | 1271 | 215 |
| Halifax (NS) | `clim-ns-halifax-stanfield-intl-a` | 1991–2020 | airport · 26.8 · 145 | -5.7 | 19.2 | -10.1 | 24.2 | 1393 | 215 |
| Charlottetown (PE) | `clim-pe-charlottetown-a` | 1991–2020 | airport · 5.4 · 49 | -7.3 | 19.0 | -11.5 | 23.6 | 1136 | 285 |
| Corner Brook (NL) | `clim-nl-corner-brook` | 1991–2020 | in town · 4.0 · 152 | -6.2 | 17.6 | -9.9 | 22.8 | 1293 | 408 |
| St. John's (NL) | `clim-nl-st-johns-intl-a` | 1991–2020 | airport · 7.2 · 140 | -4.2 | 16.0 | -7.8 | 20.9 | 1539 | 363 |
| Whitehorse (YT) | `clim-yt-whitehorse-a` | 1991–2020 | airport · 1.8 · 706 | -15.0 | 14.5 | -18.9 | 20.5 | 280 | 148 |
| Inuvik (NT) | `clim-nt-inuvik-a` | 1991–2020 | airport · 11.9 · 68 | -24.9 | 14.2 | -28.4 | 19.3 | 250 | — |
| Yellowknife (NT) | `clim-nt-yellowknife-a` | 1991–2020 | airport · 3.8 · 206 | -25.5 | 17.1 | -29.4 | 21.5 | 294 | 155 |
| Iqaluit (NU) | `clim-nu-iqaluit-a` | 1991–2020 | airport · 1.6 · 34 | -26.0 | 8.1 | -29.9 | 12.0 | 361 | 190 |

Notes on gaps. Nelson's 1991–2020 station publishes temperature and only some months of
precipitation, so the West Kootenay precipitation figure comes from Castlegar (1981–2010).
Thunder Bay and Sherbrooke airport publish no 1991–2020 precipitation. Sherbrooke's precipitation
comes from Lennoxville, a borough of Sherbrooke. Thunder Bay precipitation is parked (see
`STATUS.md`).

## Table B: bright sunshine (1981–2010 records only)

The table is sorted by annual hours. Only values with ECCC code A–D are used, matching what ECCC
publishes on its site. The temperatures in this table are also 1981–2010 and differ slightly from
Table A.

| City | Record (1981–2010) | Sunshine Jan h | Sunshine Jul h | Sunshine annual h | Jan mean °C | Jul mean °C | Annual snow cm |
|---|---|---|---|---|---|---|---|
| Calgary (AB) | `clim-ab-calgary-intl-a-1981-2010` | 120 | 314 | 2396 | -7.1 | 16.5 | 129 |
| Edmonton (AB) | `clim-ab-edmonton-intl-a-1981-2010` | 101 | 302 | 2310 | -12.1 | 16.2 | 118 |
| Saskatoon (SK) | `clim-sk-saskatoon-src-1981-2010` | 106 | 309 | 2268 | -13.9 | 19.0 | 77 |
| Yellowknife (NT) | `clim-nt-yellowknife-a-1981-2010` | 51 | 358 | 2256 | -25.6 | 17.0 | 158 |
| Cranbrook (BC) | `clim-bc-cranbrook-a-1981-2010` | 64 | 315 | 2190 | -6.1 | 18.7 | 125 |
| Victoria (BC) | `clim-bc-victoria-intl-a-1981-2010` | 71 | 318 | 2109 | 4.6 | 16.9 | 40 |
| Ottawa (ON) | `clim-on-ottawa-cda-1981-2010` | 99 | 279 | 2084 | -10.2 | 21.2 | 175 |
| Kamloops (BC) | `clim-bc-kamloops-a-1981-2010` | 55 | 303 | 2080 | -2.8 | 21.5 | 64 |
| Toronto (ON) | `clim-on-toronto-city-1981-2010` | 86 | 280 | 2066 | -3.7 | 22.3 | 122 |
| Montréal (QC) | `clim-qc-montreal-trudeau-intl-a-1981-2010` | 101 | 272 | 2051 | -9.7 | 21.2 | 210 |
| Moncton (NB) | `clim-nb-moncton-a-1981-2010` | 116 | 256 | 2002 | -8.9 | 18.8 | 325 |
| Greater Sudbury (ON) | `clim-on-sudbury-a-1981-2010` | 86 | 275 | 1973 | -13.0 | 19.1 | 263 |
| Dartmouth / Halifax (NS) | `clim-ns-shearwater-a-1981-2010` | 110 | 235 | 1962 | -4.6 | 18.1 | 182 |
| Kelowna (BC) | `clim-bc-kelowna-a` | 39 | 298 | 1949 | -2.5 | 19.5 | 89 |
| Vancouver (BC) | `clim-bc-vancouver-intl-a-1981-2010` | 60 | 290 | 1938 | 4.1 | 18.0 | 38 |
| Penticton (BC) | `clim-bc-penticton-a-1981-2010` | 35 | 288 | 1923 | -0.6 | 21.0 | 59 |
| Prince George (BC) | `clim-bc-prince-george-a-1981-2010` | 49 | 286 | 1918 | -7.9 | 15.8 | 205 |
| Québec (QC) | `clim-qc-quebec-jean-lesage-intl-a-1981-2010` | 99 | 252 | 1916 | -12.8 | 19.3 | 303 |
| Castlegar (BC) | `clim-bc-castlegar-a` | 39 | 292 | 1854 | -1.6 | 20.2 | 201 |
| Whitehorse (YT) | `clim-yt-whitehorse-a-1981-2010` | 44 | 248 | 1827 | -15.2 | 14.3 | 142 |
| Gander (NL) | `clim-nl-gander-intl-a-1981-2010` | 94 | 219 | 1624 | -7.1 | 16.3 | 452 |
| London (ON) | `clim-on-london-intl-airport-1981-2010` | — | — | — | -5.6 | 20.8 | 194 |
| Kingston (ON) | `clim-on-kingston-pumping-station` | — | — | — | -7.0 | 21.5 | 160 |

No sunshine normal of code A–D exists for Winnipeg, Regina and Saint John: ECCC lists their
1981–2010 sunshine with code E, meaning 10–14 years of data, and those values are not used. There
is no usable sunshine normal for Lethbridge, St. John's, Charlottetown, Fredericton, Halifax
Stanfield, Thunder Bay, Banff, Corner Brook, Iqaluit or Inuvik either. They show as *no data* in
`comparative-answers.md`.

**The sunshine pattern.**

- **The Prairies and southern Alberta are the sunniest year-round.** Calgary has about 2,400 hours,
  and it also has the most January sunshine of any city here.
- **The south-west BC coast is sunny in summer and dull in winter.** Victoria gets 318 hours in July
  against 71 in January.
- **The Okanagan and Kootenay valleys are among the dullest places in Canada in winter.**
  Penticton gets 35 hours in January, Kelowna and Castlegar 39, despite bright summers. The cause is
  persistent valley cloud in winter (inversions), an agent-04 interpretation consistent with the
  data.
- **Yellowknife's 358 July hours** reflect very long summer days.

## Table C: winter severity and summer heat indicators

All values are days per year from the same records. A dash means the value is not published for
that station and period. The 1981–2010 rows (Kelowna, Castlegar, Kingston) do not carry the humidex
or freezing-rain counts, because the 1981–2010 pages do not show them.

| City | Record | Days max ≤ 0 °C | Nights < −20 °C | Days snow depth ≥ 1 cm | Days max > 30 °C | Days humidex ≥ 30 | Days freezing rain | Frost-free days |
|---|---|---|---|---|---|---|---|---|
| Castlegar (BC) | `clim-bc-castlegar-a` | 34 | 0 | 90 | 32 | — | — | 154 |
| Cranbrook (BC) | `clim-bc-cranbrook-a` | 57 | 10 | 99 | 19 | 20 | 1.6 | — |
| Kamloops (BC) | `clim-bc-kamloops-a` | 33 | 3 | 48 | 36 | 37 | 0.5 | 170 |
| Kelowna (BC) | `clim-bc-kelowna-a` | 31 | 3 | 65 | 26 | — | — | — |
| Nelson (BC) | `clim-bc-nelson-cs` | 25 | 0 | — | 27 | 38 | — | — |
| Penticton (BC) | `clim-bc-penticton-a` | 22 | 0 | 25 | 29 | 38 | 0.5 | 160 |
| Prince George (BC) | `clim-bc-prince-george-a` | 66 | 17 | 120 | 4 | 5 | 4.4 | — |
| Vancouver (BC) | `clim-bc-vancouver-harbour-cs` | 2 | 0 | — | 1 | — | — | — |
| Vancouver (BC) | `clim-bc-vancouver-intl-a` | 3 | 0 | 8 | 0 | 6 | 0.6 | 235 |
| Victoria (BC) | `clim-bc-victoria-gonzales-cs` | 1 | 0 | — | 1 | 3 | — | — |
| Victoria (BC) | `clim-bc-victoria-intl-a` | 2 | 0 | 8 | 2 | 6 | 0.6 | 213 |
| Banff (AB) | `clim-ab-banff-cs` | 80 | 23 | — | 3 | 2 | — | 64 |
| Calgary (AB) | `clim-ab-calgary-intl-a` | 61 | 22 | 92 | 5 | 9 | 4.0 | — |
| Edmonton (AB) | `clim-ab-edmonton-blatchford` | 86 | 24 | — | 4 | 10 | — | — |
| Edmonton (AB) | `clim-ab-edmonton-intl-a` | 91 | 38 | 145 | 3 | 10 | 5.4 | — |
| Lethbridge (AB) | `clim-ab-lethbridge-a` | 48 | 22 | — | 18 | 24 | — | — |
| Regina (SK) | `clim-sk-regina-intl-a` | 106 | 45 | — | 13 | 28 | 8.4 | — |
| Saskatoon (SK) | `clim-sk-saskatoon-intl-a` | 110 | 49 | — | 11 | 22 | 6.5 | — |
| Winnipeg (MB) | `clim-mb-winnipeg-intl-a` | 115 | 52 | — | 12 | 37 | 9.4 | — |
| Greater Sudbury (ON) | `clim-on-sudbury-a` | 99 | 28 | 131 | 6 | 25 | 16.0 | 136 |
| Kingston (ON) | `clim-on-kingston-pumping-station` | 57 | 9 | — | 4 | — | — | 169 |
| London (ON) | `clim-on-london-a` | 57 | 4 | — | 11 | 55 | 6.9 | 165 |
| Ottawa (ON) | `clim-on-ottawa-cda` | 74 | 15 | 115 | 13 | 50 | 9.8 | 158 |
| Ottawa (ON) | `clim-on-ottawa-intl-a` | 76 | 16 | 118 | 15 | 49 | 14.0 | 160 |
| Thunder Bay (ON) | `clim-on-thunder-bay-a` | — | 42 | — | — | 26 | — | — |
| Toronto (ON) | `clim-on-toronto-city` | 44 | 2 | — | 14 | 59 | — | 208 |
| Montréal (QC) | `clim-qc-montreal-trudeau-intl-a` | 73 | 12 | 101 | 11 | 50 | 4.9 | 167 |
| Québec (QC) | `clim-qc-quebec-jean-lesage-intl-a` | 92 | 26 | — | 5 | 34 | — | 148 |
| Sherbrooke (QC) | `clim-qc-lennoxville` | 70 | 23 | — | 7 | 44 | — | — |
| Sherbrooke (QC) | `clim-qc-sherbrooke-a` | 78 | 30 | — | 5 | 37 | — | — |
| Fredericton (NB) | `clim-nb-fredericton-a` | 68 | 17 | 109 | 10 | 37 | 8.5 | — |
| Moncton (NB) | `clim-nb-moncton-a` | 72 | 12 | 120 | 6 | 34 | 14.5 | 135 |
| Saint John (NB) | `clim-nb-saint-john-a` | 60 | 13 | — | 1 | 12 | 7.5 | — |
| Halifax (NS) | `clim-ns-halifax-stanfield-intl-a` | 54 | 3 | 84 | 3 | 28 | 12.9 | — |
| Charlottetown (PE) | `clim-pe-charlottetown-a` | 70 | 6 | 113 | 1 | 25 | 14.8 | 153 |
| Corner Brook (NL) | `clim-nl-corner-brook` | 77 | 2 | 133 | 1 | 12 | — | — |
| St. John's (NL) | `clim-nl-st-johns-intl-a` | 64 | 0 | 114 | 0 | 10 | 30.8 | 142 |
| Whitehorse (YT) | `clim-yt-whitehorse-a` | 119 | 45 | — | 1 | 1 | 1.0 | 85 |
| Inuvik (NT) | `clim-nt-inuvik-a` | 204 | 124 | — | 1 | 2 | — | 78 |
| Yellowknife (NT) | `clim-nt-yellowknife-a` | 174 | 103 | — | 0 | 1 | 6.3 | — |
| Iqaluit (NU) | `clim-nu-iqaluit-a` | 206 | 122 | 231 | 0 | 0 | 3.5 | — |

## Where the airport station differs from the city

Several cities have both an airport record and an in-town record, so the difference can be measured
rather than assumed.

- **Victoria.** The airport is 24.8 km north, on the Saanich Peninsula. Its annual precipitation is
  901 mm against 675 mm in the city at Gonzales. The city is about 1 °C milder in January (5.8 °C
  against 4.6 °C) and about 2 °C cooler on July afternoons (20.6 °C against 22.7 °C). Records:
  `clim-bc-victoria-intl-a` and `clim-bc-victoria-gonzales-cs`. **This difference is material:
  downtown Victoria is drier and milder than the airport suggests.**
- **Vancouver.** The airport is on the Fraser delta, 9 km south-south-west of the reference point.
  Vancouver Harbour gets 1,537 mm a year against 1,160 mm at the airport, and its January mean is
  5.3 °C against 4.1 °C. Records: `clim-bc-vancouver-intl-a` and `clim-bc-vancouver-harbour-cs`.
  Rain increases toward the North Shore mountains; this is agent-04's reading of the direction of
  the difference, not a figure.
- **Edmonton.** The international airport is 25 km south of downtown and much colder. Its January
  mean is −12.3 °C against −10.3 °C at Blatchford in the city, and it has 38 nights below −20 °C
  against 24. Records: `clim-ab-edmonton-intl-a` and `clim-ab-edmonton-blatchford`. **Use the city
  station when judging Edmonton winters.**
- **Ottawa.** Temperatures are almost identical at the airport and at the Central Experimental Farm
  (`clim-on-ottawa-cda`). Snowfall is 232 cm at the airport against 184 cm at the Farm
  (`clim-on-ottawa-intl-a`).
- **Sherbrooke.** The airport is 16 km out and colder than Lennoxville, in the city: −10.8 °C
  against −9.5 °C in January, with 30 nights below −20 °C against 23. Records:
  `clim-qc-sherbrooke-a` and `clim-qc-lennoxville`.
- **Halifax.** Stanfield airport is 27 km inland. The coastal Shearwater station in Dartmouth
  (1981–2010, `clim-ns-shearwater-a-1981-2010`) has a January mean of −4.6 °C, against −5.7 °C at
  Stanfield in 1991–2020 (`clim-ns-halifax-stanfield-intl-a`). Because the periods differ, this
  comparison is indicative only. The likely direction is that the harbour is milder in winter and
  cooler in summer.
- **No in-city station in this set.** Montréal (airport 16 km from Old Montréal), Québec city,
  Fredericton, Moncton, Saint John, St. John's, Charlottetown, Calgary, Regina, Saskatoon and
  Winnipeg have no in-city record here, so the city–airport difference is **unquantified** for
  them.

## Daylight

Daylight is computed by agent-04 from latitude and stored as `daylight_h_computed`; it is not an
ECCC value. The figures below are for mid-December and mid-June:

| Place | Mid-December | Mid-June |
|---|---|---|
| Toronto | about 8.9 h | 15.4 h |
| Victoria | 8.3 h | 16.1 h |
| Edmonton | 7.5 h | 17.0 h |
| Whitehorse | 5.7 h | 19.1 h |
| Yellowknife | 5.0 h | 19.9 h |
| Iqaluit | 4.4 h | 20.7 h |
| Inuvik | polar night (0 h) | 24 h daylight |

North of about 60° the short winter days are a lifestyle factor in their own right, as large as the
cold itself.

## What each climate feels like through the year

This section is agent-04's professional interpretation of the tables above. It describes typical
years in the normals period and is not an outlook.

**1. Mild, wet Pacific coast: Vancouver, Victoria.** Records: `clim-bc-vancouver-intl-a`,
`clim-bc-vancouver-harbour-cs`, `clim-bc-victoria-gonzales-cs`, `clim-bc-victoria-intl-a`.

- *Winter* is grey, cool and wet rather than cold. January means are 4–6 °C and frost is rare. The
  city gets snow on only a few days, while the North Shore mountains above Vancouver hold ski-area
  snow. Vancouver airport has about 20 days with precipitation in January.
- *Spring* starts early by Canadian standards: the frost-free season is 213–235 days at the two
  airports, the longest in this set.
- *Summer* is dry and sunny but rarely hot. July highs are about 21–23 °C and there are 0–2 days above
  30 °C. The 2021 heat dome showed that rare heat can still be deadly here
  (`hazard-bc-extreme-heat`).
- *Autumn* rains return from October, with atmospheric-river storms (`hazard-bc-atmospheric-river-flood`).
- Victoria city is clearly drier (675 mm) and sunnier than Vancouver (Table B: 2,109 h against
  1,938 h, both measured at airports).

**2. Dry interior valleys: Kamloops, Penticton, Kelowna.** Records: `clim-bc-kamloops-a`,
`clim-bc-penticton-a`, `clim-bc-kelowna-a`.

- *Winter* is short and only moderately cold, with January means of −1 to −3 °C and almost no
  nights below −20 °C. It is often overcast, with only 35–55 hours of January sunshine.
- *Summer* is the hottest and driest of any city here. July highs are 28–29 °C, with 26–36 days
  above 30 °C and 270–390 mm of precipitation a year.
- Spring and autumn are long and pleasant.
- Summer wildfire smoke is the main drawback (`hazard-bc-interior-wildfire`).

**3. Mountain valleys of the Kootenays and Rockies: Nelson/Castlegar, Cranbrook, Banff.** Records:
`clim-bc-nelson-cs`, `clim-bc-castlegar-a`, `clim-bc-cranbrook-a`, `clim-ab-banff-cs`.

- The *West Kootenay* (Nelson, Castlegar) has mild valley winters for interior Canada, with a
  January mean of −1 to −2 °C. Snowfall is substantial: 201 cm at Castlegar, and more in the
  mountains around it. Summers are hot (July highs around 28 °C).
- *Cranbrook*, in the Rocky Mountain Trench, is colder in winter (10 nights below −20 °C) but dry
  and sunny (2,190 h).
- *Banff*, at about 1,400 m, has a mountain climate. July means are under 15 °C, there are 23
  nights below −20 °C and the frost-free season is 64 days.

**4. Chinook foothills and dry prairie: Calgary and Lethbridge.** Records: `clim-ab-calgary-intl-a`,
`clim-ab-lethbridge-a`, `clim-ab-calgary-intl-a-1981-2010`.

- These are the sunniest cities in the set, with about 2,400 hours at Calgary.
- *Winter* alternates cold snaps (about 22 nights below −20 °C) with mild chinook spells. That
  pattern comes from agent-04 knowledge of chinooks and is consistent with Calgary's moderate
  January mean of −7.6 °C. Snow rarely stays long: there are about 92 days with snow on the ground
  at Calgary.
- *Summer* is warm, dry and low in humidity. Thunderstorms and hail are common
  (`hazard-ab-calgary-hail`).

**5. Continental prairie and boreal: Edmonton, Saskatoon, Regina, Winnipeg, Prince George, Thunder
Bay, Sudbury.**

- *Winter* is long and properly cold. January means are −8 °C (Prince George) to −16 °C
  (Winnipeg), with 17–52 nights below −20 °C and snow on the ground for four to five months where
  published.
- *Summer* is warm and bright, with July highs of about 23–26 °C.
- Winnipeg adds summer humidity (37 days with humidex ≥ 30). Sudbury and Thunder Bay add Shield
  lakes and forest.
- Sunshine is high on the Prairies (Edmonton 2,310 h and Saskatoon 2,268 h, measured at the
  airport and SRC stations respectively).

**6. Humid continental south-east: Toronto, London, Ottawa, Kingston, Montréal, Québec city,
Sherbrooke.**

- *Winter* runs from mild-ish to moderate in southern Ontario: Toronto's January mean is −3.5 °C
  with 2 nights below −20 °C. It is colder and snowier going east and north: Montréal −9.2 °C and
  217 cm of snow, Québec city −11.9 °C.
- Freezing rain is a feature of the St. Lawrence and Ottawa valleys: 10–14 days a year at Ottawa
  (`hazard-qc-on-ice-storm`).
- *Summers* are the hottest and most humid in Canada, with 50–59 days of humidex ≥ 30 at Toronto,
  London, Ottawa and Montréal.
- Autumn foliage and a long shoulder season are a strength. That point is agent-04 interpretation.

**7. Maritime Atlantic: Halifax, Saint John, Moncton, Fredericton, Charlottetown, St. John's,
Corner Brook.**

- *Winter* is cold but rarely extreme near the sea (0–6 nights below −20 °C at Halifax, St. John's
  and Charlottetown). It is changeable, with rain, snow and freezing rain in the same week.
- These are the wettest cities, at 1,000–1,540 mm a year, and also some of the snowiest:
  285–408 cm at Charlottetown, St. John's and Corner Brook.
- St. John's records 31 freezing-rain days and 114 fog days a year.
- *Summers* are cool to warm and pleasant, with July highs of 21–26 °C.
- Late-summer and autumn post-tropical storms are the main hazard
  (`hazard-ca-atlantic-post-tropical-storms`).

**8. Subarctic and Arctic: Whitehorse, Yellowknife, Inuvik, Iqaluit.**

- *Winter* is long and dark: about 5–6 hours of daylight in December at Whitehorse and Yellowknife,
  and polar night at Inuvik. There are 45 nights below −20 °C at Whitehorse and over 100 farther
  north.
- *Summer* is short but very long-day. Yellowknife has 358 hours of July sunshine.
- Whitehorse is the mildest and driest of the four (280 mm, January mean −15 °C).
- Iqaluit's July mean is only 8.1 °C.
- Permafrost shapes building in all four (`hazard-ca-permafrost-thaw`).
