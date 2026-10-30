# Agent 04 — Provinces, Territories, Physical Geography, Climate & Lifestyle

Charter: `canada/SPEC.md` §8. Common rules: `agents/00-common-rules.md`.
Lane: `canada/knowledge-base/geography-climate/`.

## Phase 1 deliverables

1. **`provinces-territories.md`** — one section per province and territory:
   physiographic regions and landforms, characteristic landscapes, where
   mountains, forests, lakes, plains and coasts are concentrated, how terrain
   shapes settlement and transport, distinctive outdoor opportunities,
   hazards, key cities and what differentiates them, lifestyle notes. Cite
   Agents 01 and 02 for tax, healthcare and housing rather than repeating
   them. Create `region` and `landform` records under `records/` for the
   physiographic regions (Cordillera, Interior Plains, Canadian Shield,
   Hudson Bay Lowlands, Arctic Lowlands and Innuitian region, Appalachian
   region, Great Lakes–St. Lawrence Lowlands) and the major ranges.
2. **`climate/clim-<prov>-<station>.json`** — climate normals for at least
   twenty representative cities spanning every province and territory
   (candidates: Victoria, Vancouver, Kelowna, Kamloops, Castlegar or Nelson,
   Prince George, Calgary, Edmonton, Canmore or Banff, Lethbridge,
   Saskatoon, Regina, Winnipeg, Thunder Bay, Toronto, Ottawa, Kingston,
   London, Montréal, Québec, Sherbrooke, Fredericton, Moncton, Halifax,
   Charlottetown, St. John's, Corner Brook, Whitehorse, Yellowknife,
   Iqaluit). Source: Environment and Climate Change Canada Canadian Climate
   Normals. Use the 1991–2020 normals where ECCC has published them for the
   station, otherwise 1981–2010, and set `normals_period` accordingly.
   Record the station name, climate ID, elevation and distance from the
   city centre. Fill `months` (twelve rows) and `annual` from the page;
   fields the station does not report are `null`. If the ECCC pages cannot
   be fetched, try ECCC's open-data normals downloads; if neither works,
   create no record for that city and park it. Never fill a value from
   memory.
3. **`climate-comparison.md`** — one table across all cities: January and
   July mean temperature, annual precipitation, annual snowfall, sunshine
   hours where available, with the period flag per row; then a plain
   description of what each climate type feels like through the year.
4. **`hazards.md`** plus `hazard-<prov>-<slug>.json` records: wildfire and
   smoke, river and coastal flooding, coastal storms, drought, extreme heat,
   extreme cold, avalanche, ice storm, permafrost thaw, with the regions
   actually exposed and the official source (for example Natural Resources
   Canada, provincial emergency management, Public Safety Canada).
5. **`comparative-answers.md`** — first answers to the SPEC §8 questions
   (best hiking, most spectacular landscapes, mountains and forests without
   excessive housing cost, urban amenities plus nature, most manageable
   winter, milder and sunnier places, year-round outdoors, varied geography
   within reach, quiet lifestyle). Label as `professional_interpretation`,
   cite record IDs, and show the ordinal bands of SPEC §4 with their
   thresholds written down.
6. **`STATUS.md`** and your open questions in `OPEN-QUESTIONS.md`.

## Standards specific to this lane

- Never represent a large province by one station.
- Say when an airport station differs materially from the city.
- Normals are not forecasts; write nothing that reads like a forecast.
