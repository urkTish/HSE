# Provinces and territories: land, landscape, climate and lifestyle

Agent 04 · researched 2026-10-30 · Phase 1

This page describes what the land is like in each province and territory: its physiographic
regions, where the mountains, forests, lakes, plains and coasts are, how terrain shapes settlement
and transport, the outdoor opportunities, the hazards, and how the main cities differ.

**Evidence.**

- Physiographic regions and landforms are `landform` records; each province and territory is a
  `region` record. Both are under `records/`.
- Climate is `clim` records under `climate/`, compared in `climate-comparison.md`.
- Hazards are `hazard` records, summarised in `hazards.md`.
- Area and highest-point figures come from the NRCan Atlas of Canada tables republished by
  Statistics Canada. Physiographic descriptions come from the Atlas of Canada's *Physiographic
  Regions* page (Bostock 1967 map). Ecozone characteristics come from the National Ecological
  Framework table republished by Statistics Canada.

**What is not covered here.**

- Taxes, healthcare, immigration and employment belong to Agent 01 (`knowledge-base/national/`).
- Housing, rents and property rules belong to Agent 02 (`knowledge-base/real-estate/`).

This page does not repeat that material. Where it names a cost or affordability point, it marks it
as *pending Agent 02*.

**Labels.** Section headings and the facts listed under *Land* are sourced. The *Settlement and
transport*, *Outdoor opportunities* and *Lifestyle notes* paragraphs are agent-04 professional
interpretation.

## The seven physiographic regions (national frame)

| Region | What the land is like | Where | Record |
|---|---|---|---|
| Cordillera | Three parallel mountain systems: the Eastern System (Rockies, Mackenzie Mountains), the Interior System (plateaus, Columbia and other ranges) and the Western System (Coast and St. Elias mountains). It has volcanic landforms and Canada's highest peak, Mount Logan (5,959 m). | BC, south-west AB, YT, west NT | `landform-ca-cordillera` |
| Interior Plains | Prairie in the south, forest in the centre and tundra in the north. In the south the land steps down eastward from the Alberta Plain to the Saskatchewan Plain to the Manitoba Plain. | AB, SK, MB, north-east BC, NT | `landform-ca-interior-plains` |
| Canadian Shield | Ancient glaciated rock, even skylines, and countless lakes and wetlands. Its subregions are the Kazan, Davis, James and Laurentian regions. | Most of QC, ON, MB, north SK, NL (Labrador), NT, NU | `landform-ca-canadian-shield` |
| Hudson Bay Lowland | A low, swampy plain with raised beaches around Hudson Bay and James Bay. | North-east MB, far north ON, west QC | `landform-ca-hudson-bay-lowland` |
| Arctic Lowlands and Arctic Coastal Plain | Low plateaus and plains of the Arctic islands, and the Mackenzie Delta with its pingos. | NU, NT, north YT | `landform-ca-arctic-lowlands` |
| Innuitian Region | The mountains and ice caps of Ellesmere and Axel Heiberg islands; Barbeau Peak is 2,616 m. | NU | `landform-nu-innuitian-region` |
| Great Lakes–St. Lawrence Lowlands | Glacial plains split by the Niagara Escarpment, rarely above 150 m between the Ottawa and St. Lawrence rivers. Home to most Canadians. | South ON, St. Lawrence valley QC | `landform-ca-great-lakes-st-lawrence-lowlands` |
| Appalachian Uplands | Worn-down mountains, uplands and coastal plains; Mont Jacques-Cartier is 1,268 m. | NB, NS, PE, island of NL, south-east QC | `landform-ca-appalachian-uplands` |

The Atlas lists seven regions. The table shows eight rows because the Arctic Lands region is split
into its Arctic Lowlands and Innuitian parts, following the charter.

Major ranges and escarpments have their own records:

