# Natural hazards by region

Agent 04 · researched 2026-10-30 · Phase 1

This page summarises the natural hazards that differ meaningfully between places to live in
Canada. Each hazard is a `hazard` record under `records/`, with its exposed areas, documented
events, practical implications and official sources. The facts about past events are quoted or
paraphrased from official pages; the statements about exposure and implications are agent-04
professional interpretation.

**How to read this.** A past event shows that a place is exposed. It does not predict any year.
Exposure varies street by street, and no province faces any hazard uniformly. Before renting or
buying a specific property, check the municipal or provincial flood map, the wildfire
(FireSmart) guidance and the insurer's view; Agent 02 covers property and insurance rules. The
national direction of change comes from *Canada's Changing Climate Report* (2019). It finds that
warming in Canada is about double the global rate, and more than double in the North. It expects
extreme heat to become more frequent and more intense, more intense rainfall to raise urban flood
risk, coastal flooding to increase with local sea-level rise, and summer water-supply shortages to
become more likely (cited in the hazard records). These are assessments of change, not forecasts
for a place.

## Summary matrix

The matrix records documented exposure only. A blank cell means not documented here, which is
different from no risk.

| Hazard | Most exposed (examples) | Lower exposure (examples) | Records |
|---|---|---|---|
| Wildfire | BC southern and central interior; Rocky Mountain parks; boreal NT, northern prairies, Labrador | Coastal cities, southern Ontario and Quebec lowlands, Maritimes (smoke can still arrive) | `hazard-bc-interior-wildfire`, `hazard-ab-mountain-parks-wildfire`, `hazard-nt-boreal-wildfire`, `hazard-nl-western-labrador-wildfire` |
| Wildfire smoke | Western and northern Canada most often; national in bad years (Montréal, 2023) | none reliably | `hazard-ca-wildfire-smoke` |
| River flooding | Fraser Valley and southern BC interior (atmospheric rivers); Red River Valley; Bow and Elbow rivers | Upland and higher-elevation neighbourhoods anywhere | `hazard-bc-atmospheric-river-flood`, `hazard-mb-red-river-flood`, `hazard-ab-bow-elbow-river-flood` |
| Extreme-rain urban flooding | Halifax region; Montréal; Greater Toronto | none reliably | `hazard-ns-halifax-flash-flood`, `hazard-qc-montreal-heavy-rain-flood`, `hazard-on-southern-ontario-heavy-rain-flood` |
| Hurricanes and post-tropical storms, storm surge | Nova Scotia, PEI, Newfoundland, New Brunswick and the eastern Quebec coasts | Inland and western Canada | `hazard-ca-atlantic-post-tropical-storms` |
| Drought | Southern Alberta, Saskatchewan and Manitoba | Coastal and Atlantic regions | `hazard-ca-prairie-drought` |
| Extreme heat | Southern BC (2021), interior valleys; humid heat in southern Ontario and Quebec (see humidex days in `climate-comparison.md`) | North; Atlantic coast | `hazard-bc-extreme-heat` |
| Extreme cold | Prairies, North, northern Ontario and Quebec | South coast of BC | `hazard-ca-extreme-cold` |
| Avalanche (backcountry) | Rockies, Columbia and Coast mountains; Chic-Chocs | Everywhere outside mountain backcountry | `hazard-ca-mountain-avalanche` |
| Ice storm and freezing rain | St. Lawrence and Ottawa valleys, eastern Ontario, New Brunswick; St. John's has the highest freezing-rain day count in the set | Prairies, BC coast, Yukon | `hazard-qc-on-ice-storm` |
| Severe thunderstorms and derechos | Windsor–Québec corridor | | `hazard-on-qc-derecho` |
| Hail | Calgary and the central Alberta foothills | | `hazard-ab-calgary-hail` |
| Permafrost thaw | Territories, northern provinces | South of the discontinuous zone | `hazard-ca-permafrost-thaw` |
| Earthquake and tsunami | South-western BC, especially the outer coast of Vancouver Island | Most of the country | `hazard-bc-cascadia-earthquake` |

## By hazard

### Wildfire and smoke

According to NRCan, over 8,000 wildland fires burn more than 2.1 million ha in an average year.
The 2023 season was historic: more than 14.6 million ha burned and over 230,000 people were
evacuated. ECCC's figure for that year is 184,493 km².

| Area | Documented events | Record |
|---|---|---|
| BC interior | 2021: 1,522 fires burned 889,813 ha and forced 50,000 evacuations; Lytton was about 90% destroyed. | `hazard-bc-interior-wildfire` |
| Jasper | 2024: the fire burned 32,722 ha and destroyed 358 buildings in the town. | `hazard-ab-mountain-parks-wildfire` |
| Yellowknife | 2023: about 20,000 residents were evacuated. | `hazard-nt-boreal-wildfire` |
| Labrador City | 2024: the whole town of over 7,000 people was evacuated. | `hazard-nl-western-labrador-wildfire` |

**Practical effect.**

- Smoke is the hazard most residents actually experience. ECCC counts days with "smoke or haze" in
  the 1991–2020 normals of several stations, stored in each clim record's `phenomena`.
- Mountain and northern towns with one or two road exits face harder evacuations.
- Homes in the wildland–urban interface face FireSmart expectations and higher insurance scrutiny.
- The hot, dry, sunny summers of the BC interior are the same climate that drives the fire risk.
  For the user's sunshine preference, this is the main trade-off.

### Flooding

There are three different mechanisms:

1. **Autumn atmospheric rivers on the BC coast and in the southern interior.** In November 2021,
   200–300 mm of rain fell in 2.5 days. At least 6 people died, about 15,000 were evacuated and
   highways were cut into 2022 (`hazard-bc-atmospheric-river-flood`).
