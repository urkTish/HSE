# Comparative answers: first pass

Agent 04 · 2026-10-30 · Phase 1 · `data_kind: professional_interpretation`

These are first answers to the comparative questions in SPEC §8, built with the method of SPEC
§4. Every rating is an ordinal band in words with written thresholds. The thresholds were fixed
before any city was rated, and every band cites the records it rests on.

**Missing data.** A criterion without evidence is shown as **no data**. It never counts as zero or
as an average.

**Out of scope.**

- Housing cost, employment, healthcare, schools and immigration are not rated here; they belong to
  Agents 01–03. Where a question involves cost, the cost column reads *no data (pending Agent 02)*.
- Nothing here is a forecast. Climate bands describe 1991–2020 normals, or 1981–2010 where marked.

## 1. Band thresholds (written before rating)

### Winter manageability

Each city is rated on its January mean temperature and on the number of nights below −20 °C, both
from 1991–2020 unless the city's main record is 1981–2010. Each indicator gives a band from the
table below. **The city takes the colder of the two bands.**

| Band | January mean | Nights < −20 °C per year |
|---|---|---|
| very mild | ≥ 0 °C | < 0.5 |
| mild | −5 to < 0 °C | 0.5–5 |
| moderate | −10 to < −5 °C | 6–20 |
| cold | −15 to < −10 °C | 21–50 |
| severe | < −15 °C | > 50 |

### Sunshine

Annual bright-sunshine hours. These exist only in the 1981–2010 normals and are used only where
the ECCC code is A–D.

| Band | Annual hours |
|---|---|
| very sunny | ≥ 2,300 |
| sunny | 2,100–2,299 |
| average | 1,900–2,099 |
| dull | 1,700–1,899 |
| very dull | < 1,700 |
| no data | no normal of code A–D |

### Summer humidity and heat

Days per year with humidex ≥ 30, from 1991–2020.

| Band | Days |
|---|---|
| very low | < 5 |
| low | 5–14 |
| moderate | 15–29 |
| high | 30–49 |
| very high | ≥ 50 |

### Wetness

Annual precipitation.

| Band | mm per year |
|---|---|
| dry | < 400 |
| moderately dry | 400–699 |
| moderate | 700–999 |
| wet | 1,000–1,299 |
| very wet | ≥ 1,300 |

### Mountain setting

This is a qualitative ordinal band. It reflects agent-04's reading of the physiographic records;
travel times are not yet verified.

1. **in the mountains**: the town sits in a valley inside a Cordilleran range.
2. **mountains at the edge of the city**: a major range rises directly from the urban area.
3. **mountains on the horizon**: a range or high plateau lies close by, and the town is in a
   mountain valley or a foothills edge.
4. **hills, lakes and Shield forest nearby**: Laurentians, Gatineau Hills, Appalachian or Shield
   uplands, with no alpine terrain.
5. **forest and plateau, mountains at a distance**.
6. **lowland with lake, ravines and escarpment**.
7. **plains**.

The SPEC asks for five bands. This criterion uses seven descriptive steps, and the order rule
treats steps 1–3 as the **top group**.

### Order rule (no points)

USER-PROFILE gives three inferred **strong** preferences, weighted 2: mountains, winter and
sunshine. Humidity and wetness are treated as **flexible**, weighted 1.

1. For each city, count the strong criteria that fall in the top two bands. For mountains, use
   steps 1–3.
2. Break ties by the same count over the flexible criteria.
3. A **no data** criterion does not count as top. It is shown, so the reader can see where missing
   data, not climate, holds a city back.

## 2. Bands by city

The Evidence column lists the record ids. The order of the ids is: winter record, sunshine record,
humidex record, precipitation record.