- `landform-ca-rocky-mountains`
- `landform-bc-coast-mountains`
- `landform-bc-columbia-mountains`
- `landform-yt-st-elias-mountains`
- `landform-nt-mackenzie-mountains`
- `landform-qc-laurentian-highlands`
- `landform-nl-torngat-mountains`
- `landform-qc-chic-chocs`
- `landform-nl-long-range-mountains`
- `landform-on-niagara-escarpment`

---

## British Columbia (`region-bc-british-columbia`)

**Land.** BC covers 944,735 km² and is almost entirely Cordillera.

- The Coast Mountains (`landform-bc-coast-mountains`) rise from a fjorded coast. Mount Waddington
  (4,016 m) is the highest summit wholly in BC.
- Vancouver Island and Haida Gwaii lie offshore.
- The interior has dry plateaus and deep valleys: the Fraser, Thompson and Okanagan.
- The Columbia Mountains (Purcells, Selkirks, Monashees, Cariboos; `landform-bc-columbia-mountains`)
  have interior temperate rainforest and deep snow.
- The Rockies (`landform-ca-rocky-mountains`) lie along the Alberta boundary. Mount Robson
  (3,954 m) is the highest in the Canadian Rockies table.
- The north-east (Peace River) is Interior Plains.
- The province's highest point is Fairweather Mountain (4,663 m) in the St. Elias Mountains.
- Ecozones: Pacific Maritime (mild, very wet coast) and Montane Cordillera (from moist to arid
  interior grassland).

**Settlement and transport.** Population is concentrated where the land is flat: the Fraser delta
(Vancouver), south-east Vancouver Island (Victoria) and the interior valley floors (Kelowna,
Penticton, Kamloops, Nelson, Cranbrook, Prince George). Roads and railways follow a few valleys
and passes, so a single landslide, flood or fire can cut a corridor. The November 2021 floods
closed the Coquihalla into 2022 (`hazard-bc-atmospheric-river-flood`).

**Outdoor opportunities.** BC offers the widest range of any province: coastal rainforest and
ocean kayaking, and alpine hiking from city doorsteps (North Shore). It also has
interior lake country (Okanagan, Kootenay and Arrow lakes), powder skiing in the Columbia
Mountains, and the Rockies parks (Yoho, Kootenay, Mount Robson). Pacific Rim represents the coastal
lowland forests of the Pacific coast.

**Climate.** BC has the widest internal range of any province, so it must never be summarised by
one station.

| Area | Climate | Records |
|---|---|---|
| South coast | Mildest winters in Canada (Victoria January mean 5.8 °C in the city), wet winters, dry summers | `clim-bc-victoria-gonzales-cs`, `clim-bc-vancouver-intl-a` |
| Interior valleys | Hot, dry summers and short, often cloudy winters | `clim-bc-kamloops-a`, `clim-bc-penticton-a`, `clim-bc-kelowna-a` |
| West Kootenay | Snowy mountain valleys with mild valley-floor winters | `clim-bc-castlegar-a`, `clim-bc-nelson-cs` |
| Rocky Mountain Trench | Sunny, colder winters | `clim-bc-cranbrook-a` |
| Central interior | Long, cold winters | `clim-bc-prince-george-a` |

**Hazards.**

- Interior wildfire and smoke: `hazard-bc-interior-wildfire`.
- Extreme heat, as in the 2021 heat dome: `hazard-bc-extreme-heat`.
- Atmospheric-river flooding: `hazard-bc-atmospheric-river-flood`.
- Cascadia earthquake and tsunami on the south coast: `hazard-bc-cascadia-earthquake`.
- Backcountry avalanches: `hazard-ca-mountain-avalanche`.

**Key cities and what differentiates them.**

