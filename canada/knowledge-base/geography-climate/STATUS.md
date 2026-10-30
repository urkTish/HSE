# Agent 04 status: geography and climate

Last updated 2026-10-30 · Phase 1

## Done

The validator passes:
`node canada/knowledge-base/scripts/validate.mjs canada/knowledge-base/geography-climate` reports
**113 record(s) checked, 0 failed, 0 warning(s), 0 non-record JSON file(s) skipped.**

| Path | Contents |
|---|---|
| `provinces-territories.md` | One section per province and territory, plus a national table of physiographic regions. |
| `climate-comparison.md` | Three generated tables (temperature and precipitation, sunshine, winter and summer indicators), airport-versus-city differences, daylight, and eight climate types described season by season. |
| `hazards.md` | Hazard matrix and narrative with settlement implications. |
| `comparative-answers.md` | Band thresholds, bands for 34 cities, sensitivity analysis, and answers to the SPEC §8 questions (`professional_interpretation`). |
| `climate/` | 61 `clim` records. |
| `records/` | 52 records: 18 `landform`, 13 `region`, 21 `hazard`. |

The 61 `clim` records cover every province and territory and 34 cities and towns:

- **38 primary 1991–2020 records.** Several cities have both an airport and an in-town record:
  Victoria, Vancouver, Edmonton, Ottawa and Sherbrooke (Sherbrooke A and Lennoxville).
- **3 primary 1981–2010 records:** Kelowna A, Castlegar A and Kingston Pumping Station. For these
  stations the 1991–2020 normals publish no precipitation for most months.
- **20 supplementary 1981–2010 records** (ids ending `-1981-2010`). They provide bright sunshine,
  which is not part of the 1991–2020 normals, and snowfall where 1991–2020 snowfall is missing.
- **Large provinces have several stations:**
  - BC: 11 locations (Victoria ×2, Vancouver ×2, Kelowna, Penticton, Kamloops, Nelson, Castlegar,
    Cranbrook, Prince George).
  - Alberta: 4 cities.
  - Ontario: 6 cities.
  - Quebec: 3 cities.
  - The territories: Whitehorse, Yellowknife, Inuvik and Iqaluit.
- **How the values were sourced:**
  - Every value was parsed from the ECCC normals results page.
  - For the 1991–2020 records, the values were compared cell by cell with ECCC's 1991–2020 bulk CSV
    and match exactly.
  - For the 1981–2010 records, annual values were compared with the MSC GeoMet API where the
    station is in it.
  - Distance to the city centre was computed from the NRCan CGNDB reference point. A downtown proxy
    was used for Toronto, Ottawa, Greater Sudbury and St. John's.

## In progress and parked

| Item | Reason | Next step |
|---|---|---|
| **Thunder Bay precipitation and snow** | ECCC's 1991–2020 Thunder Bay composite publishes temperature only. The 1981–2010 normals search finds no station named "Thunder Bay". `clim-on-thunder-bay-a` therefore has null precipitation and snow. | Search the 1981–2010 normals by proximity (lat 48.37, lon −89.32) or by climate ID 6048261. |
| **Nelson precipitation** | Nelson CS (1991–2020) publishes only some months. Castlegar A (1981–2010, 30 km away) stands in for the West Kootenay. | Accept, or add a Nelson 1981–2010 station if one exists. |
| **City-centre stations missing** | No in-city record for Montréal, Québec city, Calgary, Regina, Saskatoon, Winnipeg, Fredericton, Moncton, Saint John, Halifax, St. John's or Charlottetown, so the airport-versus-city difference is unquantified there. | Check for ECCC in-city normals stations (for example McGill, Calgary city stations). |
| **Cities named in the charter without their own record** | Canmore is covered by `clim-ab-banff-cs` (no ECCC normals for Canmore). London has precipitation but its 1991–2020 snowfall is missing; 1981–2010 is supplied by `clim-on-london-intl-airport-1981-2010`. Every other candidate city has a record. | None needed. |
| **PEI coastal erosion** | princeedwardisland.ca and authoringweb.gpei.ca blocked automated access twice (bot check / HTTP 403, and proxy refusal). No PEI erosion hazard record was created. | Fetch the PEI Coastal Property Guide or the provincial erosion page manually, then create `hazard-pe-coastal-erosion`. |
| **2013 southern Alberta flood figures** | No official page with event figures was retrievable (ECCC 2013 top-ten page returns 404). `hazard-ab-bow-elbow-river-flood` is `partially_verified` and holds no 2013 numbers. | Find the archived ECCC 2013 top-ten page or the Alberta flood recovery report. |
| **Appalachian Uplands and Chic-Chocs description** | The Atlas page's Appalachian section did not render. These two landform records are `partially_verified`; their heights are verified. | Source from NRCan (GEO.ca record a3dfbaf4…) or Sépaq / Parc national de la Gaspésie. |
| **Trails, parks and travel times** | Out of Phase 1 time. The comparative answers say travel times are unverified. | Phase 2: `park` and `trail` records. |