| City | Winter | Sunshine (1981–2010) | Summer humidex | Wetness | Mountain setting | Evidence |
|---|---|---|---|---|---|---|
| Victoria | very mild | sunny | very low | moderately dry | mountains on the horizon | `clim-bc-victoria-gonzales-cs`, `clim-bc-victoria-intl-a-1981-2010` |
| Vancouver | very mild | average | low | wet | mountains at the edge of the city | `clim-bc-vancouver-intl-a`, `clim-bc-vancouver-intl-a-1981-2010` |
| Kelowna | mild | average | no data | dry | mountains on the horizon | `clim-bc-kelowna-a` |
| Penticton | mild | average | high | dry | mountains on the horizon | `clim-bc-penticton-a`, `clim-bc-penticton-a-1981-2010` |
| Kamloops | mild | average | high | dry | mountains on the horizon | `clim-bc-kamloops-a`, `clim-bc-kamloops-a-1981-2010` |
| Nelson / Castlegar | mild | dull | high | moderate | in the mountains | `clim-bc-nelson-cs`, `clim-bc-castlegar-a` |
| Cranbrook | moderate | sunny | moderate | dry | in the mountains | `clim-bc-cranbrook-a`, `clim-bc-cranbrook-a-1981-2010` |
| Prince George | moderate | average | very low | moderately dry | forest and plateau, mountains at a distance | `clim-bc-prince-george-a`, `clim-bc-prince-george-a-1981-2010` |
| Calgary | cold | very sunny | low | moderately dry | mountains on the horizon | `clim-ab-calgary-intl-a`, `clim-ab-calgary-intl-a-1981-2010` |
| Banff (Bow Valley) | cold | no data | very low | moderately dry | in the mountains | `clim-ab-banff-cs` |
| Edmonton | cold | very sunny | low | moderately dry | plains | `clim-ab-edmonton-blatchford`, `clim-ab-edmonton-intl-a-1981-2010` |
| Lethbridge | cold | no data | moderate | dry | plains | `clim-ab-lethbridge-a` |
| Saskatoon | severe | sunny | moderate | dry | plains | `clim-sk-saskatoon-intl-a`, `clim-sk-saskatoon-src-1981-2010` |
| Regina | cold | no data | moderate | dry | plains | `clim-sk-regina-intl-a` |
| Winnipeg | severe | no data | high | moderately dry | plains | `clim-mb-winnipeg-intl-a` |
| Toronto | mild | average | very high | moderate | lowland with lake, ravines and escarpment | `clim-on-toronto-city`, `clim-on-toronto-city-1981-2010` |
| Ottawa | moderate | average | very high | moderate | hills, lakes and Shield forest nearby | `clim-on-ottawa-cda`, `clim-on-ottawa-cda-1981-2010` |
| Kingston | moderate | no data | no data | moderate | lowland with lake, ravines and escarpment | `clim-on-kingston-pumping-station` |
| London | moderate | no data | very high | moderate | lowland with lake, ravines and escarpment | `clim-on-london-a` |
| Greater Sudbury | cold | average | moderate | moderate | hills, lakes and Shield forest nearby | `clim-on-sudbury-a`, `clim-on-sudbury-a-1981-2010` |
| Thunder Bay | cold | no data | moderate | no data | hills, lakes and Shield forest nearby | `clim-on-thunder-bay-a` |
| Montréal | moderate | average | very high | wet | hills, lakes and Shield forest nearby | `clim-qc-montreal-trudeau-intl-a`, `clim-qc-montreal-trudeau-intl-a-1981-2010` |
| Québec | cold | average | high | wet | hills, lakes and Shield forest nearby | `clim-qc-quebec-jean-lesage-intl-a`, `clim-qc-quebec-jean-lesage-intl-a-1981-2010` |
| Sherbrooke | cold | no data | high | wet | hills, lakes and Shield forest nearby | `clim-qc-lennoxville` |
| Fredericton | moderate | no data | high | wet | lowland with lake, ravines and escarpment | `clim-nb-fredericton-a` |
| Moncton | moderate | average | high | wet | lowland with lake, ravines and escarpment | `clim-nb-moncton-a`, `clim-nb-moncton-a-1981-2010` |
| Saint John | moderate | no data | low | wet | lowland with lake, ravines and escarpment | `clim-nb-saint-john-a` |
| Halifax | moderate | average | moderate | very wet | lowland with lake, ravines and escarpment | `clim-ns-halifax-stanfield-intl-a`, `clim-ns-shearwater-a-1981-2010` |
| Charlottetown | moderate | no data | moderate | wet | plains | `clim-pe-charlottetown-a` |
| St. John's | mild | no data | low | very wet | hills, lakes and Shield forest nearby | `clim-nl-st-johns-intl-a` |
| Corner Brook | moderate | no data | low | wet | mountains on the horizon | `clim-nl-corner-brook` |
| Whitehorse | cold | dull | very low | dry | mountains on the horizon | `clim-yt-whitehorse-a`, `clim-yt-whitehorse-a-1981-2010` |
| Yellowknife | severe | sunny | very low | dry | hills, lakes and Shield forest nearby | `clim-nt-yellowknife-a`, `clim-nt-yellowknife-a-1981-2010` |
| Iqaluit | severe | no data | very low | dry | hills, lakes and Shield forest nearby | `clim-nu-iqaluit-a` |