| City | What sets it apart |
|---|---|
| Vancouver | Ocean, rainforest and mountains in one metro area; the wettest large city in the West. |
| Victoria | Mildest and, in the city, driest of the coast; island setting. |
| Kelowna and Penticton | Lakes, orchards and vineyards; hot summers; smoke risk. |
| Kamloops | Semi-desert grassland and plateau; the driest southern city in the set (273 mm). |
| Nelson and Castlegar | Small mountain towns with lakes and skiing. |
| Cranbrook | Sunny trench between the Rockies and the Purcells. |
| Prince George | Northern forest hub. |

**Lifestyle notes.** BC is the strongest match for an outdoors-oriented household that wants mild
or short winters. The trade-offs vary by place:

- coast: rain and grey winters, plus earthquake exposure;
- interior: summer smoke and heat;
- small mountain towns: limited services.

Housing cost on the coast and in the Okanagan is pending Agent 02.

## Alberta (`region-ab-alberta`)

**Land.** Alberta covers 661,848 km². Most of it is Interior Plains (`landform-ca-interior-plains`):

- prairie in the south-east;
- aspen parkland in the centre;
- boreal forest in the north;
- a sliver of Canadian Shield in the far north-east.

In the west the land rises through foothills to the Rocky Mountains (`landform-ca-rocky-mountains`).
Mount Columbia (3,747 m) is the province's highest point. Banff and Jasper national parks lie here.

**Settlement and transport.** Calgary sits on the foothills edge at about 1,100 m on the Bow and
Elbow rivers. Edmonton sits in the parkland on the North Saskatchewan. Mountain access runs
through the Bow Valley (Canmore, Banff) and the Yellowhead route (Jasper). Wide plains make road
travel straightforward outside the mountains.

**Outdoor opportunities.**

- Rocky Mountain hiking, scrambling, skiing and lakes: Banff, Jasper, Kananaskis, Waterton.
- Badlands and river valleys on the plains.
- Boreal lakes in the north.

**Climate.** Records: `clim-ab-calgary-intl-a`, `clim-ab-calgary-intl-a-1981-2010`,
`clim-ab-banff-cs`, `clim-ab-edmonton-blatchford`, `clim-ab-edmonton-intl-a`,
`clim-ab-lethbridge-a`.

- Calgary is the sunniest city in this dataset at about 2,400 hours in 1981–2010. It has cold snaps
  (about 22 nights below −20 °C) broken by milder spells.
- Lethbridge has a similar pattern, with more summer heat.
- Banff has a mountain climate, with a 64-day frost-free season.
- Edmonton is colder and has long winters.
- The airport-versus-city difference in Edmonton is material: see `climate-comparison.md`.

**Hazards.**

- Hail: `hazard-ab-calgary-hail`.
- Bow and Elbow river floods: `hazard-ab-bow-elbow-river-flood`.
- Mountain-park wildfire: `hazard-ab-mountain-parks-wildfire`.
- Drought in the south: `hazard-ca-prairie-drought`.
- Extreme cold: `hazard-ca-extreme-cold`.
- Backcountry avalanches: `hazard-ca-mountain-avalanche`.

**Key cities.**

- **Calgary:** a large city with very sunny skies and the Rockies to the west.
- **Edmonton:** a capital city with a river-valley park system and long winters.
- **Canmore and Banff:** living inside the mountains, with no ECCC record for Canmore. Banff is the
  nearest normals station.
- **Lethbridge:** a prairie city with a warm, dry, windy climate. Its mean wind speed is
  17.1 km/h, among the highest in the set (`clim-ab-lethbridge-a`).

**Lifestyle notes.** Calgary combines big-city amenities with the strongest sunshine and good
mountain access. Its winters are colder than coastal BC but sunnier than anywhere east.

## Saskatchewan (`region-sk-saskatchewan`)

**Land.** Saskatchewan covers 651,036 km².

- The south is Interior Plains: farmed grassland and parkland, cut by the South and North
  Saskatchewan and Qu'Appelle valleys.
- The north is Canadian Shield boreal forest with thousands of lakes.
- The highest point is in the Cypress Hills (1,392 m).