## Key findings

1. **Victoria is the only city in the top two bands for both winter mildness and sunshine.**
   Downtown has a January mean of 5.8 °C and 675 mm of precipitation
   (`clim-bc-victoria-gonzales-cs`). Its 1981–2010 airport sunshine is 2,109 h. It stays in the top
   group under every single-step weight change.
2. **The southern BC interior has mild winters and the hottest, driest summers in the set:**
   Kamloops 273 mm and 36 days above 30 °C; Penticton −0.8 °C in January. Its winters are among
   the dullest in Canada (35–55 h of January sun), and it is the core BC wildfire and smoke zone.
3. **Calgary is the sunniest city:** 2,396 h a year and 120 h in January (1981–2010). It has the
   Rockies on the horizon but a cold-band winter, with about 22 nights below −20 °C. Hail and
   mapped river-flood zones are its hazards.
4. **Airport stations can mislead.**
   - Edmonton International is about 2 °C colder in January than in-city Blatchford, with 38 nights
     below −20 °C against 24.
   - Victoria airport has 34% more precipitation than downtown.
   - Vancouver Harbour has 33% more precipitation than the airport.
5. **Southern Ontario and Quebec have the most humid summers:** 50–59 days of humidex ≥ 30 at
   Toronto, London, Ottawa and Montréal. They also have the most freezing rain in the interior
   (Ottawa airport 14 days a year).
6. **The Atlantic cities have mild-ish cold but are the wettest, foggiest and most
   freezing-rain-prone.** St. John's has 1,539 mm of precipitation, 114 fog days and 31
   freezing-rain days. Their major hazard is post-tropical storms (Fiona 2022).
7. **Prairie and northern winters are a different order:** 45–52 nights below −20 °C on the
   Prairies and over 100 in Yellowknife and Iqaluit. In the North, short winter days (5 hours of
   daylight at Yellowknife in December, computed) are as significant as the cold.
8. **Sunshine normals end in 2010.** ECCC's 1991–2020 normals no longer include bright sunshine,
   so any sunshine comparison rests on 1981–2010 data. Several cities (Winnipeg, Regina, Halifax
   airport, St. John's, Charlottetown) have no usable sunshine normal.

## Open questions added

Four lines were appended to `canada/OPEN-QUESTIONS.md` under "From Agent 04":

1. The user's winter limit, as a band.
2. Whether "more sunshine" means winter sunshine or annual sunshine.
3. Within BC, the coast's grey winters against the interior's smoke summers.
4. Whether winter backcountry activities are planned (avalanche relevance).

## Next step

1. Resolve the parked data gaps: Thunder Bay precipitation, PEI erosion and the 2013 Alberta flood
   figures.
2. Add in-city stations for Montréal and Calgary.
3. Once Agent 02 delivers `re` records for the candidate mountain towns, fill the housing-cost
   column in `comparative-answers.md` (handoff line 04-7 in `TASKS.md`, which the coordinator
   should move under Agent 02).
4. Phase 2: `park` and `trail` records for the top-group regions (southern BC, the Rockies, the
   Kootenays), and verified travel times from cities to mountain access points.