**Caveats on specific rows.**

- **Edmonton.** Winter is rated from the in-city Blatchford station. Sunshine comes from the
  international airport, 25 km south, in 1981–2010.
- **Halifax.** Sunshine comes from Shearwater in Dartmouth, 1981–2010.
- **Nelson / Castlegar.**
  - Winter and humidex come from Nelson (1991–2020). Sunshine and wetness come from Castlegar
    airport (1981–2010).
  - Castlegar's annual precipitation is 751 mm, which falls in the *moderate* band.
  - Because Nelson has no published annual figure, the row stands for the West Kootenay valley
    floor, not the surrounding mountains, which are wetter and snowier.
- **Kelowna and Penticton.** Penticton's 1991–2020 humidex count (38 days) suggests Kelowna is
  similar, but Kelowna's own record has no humidex data, so it stays **no data**.
- **Calgary.** Winter falls in the *cold* band because of about 22 nights below −20 °C. Its January
  mean of −7.6 °C would be *moderate*.

## 3. Sensitivity: how the order changes when one weight moves one step

The top two groups are shown under each scenario. The pair of numbers after each city counts the
criteria in the top bands: strong criteria first, flexible criteria second.

**Default.** Strong criteria: mountains, winter and sunshine. Flexible criteria: humidity and
wetness.

- **Top group:** Victoria (3/3 strong, 2/2 flexible).
- **Next group:** Calgary (2/3, 2/2), Cranbrook (2/3, 1/2), Kamloops (2/3, 1/2), Kelowna (2/3, 1/2),
  Nelson / Castlegar (2/3, 1/2), Penticton (2/3, 1/2), Vancouver (2/3, 1/2).

**Sunshine moved from strong to flexible.**

- **Top group:** Victoria, Kamloops, Kelowna, Nelson / Castlegar, Penticton, Vancouver. All have
  mountains and a mild winter.
- **Next group:** Calgary, Banff, Cranbrook, Whitehorse, Corner Brook, St. John's, Toronto.

**Winter moved from strong to flexible.**

- **Top group:** Victoria, Calgary, Cranbrook. All have mountains and sun.
- **Next group:** Banff, Edmonton, Kamloops, Kelowna, Nelson / Castlegar, Penticton, Vancouver,
  Whitehorse, Yellowknife, Corner Brook, Saskatoon.

**Mountains moved from strong to flexible.**

- **Top group:** Victoria.
- **Next group:** Calgary, Cranbrook, Edmonton, Kamloops, Kelowna, Nelson / Castlegar, Penticton,
  Vancouver, Yellowknife, Saskatoon, St. John's, Toronto.

**Robust conclusions.**

1. Victoria is at the top under every scenario.
2. The southern BC interior (Okanagan, Thompson, Kootenays) and Vancouver stay in the leading
   group under every scenario.
3. Calgary and Cranbrook rise to the top when sunshine outweighs winter mildness.
4. No Prairie, Ontario, Quebec or Atlantic city enters the top group under any single-step change.
   This is a statement about **climate and landform only**. Cost, jobs, schools and immigration
   could reorder everything, and they are not yet rated.

## 4. Answers to the SPEC §8 questions

### Which province has the best hiking?

There is no single province-wide answer, because hiking quality depends on the region.