**Settlement and transport.** Population is concentrated in the south and centre (Regina,
Saskatoon). The north is reached by a few highways and by air.

**Outdoor opportunities.**

- Northern lake country: canoeing and fishing.
- Grasslands and big-sky prairie.
- Few mountains: the province is weak on mountain hiking.

**Climate.** Records: `clim-sk-saskatoon-intl-a`, `clim-sk-regina-intl-a`,
`clim-sk-saskatoon-src-1981-2010`.

- Severe to cold continental climate: January means of −15.4 °C at Saskatoon and −14.7 °C at
  Regina, with 45–49 nights below −20 °C.
- Warm, sunny summers: about 2,268 hours at Saskatoon SRC.
- Low precipitation, under 400 mm.

**Hazards.** Drought (`hazard-ca-prairie-drought`) and extreme cold (`hazard-ca-extreme-cold`).

**Lifestyle notes.** Sunshine is high, but the long cold winters and the distance to mountains fit
the inferred preferences poorly.

## Manitoba (`region-mb-manitoba`)

**Land.** Manitoba covers 647,797 km².

- The south-west is Interior Plains below the Manitoba Escarpment (Riding Mountain); Baldy Mountain
  (832 m) is the highest point.
- The Red River Valley and the lake-covered Manitoba Plain hold lakes Winnipeg, Manitoba and
  Winnipegosis.
- Most of the province is Canadian Shield.
- The north-east is Hudson Bay Lowland: Churchill, and Wapusk National Park with its polar bear
  denning areas (`landform-ca-hudson-bay-lowland`).

**Settlement and transport.** Winnipeg holds most of the population, on the flat Red River plain.
The north is reached by rail, air and winter roads.

**Outdoor opportunities.**

- Shield lakes (Whiteshell) and Riding Mountain.
- Lake Winnipeg beaches.
- Polar bears and beluga whales at Churchill (visit rather than live).

**Climate.** Record: `clim-mb-winnipeg-intl-a`. Winnipeg has the coldest January mean of the
southern cities in this set (−16.3 °C) and about 52 nights below −20 °C. It also has humid summers
(37 days with humidex ≥ 30).

**Hazards.** Red River flooding (`hazard-mb-red-river-flood`) and extreme cold
(`hazard-ca-extreme-cold`).

**Lifestyle notes.** Winnipeg is a large city, but its winter severity and the distance to
mountains run against the inferred preferences.

## Ontario (`region-on-ontario`)

**Land.** Ontario covers 1,076,395 km² and is three different lands:

1. The Great Lakes–St. Lawrence Lowlands in the south (`landform-ca-great-lakes-st-lawrence-lowlands`),
   split by the Niagara Escarpment (`landform-on-niagara-escarpment`, 535 m point).
2. The Canadian Shield of lakes, rock and forest: Muskoka, Algonquin, Sudbury, Lake Superior's
   north shore.
3. The roadless Hudson Bay Lowland in the far north.

The highest point is Ishpatina Ridge (693 m).

**Settlement and transport.** Population is concentrated on the lowland:

- Toronto and the Golden Horseshoe;
- Ottawa;
- London;
- Kingston.

The Shield towns (Sudbury, Thunder Bay) are hundreds of kilometres apart along the Trans-Canada
corridors.

**Outdoor opportunities.**

- Canoe country on the Shield (Algonquin, Temagami, Superior coast).
- The Bruce Peninsula and the Niagara Escarpment.
- Lakes everywhere.
- There are no high mountains. Hiking is forest, lakeshore and escarpment rather than alpine.

**Climate.** Records: `clim-on-toronto-city`, `clim-on-london-a`, `clim-on-kingston-pumping-station`,
`clim-on-ottawa-cda`, `clim-on-sudbury-a`, `clim-on-thunder-bay-a`.