2. **Spring snowmelt and rain-on-snow river floods.** These affect the Red River, where Winnipeg's
   floodway now targets a 1-in-700-year event (`hazard-mb-red-river-flood`), and the Bow and Elbow
   rivers (`hazard-ab-bow-elbow-river-flood`). For Calgary's 2013 flood, no official figures were
   retrieved, so none are stored.
3. **Short, extreme rainfall over cities.**
   - Bedford in Halifax had 100 mm in one hour in July 2023, a national record per ECCC
     (`hazard-ns-halifax-flash-flood`).
   - Montréal–Trudeau had 154 mm in a day in August 2024 (`hazard-qc-montreal-heavy-rain-flood`).
   - Toronto Pearson had 97.8 mm on 16 July 2024 (`hazard-on-southern-ontario-heavy-rain-flood`).

**Implications.** Check the floodplain map for any specific address; the City of Calgary publishes
flood hazard maps with four risk categories. Check overland-flood insurance availability (a
question for Agent 02). Basement apartments are more exposed in heavy-rain cities.

### Coastal storms

Fiona (24 September 2022) reached eastern Nova Scotia with sustained winds of 165 km/h and a
pressure of 932.7 hPa, the deepest ever recorded over land in Canada. More than 600,000 customers
lost power and insured losses were $846 million. Exposure covers the Atlantic and Gulf coasts,
including PEI and the Îles de la Madeleine (`hazard-ca-atlantic-post-tropical-storms`). PEI's
coastal-erosion data could not be retrieved: the provincial site blocked automated access twice on
2026-10-30. That gap is parked in `STATUS.md`.

### Drought

On the southern Prairies drought recurs. In 2023 the Bow River had its lowest flow since 1911, and
spring precipitation at Lethbridge and Winnipeg was among the lowest in over 100 years
(`hazard-ca-prairie-drought`). Agriculture and Agri-Food Canada's Canadian Drought Monitor is the
official monthly tracker. Live status is not stored here.

### Extreme heat

In the 2021 heat dome Lytton reached 49.6 °C, the Canadian record. The BC Coroners Service
identified 619 heat-related deaths:

- 98% of them occurred indoors;
- 67% of those who died were aged 70 or older;
- 74% were in the Fraser and Vancouver Coastal health regions.

Records: `hazard-bc-extreme-heat`.

**Implication.** On the normally mild coast, many homes have no cooling, so a rental's cooling is
worth checking. Heat that is humid rather than dry is a regular summer feature in southern Ontario
and Quebec: about 50–59 days a year with humidex ≥ 30 at Toronto, London, Ottawa and Montréal, per
the clim records.

### Extreme cold

In the 1991–2020 normals, nights below −20 °C average:

| Place | Nights per year |
|---|---|
| Winnipeg | about 52 |
| Saskatoon | 49 |
| Regina | 45 |
| Whitehorse | 45 |
| Yellowknife | 103 |
| Iqaluit | 122 |
| Toronto | about 2 |
| Vancouver and Victoria | 0 |

January 2024 brought −48.4 °C at Puntzi Mountain, BC, and a record Alberta power demand
(`hazard-ca-extreme-cold`).

### Avalanche

Avalanches are the most significant winter threat to anyone in uncontrolled mountain backcountry.
Parks Canada publishes daily public avalanche forecasts for the mountain national parks from
November to April (`hazard-ca-mountain-avalanche`). The risk falls on people who travel in the
backcountry, not on towns. It matters for the user's hiking and ski interests and is managed
through training, specifically Avalanche Skills Training courses.

### Ice storms and freezing rain

The January 1998 ice storm left up to 100 mm of freezing rain and ice pellets on parts of eastern
Ontario, southern Quebec and New Brunswick. About 35 people died, more than 600,000 were displaced
and over 15,000 troops were deployed (`hazard-qc-on-ice-storm`). The 1991–2020 normals show
freezing rain on:

| Place | Days per year |
|---|---|
| St. John's | 30.8 |
| Moncton | 14.5 |
| Charlottetown | 14.8 |
| Ottawa airport | 14.0 |
| Halifax | 12.9 |
| Vancouver and Victoria | 0.6 |
| Kamloops and Penticton | 0.5 |

### Permafrost thaw

About one-half of Canada's land surface is underlain by permafrost. Thaw is already evident and
damages foundations, roads and airstrips, which raises building and maintenance costs in Inuvik,
Yellowknife, Iqaluit and northern Yukon (`hazard-ca-permafrost-thaw`).

### Earthquake (geological, included for completeness)

South-western BC records about 400 earthquakes a year, and earthquakes able to cause structural
damage occur every decade or so. Cascadia megathrust earthquakes, up to M9, recur every 200–800
years; the last was in 1700. On the outer coast, the first tsunami waves would arrive 15–30
minutes after such an earthquake (`hazard-bc-cascadia-earthquake`).

## What this means for settlement (interpretation)

- **Mild, sunny-summer BC places carry fire, smoke and heat risk.** The interior valleys that
  rank best for mild winters and summer sun (Okanagan, Thompson, Kootenays) are the core BC
  wildfire and smoke zone. The south coast trades this for wet winters, earthquake and tsunami
  exposure, and rare but deadly heat.
- **Calgary has no single dominant hazard.** It is very sunny, and its hazards are hail, river
  flooding in mapped zones and cold snaps.
- **Outside BC, the least severe winter cold is in southern Ontario (Toronto) and on the Atlantic
  coast (St. John's, Halifax).** The Atlantic cities, however, carry the highest storm, fog and
  freezing-rain exposure.
- **The North's constraints are daylight, cold, permafrost and evacuation logistics**, more than
  any single event.