| Rank | Where | Why | Evidence |
|---|---|---|---|
| 1 | **British Columbia** | The widest variety: coastal rainforest, Coast Mountains alpine, Columbia Mountains, the BC Rockies and interior grassland. Trails are close to most cities. | `landform-bc-coast-mountains`, `landform-bc-columbia-mountains`, `landform-ca-rocky-mountains`, `region-bc-british-columbia` |
| 2 | **Alberta (Rockies only)** | Banff, Jasper, Kananaskis and Waterton are a world-class concentration, but the rest of the province is plains. | `landform-ca-rocky-mountains`, `region-ab-alberta` |
| 3 | **Yukon** | Wilderness scale and the St. Elias range. The season is short. | `landform-yt-st-elias-mountains`, `clim-yt-whitehorse-a` |
| 4 | **Newfoundland and Labrador** | Gros Morne, the Long Range Mountains and coastal trails. | `landform-nl-long-range-mountains` |
| 5 | **Quebec** | The Laurentians, Charlevoix and the Gaspé, including the Chic-Chocs. | `landform-qc-laurentian-highlands`, `landform-qc-chic-chocs` |

Ontario and the Maritimes offer forest, lake and escarpment hiking rather than alpine hiking
(`landform-on-niagara-escarpment`). Trail-level data (difficulty, gain, season) is a later task;
no trail records exist yet.

### Which offers the most spectacular landscapes?

**To visit:** the Rockies parks, the Coast Mountains and the west coast of Vancouver Island, Kluane
and the St. Elias, the Torngat Mountains, Gros Morne, and Nunavut's Arctic mountains.

Evidence: `landform-ca-rocky-mountains`, `landform-yt-st-elias-mountains`,
`landform-nl-torngat-mountains`, `landform-nl-long-range-mountains`, `landform-nu-innuitian-region`.

**To live near:** Vancouver, the Bow Valley (Canmore and Banff), the Kootenays and Corner Brook put
dramatic landscape at the doorstep. That statement is interpretation.

### Where can someone live near mountains and forests without excessive housing costs?

Places in the top mountain-setting steps that are not large metros:

| Place | Mountain setting | Evidence |
|---|---|---|
| Nelson / Castlegar | in the mountains | `clim-bc-nelson-cs`, `clim-bc-castlegar-a` |
| Cranbrook | in the mountains | `clim-bc-cranbrook-a` |
| Kamloops | mountains on the horizon | `clim-bc-kamloops-a` |
| Penticton | mountains on the horizon | `clim-bc-penticton-a` |
| Prince George | forest and plateau, mountains at a distance | `clim-bc-prince-george-a` |
| Corner Brook | mountains on the horizon | `clim-nl-corner-brook` |
| Whitehorse | mountains on the horizon | `clim-yt-whitehorse-a` |
| Sherbrooke | Appalachian hills | `clim-qc-lennoxville` |