| City | January mean | Other features |
|---|---|---|
| Toronto | −3.5 °C | Mildest winters east of BC; humid summers (59 days humidex ≥ 30) |
| London | −5.4 °C | Humid summers (55 days humidex ≥ 30) |
| Ottawa | −9.6 °C | Colder and snowier; freezing rain |
| Sudbury | −12.7 °C | Shield winter |
| Thunder Bay | −13.4 °C | Shield winter; 42 nights below −20 °C |

**Hazards.**

- Urban flooding: `hazard-on-southern-ontario-heavy-rain-flood`.
- Derechos: `hazard-on-qc-derecho`.
- Ice storms: `hazard-qc-on-ice-storm`.
- Smoke episodes: `hazard-ca-wildfire-smoke`.

**Key cities.**

| City | What sets it apart |
|---|---|
| Toronto | Canada's largest city; lake and ravines; mild for Ontario. |
| Ottawa | Capital; Gatineau Hills and Shield lakes close by. |
| Kingston | Lake Ontario and Thousand Islands; mid-size. |
| London | Mid-size; southwestern farmland. |
| Sudbury and Thunder Bay | Shield lake living; colder. |

## Quebec (`region-qc-quebec`)

**Land.** Quebec is the largest province at 1,542,056 km².

- The St. Lawrence Lowlands run from Montréal to Québec city.
- North of them the Laurentian Highlands (`landform-qc-laurentian-highlands`) rise abruptly; Mont
  Tremblant is 968 m and Mont Sainte-Anne 800 m. Beyond lies a vast Shield of lakes, boreal forest
  and taiga reaching Nunavik.
- To the south-east are the Appalachians: the Eastern Townships, the Gaspé and the Chic-Chocs, with
  Mont Jacques-Cartier at 1,268 m (`landform-qc-chic-chocs`).
- The highest point is Mont D'Iberville (1,652 m) in the Torngats.

**Settlement and transport.** Population lines the St. Lawrence. Highways and rail follow both
shores, and the north is reached by long roads and by air.

**Outdoor opportunities.**

- Laurentian and Charlevoix hills, lakes and skiing close to both main cities.
- The Gaspé coast and Chic-Chocs.
- Fjord du Saguenay.
- Cross-country skiing culture.

**Climate.** Records: `clim-qc-montreal-trudeau-intl-a`, `clim-qc-quebec-jean-lesage-intl-a`,
`clim-qc-lennoxville`, `clim-qc-sherbrooke-a`.

- Snowy winters: Montréal has a January mean of −9.2 °C and 217 cm of snow; Québec city is colder
  at −11.9 °C.
- Humid summers: Montréal has 50 days with humidex ≥ 30.
- Precipitation is over 1,000 mm.

**Hazards.**

- Ice storms: `hazard-qc-on-ice-storm`.
- Heavy-rain flooding: `hazard-qc-montreal-heavy-rain-flood`.
- Derechos: `hazard-on-qc-derecho`.
- Smoke: `hazard-ca-wildfire-smoke`.
- Coastal storms in the Gulf: `hazard-ca-atlantic-post-tropical-storms`.

**Lifestyle notes.** Montréal and Québec city combine strong urban culture with hills and lakes
within reach. Whether French-language living is acceptable is an open user question (Agent 01
covers the language rules).

## New Brunswick (`region-nb-new-brunswick`)

**Land.** New Brunswick covers 72,908 km².

- Appalachian uplands and forest dominate the north-west, where Mount Carleton (817 m) is the
  highest point in the Maritimes.
- The Saint John River valley runs through the province.
- The low Northumberland and Acadian coast lies to the east.
- The Bay of Fundy coast lies to the south.

**Cities and climate.** Records: `clim-nb-fredericton-a`, `clim-nb-moncton-a`,
`clim-nb-saint-john-a`.

- Fredericton (river valley): colder winters, warmer summers.
- Moncton: the snowiest of the three at 310 cm.
- Saint John (Fundy coast): cooler summers (July high 23.0 °C) and few heat days.

**Hazards.** Post-tropical storms (`hazard-ca-atlantic-post-tropical-storms`) and freezing rain
(`hazard-qc-on-ice-storm`).

**Lifestyle notes.** Mid-size and small cities with forest, river and coast close by. Housing cost
is pending Agent 02.

## Nova Scotia (`region-ns-nova-scotia`)

**Land.** Nova Scotia covers 55,284 km². It is an Appalachian peninsula plus Cape Breton Island,
whose highlands reach 532 m at White Hill. Its landscapes are:

- the rocky Atlantic shore;
- the Fundy shore and Annapolis Valley;
- lakes and forest inland.

No point is far from the sea.

**Cities and climate.** Halifax is the regional centre on a deep harbour; the airport is 27 km
inland. Records: `clim-ns-halifax-stanfield-intl-a`, `clim-ns-shearwater-a-1981-2010`.

- Winters are cold but mild for eastern Canada, with 3 nights below −20 °C.
- The climate is very wet: 1,393 mm a year.
- There is frequent fog: 104 days at Stanfield.

**Hazards.** Post-tropical storms (`hazard-ca-atlantic-post-tropical-storms`) and extreme-rain
flooding (`hazard-ns-halifax-flash-flood`).

**Outdoor opportunities.** Coastal hiking (Cape Breton Highlands, Cabot Trail), sea kayaking and
lakes. Mountains are modest.

## Prince Edward Island (`region-pe-prince-edward-island`)

**Land.** PEI is a low, gently rolling island of 5,660 km²; its highest point is 142 m. It has
farmland, red cliffs and beaches. Coastal erosion and storm surge are the main physical issues;
the provincial erosion data could not be retrieved (see `STATUS.md`).

**Climate.** Record: `clim-pe-charlottetown-a`.

- Winter January mean of −7.3 °C, with 285 cm of snow.
- 14.8 days of freezing rain a year.
- Pleasant summers, with a July high of 23.6 °C.

**Lifestyle notes.** Small-city, quiet island living with beaches and cycling. There are no
mountains or large forests.

## Newfoundland and Labrador (`region-nl-newfoundland-and-labrador`)

**Land.** The province covers 405,212 km².

- The island of Newfoundland is Appalachian. On the west coast the Long Range Mountains
  (`landform-nl-long-range-mountains`) reach 814 m in the Lewis Hills, with fjords and Gros Morne.
- Inland are barrens and forest.
- The Avalon Peninsula is rugged.
- Labrador is Canadian Shield, with the Torngat Mountains (`landform-nl-torngat-mountains`,
  1,652 m) and the only glaciers in eastern continental North America.

**Cities and climate.** Records: `clim-nl-st-johns-intl-a`, `clim-nl-corner-brook`,
`clim-nl-gander-intl-a-1981-2010`.

St. John's:

- the mildest January of the Atlantic cities at −4.2 °C, with no nights below −20 °C;
- the wettest and among the snowiest cities in the set: 1,539 mm of precipitation and 363 cm of
  snow;
- 114 fog days and 31 freezing-rain days a year;
- cool summers.

Corner Brook has the most snow of any 1991–2020 record in the set (408 cm), in a fjord setting;
Gander's 1981–2010 record is higher still at 452 cm. Gander is dull, with 1,624 hours of sunshine in 1981–2010.
St. John's is the windiest station in the set, with a mean of 22 km/h.

**Hazards.** Post-tropical storms (`hazard-ca-atlantic-post-tropical-storms`) and western Labrador
wildfire (`hazard-nl-western-labrador-wildfire`).

**Lifestyle notes.** Spectacular coastal and fjord landscapes, especially Gros Morne and the east
coast trails. Weather is harsh in its variability rather than in its cold.

## Yukon (`region-yt-yukon`)