**Housing cost: no data (pending Agent 02's `re` records).** No affordability band is given, and
none of these places should be read as cheap until Agent 02 reports.

### Which cities combine urban amenities and nature?

This is interpretation. City size and amenities are not yet records; Agent 07 or Agent 01 should
supply city records.

| City | Nature within reach | Evidence |
|---|---|---|
| Vancouver | Ocean and mountains at the city edge | `clim-bc-vancouver-intl-a`, `landform-bc-coast-mountains` |
| Calgary | Rockies on the horizon, river parks | `clim-ab-calgary-intl-a`, `landform-ca-rocky-mountains` |
| Victoria | Ocean, island forest | `clim-bc-victoria-gonzales-cs` |
| Montréal | Laurentians within reach | `landform-qc-laurentian-highlands` |
| Québec city | Laurentians and Charlevoix | `landform-qc-laurentian-highlands` |
| Ottawa | Gatineau Hills, Shield lakes | `clim-on-ottawa-cda` |

Kelowna is the mid-size option (`clim-bc-kelowna-a`).

### Where is winter most manageable?

By the winter band:

- **Very mild:** Victoria and Vancouver.
- **Mild:**
  - Penticton, Kamloops, Kelowna and Nelson / Castlegar;
  - Toronto, at −3.5 °C with about 2 nights below −20 °C;
  - St. John's, at −4.2 °C with 0 nights below −20 °C, but with 363 cm of snow, 31 freezing-rain
    days and 114 fog days a year.

So the mildest winter by temperature is not always the easiest to live with. In the BC interior
valleys, winter is mild but dull: 35–55 hours of January sunshine. Records: `clim-nl-st-johns-intl-a`,
`clim-bc-penticton-a`, `clim-on-toronto-city`.

### Which places have milder winters, more sunshine or less humidity?

- **Milder winter *and* more sunshine (top two bands for both):** only **Victoria**.
  `clim-bc-victoria-gonzales-cs` gives the winter; `clim-bc-victoria-intl-a-1981-2010` gives
  2,109 sunshine hours, measured at the airport.
- **Sunniest overall:** Calgary (2,396 h), Edmonton (2,310 h), Saskatoon (2,268 h), Yellowknife
  (2,256 h) and Cranbrook (2,190 h), all in 1981–2010. All have colder winters.
- **Least summer humidity:** Victoria, Vancouver, Prince George, Calgary, Banff, Edmonton, Saint
  John, St. John's, Corner Brook and the North, all with fewer than 15 days of humidex ≥ 30.
- **Most humid summers:** Toronto, London, Ottawa and Montréal, with 50–59 days of humidex ≥ 30.

### Where can someone enjoy outdoor activities year-round?

This is interpretation from the climate records and landforms.

| Place | Year-round pattern | Evidence |
|---|---|---|
| South coast BC | Hiking and cycling all year at low elevation, skiing in the nearby mountains, summer water sports. The cost is wet winter days, about 20 days with precipitation in January at Vancouver airport. | `clim-bc-vancouver-intl-a`, `landform-bc-coast-mountains` |
| Okanagan, Thompson and Kootenay valleys | Four distinct seasons: lake summers, ski winters. Summer smoke is the limit. | `clim-bc-kelowna-a`, `clim-bc-castlegar-a`, `hazard-bc-interior-wildfire` |
| Calgary and the Bow Valley | Sunny winter skiing and summer hiking. Cold snaps and the short Banff frost-free season (64 days) shape the calendar. | `clim-ab-calgary-intl-a`, `clim-ab-banff-cs` |

### Which locations have the most varied geography within practical travel distance?

Travel times are not yet verified, so this is interpretation.

| City | Range within reach | Evidence |
|---|---|---|
| Vancouver | Ocean, delta, rainforest, alpine and glaciers | `landform-bc-coast-mountains` |
| Calgary | Prairie, foothills, the Rockies, and badlands to the east | `landform-ca-interior-plains`, `landform-ca-rocky-mountains` |
| Kamloops | Semi-desert grassland to alpine plateaus | `clim-bc-kamloops-a` |
| Québec city | St. Lawrence estuary, Laurentian Shield and Appalachians | `landform-qc-laurentian-highlands`, `landform-ca-appalachian-uplands` |
| Corner Brook | Fjord, Long Range Mountains, Gros Morne | `landform-nl-long-range-mountains` |

### Which places suit a quiet lifestyle?

Smaller centres with nature at the door:

| Place | Note | Evidence |
|---|---|---|
| Nelson / Castlegar | | `clim-bc-nelson-cs` |
| Penticton | | `clim-bc-penticton-a` |
| Cranbrook | | `clim-bc-cranbrook-a` |
| Corner Brook | | `clim-nl-corner-brook` |
| Charlottetown | | `clim-pe-charlottetown-a` |
| Fredericton | | `clim-nb-fredericton-a` |
| Whitehorse | Demanding winters | `clim-yt-whitehorse-a` |

Population, services and walkability are **no data** here. They need city records from Agents 01
and 02, so this list is a lead, not a conclusion.

## 5. What would change these answers

- **The user's essential requirements** (USER-PROFILE): legal pathway, a qualifying school and a
  housing budget. These act as gates before any of the bands above matter.
- **Whether French-language living is acceptable.** This decides whether Montréal, Québec city and
  Sherbrooke stay in scope.
- **The user's tolerance for summer wildfire smoke and for grey winters.** This is the main
  trade-off inside BC (question added to `OPEN-QUESTIONS.md`).
- **Whether "more sunshine" means sunnier winters or sunnier years.**
  - For winter sunshine, Calgary (120 h in January) and Moncton (116 h) beat every BC city.
  - For annual or summer sunshine, the Prairies and Victoria lead.