**Land.** Yukon covers 482,443 km² and is almost all Cordillera.

- In the south-west are the St. Elias Mountains and Kluane (`landform-yt-st-elias-mountains`).
  Mount Logan (5,959 m) is Canada's highest peak, and the Icefield Ranges hold the world's largest
  non-polar icefields.
- The centre has plateaus and the Yukon River valley.
- Mountains lie to the east and north.
- The Arctic coastal plain is in the far north.

**City and climate.** Records: `clim-yt-whitehorse-a`, `clim-yt-whitehorse-a-1981-2010`. Whitehorse
has:

- a dry climate, with 280 mm of precipitation a year;
- a January mean of −15 °C and 45 nights below −20 °C;
- a short summer with very long days: 19.1 hours of daylight in mid-June and 5.7 in mid-December
  (computed);
- a frost-free season of only 85 days.

**Hazards.** Permafrost (`hazard-ca-permafrost-thaw`) and extreme cold (`hazard-ca-extreme-cold`).

**Lifestyle notes.** Wilderness on a vast scale with a small capital. It is a great place to
explore, with demanding winters.

## Northwest Territories (`region-nt-northwest-territories`)

**Land.** The territory covers 1,346,106 km².

- The Mackenzie valley (Interior Plains) lies between the Mackenzie Mountains to the west
  (`landform-nt-mackenzie-mountains`; highest point 2,773 m) and the Canadian Shield to the east.
- The Shield side holds Yellowknife and Great Slave and Great Bear lakes.
- The Mackenzie Delta and Inuvik are in the north.

**Climate.** Records: `clim-nt-yellowknife-a`, `clim-nt-inuvik-a`.

| Place | January mean | Nights below −20 °C | Other |
|---|---|---|---|
| Yellowknife | −25.5 °C | 103 | Very bright summers: 358 h of July sunshine (1981–2010) |
| Inuvik | −24.9 °C | 124 | Polar night in December and 24-hour daylight in June (computed) |

**Hazards.** Boreal wildfire, including the evacuation of Yellowknife in 2023
(`hazard-nt-boreal-wildfire`); permafrost (`hazard-ca-permafrost-thaw`); and cold
(`hazard-ca-extreme-cold`).

## Nunavut (`region-nu-nunavut`)

**Land.** Nunavut is the largest jurisdiction at 2,093,190 km².

- The mainland and Baffin Island are treeless Canadian Shield. Eastern Baffin Island has high,
  glaciated mountains.
- The central islands are Arctic Lowlands.
- In the north are the Innuitian mountains and ice caps of Ellesmere and Axel Heiberg islands
  (`landform-nu-innuitian-region`). Barbeau Peak (2,616 m) is the highest point.

**Climate.** Record: `clim-nu-iqaluit-a`. Iqaluit has:

- a January mean of −26.0 °C and a July mean of 8.1 °C;
- 122 nights below −20 °C;
- 4.4 hours of daylight in mid-December (computed).

**Lifestyle notes.** Nunavut is extraordinary to visit. Living there is a specialised choice, with
fly-in logistics. That statement is agent-04 interpretation.

---

## Visit, live, invest, raise a family: these differ (interpretation)

| | Strongest candidates from a land-and-climate view |
|---|---|
| Visit for landscapes | Rockies parks (AB/BC), Coast Mountains and Vancouver Island, Kluane (YT), Gros Morne and the Torngats (NL), Gaspé and Charlevoix (QC), Nunavut |
| Live with nature and a mild climate | South coast BC, Okanagan and Thompson valleys, West Kootenay |
| Live with nature and sunshine (accepting cold) | Calgary and the Bow Valley, Cranbrook |
| Invest | Pending Agent 02 |
| Raise a family | Pending Agents 01, 02 and 03 (schools, services and cost) |

Climate and land are necessary inputs but not sufficient: the final recommendation belongs to
Agent 07.
