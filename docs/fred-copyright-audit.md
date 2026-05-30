# FRED copyright audit

Source: FRED API + heuristic backup.

Total FRED YAMLs audited: **420**.

Bucket meanings come from FRED's Terms of Use § III:
  - `PRE-APPROVAL`: third-party copyrighted; needs licensor permission for anything beyond personal use.
  - `CITATION-REQUIRED`: third-party copyrighted but usable with proper attribution.
  - `PUBLIC-DOMAIN`: usable with citation, no permission needed.
  - `UNKNOWN`: status not resolved; verify manually.


## PRE-APPROVAL (0)

**Action**: REMOVE. (Or: ask Keller before keeping.)

_(none)_

## CITATION-REQUIRED (6)

**Action**: KEEP. Verify citation reads 'Source: <owner> via FRED'.

| YAML | Series | Declared provider | Declared license | Owner (resolved) | Source |
| --- | --- | --- | --- | --- | --- |
| `src/content/sources/fred/dc_median_listing.yaml` | `MEDLISPRI47900` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/median_listing_price.yaml` | `MEDLISPRIUS` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/mortgage_15y.yaml` | `MORTGAGE15US` | FRED (St. Louis Fed) / Freddie Mac | Public domain (US government data) | — | api |
| `src/content/sources/fred/mortgage_30y.yaml` | `MORTGAGE30US` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/nber_recession.yaml` | `USREC` | FRED (St. Louis Fed) / NBER | Public domain (US government data) | — | api |
| `src/content/sources/fred/stlfsi.yaml` | `STLFSI4` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |

## PUBLIC-DOMAIN (414)

**Action**: KEEP. Verify citation acknowledges the original source.

| YAML | Series | Declared provider | Declared license | Owner (resolved) | Source |
| --- | --- | --- | --- | --- | --- |
| `src/content/sources/fred/ag_employment.yaml` | `LNS12034560` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/ag_exports.yaml` | `B181RC1Q027SBEA` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/avg_hourly_earnings.yaml` | `AHETPI` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/avg_hourly_earnings_all.yaml` | `CES0500000003` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/building_permits.yaml` | `PERMIT` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/capacity_util.yaml` | `TCU` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/cny_usd.yaml` | `DEXCHUS` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/computer_electronics_orders.yaml` | `A34SNO` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/consumer_credit.yaml` | `TOTALSL` | Board of Governors of the Federal Reserve System via FRED | Public domain (US government data; FRB G.19 Consumer Credit release) | — | api |
| `src/content/sources/fred/continuing_claims.yaml` | `CCSA` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/core_cpi.yaml` | `CPILFESL` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/core_pce.yaml` | `PCEPILFE` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/cpi_energy.yaml` | `CPIENGSL` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/cpi_food.yaml` | `CPIUFDSL` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/cpi_food_at_home.yaml` | `CUSR0000SAF11` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/cpi_food_away.yaml` | `CUSR0000SEFV` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/cpi_medical.yaml` | `CPIMEDSL` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/cpi_rent.yaml` | `CUUR0000SEHA` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/cpi_shelter.yaml` | `CUUR0000SAH1` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/cpi_yoy.yaml` | `CPIAUCSL (transformation=pc1)` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/dc_cpi.yaml` | `CUUSA311SA0` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/dc_payrolls.yaml` | `WASH911NA` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/dc_unemployment_rate.yaml` | `WASH911URN` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/defense_pct_gdp.yaml` | `A824RE1Q156NBEA` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/electric_power_production.yaml` | `IPG2211S` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/fed_balance_sheet.yaml` | `WALCL` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/fed_funds.yaml` | `FEDFUNDS` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/federal_debt_pct_gdp.yaml` | `GFDEGDQ188S` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/federal_debt_total.yaml` | `GFDEBTN` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/federal_defense.yaml` | `FDEFX` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/federal_defense_spending.yaml` | `FDEFX` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/federal_deficit_pct_gdp.yaml` | `FYFSGDA188S` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/federal_employment.yaml` | `CES9091000001` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/federal_expenditures.yaml` | `FGEXPND` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/federal_interest.yaml` | `A091RC1Q027SBEA` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/federal_interest_pct_gdp.yaml` | `FYOIGDA188S` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/federal_medicaid.yaml` | `W729RC1Q027SBEA` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/federal_medicare.yaml` | `W824RC1Q027SBEA` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/federal_nondefense_spending.yaml` | `FNDEFX` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/federal_outlays_pct_gdp.yaml` | `FYONGDA188S` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/federal_receipts_pct_gdp.yaml` | `FYFRGDA188S` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/federal_social_security.yaml` | `W823RC1Q027SBEA` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/federal_subsidies.yaml` | `B096RC1Q027SBEA` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/fhfa_dc_hpi.yaml` | `ATNHPIUS47894Q` | U.S. Federal Housing Finance Agency (FHFA) via FRED | Public domain (US government data; FHFA publishes the underlying index) | — | api |
| `src/content/sources/fred/fhfa_us_hpi.yaml` | `USSTHPI` | U.S. Federal Housing Finance Agency (FHFA) via FRED | Public domain (US government data; FHFA publishes the underlying index) | — | api |
| `src/content/sources/fred/gdp_deflator.yaml` | `GDPDEF` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/headline_pce.yaml` | `PCEPI` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/health_care_employment.yaml` | `CES6562000001` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/homeowner_vacancy.yaml` | `RHVRUSQ156N` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/housing_starts.yaml` | `HOUST` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/industrial_production_mining.yaml` | `IPMINE` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/information_employment.yaml` | `USINFO` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/initial_claims.yaml` | `ICSA` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/jolts_openings.yaml` | `JTSJOL` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/jolts_quits_rate.yaml` | `JTSQUR` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; BLS Job Openings and Labor Turnover Survey) | — | api |
| `src/content/sources/fred/labor_participation.yaml` | `CIVPART` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/local_employment.yaml` | `CES9093000001` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/m2.yaml` | `M2SL` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/manufacturing_employment.yaml` | `MANEMP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/manufacturing_weekly_hours.yaml` | `AWHMAN` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/median_home_price.yaml` | `MSPUS` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/months_supply.yaml` | `MSACSR` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/nat_gas_henry_hub.yaml` | `DHHNGSP` | FRED (St. Louis Fed) / EIA | Public domain (US government data, EIA) | — | api |
| `src/content/sources/fred/net_farm_income.yaml` | `B1448C1A027NBEA` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/new_home_sales.yaml` | `HSN1F` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/oil_gas_production.yaml` | `IPG211S` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/payrolls.yaml` | `PAYEMS` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/personal_income.yaml` | `PI` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/ppi_data_processing_hosting.yaml` | `PCU518210518210` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/ppi_farm_products.yaml` | `WPU01` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/ppi_fertilizer.yaml` | `WPS0652` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/ppi_semiconductor.yaml` | `PCU33443344` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/prime_age_participation.yaml` | `LNS11300060` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/productivity_mfg.yaml` | `OPHMFG` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/productivity_nfb.yaml` | `OPHNFB` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/quits_rate.yaml` | `JTSQUR` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/real_disposable_income.yaml` | `DSPIC96` | U.S. Bureau of Economic Analysis (BEA) via FRED | Public domain (US government data; BEA publishes the underlying NIPA series) | — | api |
| `src/content/sources/fred/real_dpi_per_capita.yaml` | `A229RX0` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/recession_probability_ny_fed.yaml` | `RECPROUSM156N` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/rental_vacancy.yaml` | `RRVRUSQ156N` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/retail_sales.yaml` | `RSAFS` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/sahm_rule.yaml` | `SAHMREALTIME` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/saving_rate.yaml` | `PSAVERT` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/semiconductor_capacity_util.yaml` | `CAPUTLG3344S` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/semiconductor_production.yaml` | `IPG3344S` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/sloos_cc_tightening.yaml` | `DRTSCLCC` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/sloos_ci_loans_tightening.yaml` | `DRTSCILM` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_employment.yaml` | `CES9092000001` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ak.yaml` | `SMS02000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_al.yaml` | `SMS01000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ar.yaml` | `SMS05000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_az.yaml` | `SMS04000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ca.yaml` | `SMS06000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_co.yaml` | `SMS08000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ct.yaml` | `SMS09000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_dc.yaml` | `SMS11000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_de.yaml` | `SMS10000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_fl.yaml` | `SMS12000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ga.yaml` | `SMS13000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_hi.yaml` | `SMS15000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ia.yaml` | `SMS19000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_id.yaml` | `SMS16000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_il.yaml` | `SMS17000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_in.yaml` | `SMS18000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ks.yaml` | `SMS20000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ky.yaml` | `SMS21000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_la.yaml` | `SMS22000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ma.yaml` | `SMS25000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_md.yaml` | `SMS24000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_me.yaml` | `SMS23000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_mi.yaml` | `SMS26000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_mn.yaml` | `SMS27000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_mo.yaml` | `SMS29000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ms.yaml` | `SMS28000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_mt.yaml` | `SMS30000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_nc.yaml` | `SMS37000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_nd.yaml` | `SMS38000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ne.yaml` | `SMS31000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_nh.yaml` | `SMS33000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_nj.yaml` | `SMS34000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_nm.yaml` | `SMS35000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_nv.yaml` | `SMS32000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ny.yaml` | `SMS36000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_oh.yaml` | `SMS39000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ok.yaml` | `SMS40000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_or.yaml` | `SMS41000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_pa.yaml` | `SMS42000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ri.yaml` | `SMS44000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_sc.yaml` | `SMS45000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_sd.yaml` | `SMS46000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_tn.yaml` | `SMS47000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_tx.yaml` | `SMS48000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_ut.yaml` | `SMS49000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_va.yaml` | `SMS51000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_vt.yaml` | `SMS50000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_wa.yaml` | `SMS53000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_wi.yaml` | `SMS55000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_wv.yaml` | `SMS54000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_fedgovemp_wy.yaml` | `SMS56000009091000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_local_expenditures.yaml` | `SLEXPND` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ak.yaml` | `SMS02000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_al.yaml` | `SMS01000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ar.yaml` | `SMS05000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_az.yaml` | `SMS04000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ca.yaml` | `SMS06000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_co.yaml` | `SMS08000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ct.yaml` | `SMS09000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_de.yaml` | `SMS10000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_fl.yaml` | `SMS12000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ga.yaml` | `SMS13000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_hi.yaml` | `SMS15000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ia.yaml` | `SMS19000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_id.yaml` | `SMS16000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_il.yaml` | `SMS17000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_in.yaml` | `SMS18000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ks.yaml` | `SMS20000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ky.yaml` | `SMS21000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_la.yaml` | `SMS22000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ma.yaml` | `SMS25000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_md.yaml` | `SMS24000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_me.yaml` | `SMS23000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_mi.yaml` | `SMS26000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_mn.yaml` | `SMS27000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_mo.yaml` | `SMS29000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ms.yaml` | `SMS28000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_mt.yaml` | `SMS30000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_nc.yaml` | `SMS37000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_nd.yaml` | `SMS38000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ne.yaml` | `SMS31000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_nh.yaml` | `SMS33000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_nj.yaml` | `SMS34000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_nm.yaml` | `SMS35000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_nv.yaml` | `SMS32000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ny.yaml` | `SMS36000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_oh.yaml` | `SMS39000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ok.yaml` | `SMS40000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_or.yaml` | `SMS41000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_pa.yaml` | `SMS42000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ri.yaml` | `SMS44000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_sc.yaml` | `SMS45000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_sd.yaml` | `SMS46000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_tn.yaml` | `SMS47000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_tx.yaml` | `SMS48000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_ut.yaml` | `SMS49000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_va.yaml` | `SMS51000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_vt.yaml` | `SMS50000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_wa.yaml` | `SMS53000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_wi.yaml` | `SMS55000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_wv.yaml` | `SMS54000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_locgovemp_wy.yaml` | `SMS56000009093000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_population_ak.yaml` | `AKPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_al.yaml` | `ALPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_ar.yaml` | `ARPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_az.yaml` | `AZPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_ca.yaml` | `CAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_co.yaml` | `COPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_ct.yaml` | `CTPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_dc.yaml` | `DCPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_de.yaml` | `DEPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_fl.yaml` | `FLPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_ga.yaml` | `GAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_hi.yaml` | `HIPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_ia.yaml` | `IAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_id.yaml` | `IDPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_il.yaml` | `ILPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_in.yaml` | `INPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_ks.yaml` | `KSPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_ky.yaml` | `KYPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_la.yaml` | `LAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_ma.yaml` | `MAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_md.yaml` | `MDPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_me.yaml` | `MEPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_mi.yaml` | `MIPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_mn.yaml` | `MNPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_mo.yaml` | `MOPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_ms.yaml` | `MSPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_mt.yaml` | `MTPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_nc.yaml` | `NCPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_nd.yaml` | `NDPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_ne.yaml` | `NEPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_nh.yaml` | `NHPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_nj.yaml` | `NJPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_nm.yaml` | `NMPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_nv.yaml` | `NVPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_ny.yaml` | `NYPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_oh.yaml` | `OHPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_ok.yaml` | `OKPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_or.yaml` | `ORPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_pa.yaml` | `PAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_ri.yaml` | `RIPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_sc.yaml` | `SCPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_sd.yaml` | `SDPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_tn.yaml` | `TNPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_tx.yaml` | `TXPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_ut.yaml` | `UTPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_va.yaml` | `VAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_vt.yaml` | `VTPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_wa.yaml` | `WAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_wi.yaml` | `WIPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_wv.yaml` | `WVPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_population_wy.yaml` | `WYPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/state_stgovemp_ak.yaml` | `SMS02000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_al.yaml` | `SMS01000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_ar.yaml` | `SMS05000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_az.yaml` | `SMS04000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_ca.yaml` | `SMS06000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_co.yaml` | `SMS08000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_ct.yaml` | `SMS09000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_de.yaml` | `SMS10000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_fl.yaml` | `SMS12000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_ga.yaml` | `SMS13000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_hi.yaml` | `SMS15000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_ia.yaml` | `SMS19000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_id.yaml` | `SMS16000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_il.yaml` | `SMS17000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_in.yaml` | `SMS18000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_ks.yaml` | `SMS20000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_ky.yaml` | `SMS21000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_la.yaml` | `SMS22000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_ma.yaml` | `SMS25000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_md.yaml` | `SMS24000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_me.yaml` | `SMS23000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_mi.yaml` | `SMS26000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_mn.yaml` | `SMS27000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_mo.yaml` | `SMS29000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_ms.yaml` | `SMS28000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_mt.yaml` | `SMS30000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_nc.yaml` | `SMS37000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_nd.yaml` | `SMS38000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_ne.yaml` | `SMS31000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_nh.yaml` | `SMS33000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_nj.yaml` | `SMS34000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_nm.yaml` | `SMS35000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_nv.yaml` | `SMS32000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_ny.yaml` | `SMS36000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_oh.yaml` | `SMS39000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_ok.yaml` | `SMS40000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_or.yaml` | `SMS41000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_pa.yaml` | `SMS42000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_ri.yaml` | `SMS44000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_sc.yaml` | `SMS45000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_sd.yaml` | `SMS46000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_tn.yaml` | `SMS47000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_tx.yaml` | `SMS48000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_ut.yaml` | `SMS49000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_va.yaml` | `SMS51000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_vt.yaml` | `SMS50000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_wa.yaml` | `SMS53000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_wi.yaml` | `SMS55000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_wv.yaml` | `SMS54000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_stgovemp_wy.yaml` | `SMS56000009092000001` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ak.yaml` | `QTAXTOTALQTAXCAT3AKNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_al.yaml` | `QTAXTOTALQTAXCAT3ALNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ar.yaml` | `QTAXTOTALQTAXCAT3ARNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_az.yaml` | `QTAXTOTALQTAXCAT3AZNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ca.yaml` | `QTAXTOTALQTAXCAT3CANO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_co.yaml` | `QTAXTOTALQTAXCAT3CONO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ct.yaml` | `QTAXTOTALQTAXCAT3CTNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_dc.yaml` | `QTAXTOTALQTAXCAT3DCNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_de.yaml` | `QTAXTOTALQTAXCAT3DENO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_fl.yaml` | `QTAXTOTALQTAXCAT3FLNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ga.yaml` | `QTAXTOTALQTAXCAT3GANO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_hi.yaml` | `QTAXTOTALQTAXCAT3HINO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ia.yaml` | `QTAXTOTALQTAXCAT3IANO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_id.yaml` | `QTAXTOTALQTAXCAT3IDNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_il.yaml` | `QTAXTOTALQTAXCAT3ILNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_in.yaml` | `QTAXTOTALQTAXCAT3INNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ks.yaml` | `QTAXTOTALQTAXCAT3KSNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ky.yaml` | `QTAXTOTALQTAXCAT3KYNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_la.yaml` | `QTAXTOTALQTAXCAT3LANO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ma.yaml` | `QTAXTOTALQTAXCAT3MANO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_md.yaml` | `QTAXTOTALQTAXCAT3MDNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_me.yaml` | `QTAXTOTALQTAXCAT3MENO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_mi.yaml` | `QTAXTOTALQTAXCAT3MINO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_mn.yaml` | `QTAXTOTALQTAXCAT3MNNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_mo.yaml` | `QTAXTOTALQTAXCAT3MONO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ms.yaml` | `QTAXTOTALQTAXCAT3MSNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_mt.yaml` | `QTAXTOTALQTAXCAT3MTNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_nc.yaml` | `QTAXTOTALQTAXCAT3NCNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_nd.yaml` | `QTAXTOTALQTAXCAT3NDNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ne.yaml` | `QTAXTOTALQTAXCAT3NENO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_nh.yaml` | `QTAXTOTALQTAXCAT3NHNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_nj.yaml` | `QTAXTOTALQTAXCAT3NJNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_nm.yaml` | `QTAXTOTALQTAXCAT3NMNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_nv.yaml` | `QTAXTOTALQTAXCAT3NVNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ny.yaml` | `QTAXTOTALQTAXCAT3NYNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_oh.yaml` | `QTAXTOTALQTAXCAT3OHNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ok.yaml` | `QTAXTOTALQTAXCAT3OKNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_or.yaml` | `QTAXTOTALQTAXCAT3ORNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_pa.yaml` | `QTAXTOTALQTAXCAT3PANO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ri.yaml` | `QTAXTOTALQTAXCAT3RINO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_sc.yaml` | `QTAXTOTALQTAXCAT3SCNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_sd.yaml` | `QTAXTOTALQTAXCAT3SDNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_tn.yaml` | `QTAXTOTALQTAXCAT3TNNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_tx.yaml` | `QTAXTOTALQTAXCAT3TXNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_ut.yaml` | `QTAXTOTALQTAXCAT3UTNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_va.yaml` | `QTAXTOTALQTAXCAT3VANO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_vt.yaml` | `QTAXTOTALQTAXCAT3VTNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_wa.yaml` | `QTAXTOTALQTAXCAT3WANO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_wi.yaml` | `QTAXTOTALQTAXCAT3WINO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_wv.yaml` | `QTAXTOTALQTAXCAT3WVNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_taxrev_wy.yaml` | `QTAXTOTALQTAXCAT3WYNO` | U.S. Census Bureau via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ak.yaml` | `AKGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_al.yaml` | `ALGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ar.yaml` | `ARGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_az.yaml` | `AZGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ca.yaml` | `CAGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_co.yaml` | `COGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ct.yaml` | `CTGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_dc.yaml` | `DCGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_de.yaml` | `DEGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_fl.yaml` | `FLGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ga.yaml` | `GAGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_hi.yaml` | `HIGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ia.yaml` | `IAGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_id.yaml` | `IDGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_il.yaml` | `ILGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_in.yaml` | `INGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ks.yaml` | `KSGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ky.yaml` | `KYGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_la.yaml` | `LAGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ma.yaml` | `MAGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_md.yaml` | `MDGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_me.yaml` | `MEGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_mi.yaml` | `MIGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_mn.yaml` | `MNGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_mo.yaml` | `MOGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ms.yaml` | `MSGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_mt.yaml` | `MTGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_nc.yaml` | `NCGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_nd.yaml` | `NDGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ne.yaml` | `NEGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_nh.yaml` | `NHGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_nj.yaml` | `NJGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_nm.yaml` | `NMGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_nv.yaml` | `NVGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ny.yaml` | `NYGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_oh.yaml` | `OHGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ok.yaml` | `OKGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_or.yaml` | `ORGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_pa.yaml` | `PAGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ri.yaml` | `RIGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_sc.yaml` | `SCGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_sd.yaml` | `SDGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_tn.yaml` | `TNGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_tx.yaml` | `TXGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_ut.yaml` | `UTGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_va.yaml` | `VAGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_vt.yaml` | `VTGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_wa.yaml` | `WAGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_wi.yaml` | `WIGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_wv.yaml` | `WVGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/state_totgovemp_wy.yaml` | `WYGOVT` | U.S. Bureau of Labor Statistics (BLS) via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/tips_10y.yaml` | `DFII10` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/tips_5y.yaml` | `DFII5` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/total_govt_employment.yaml` | `USGOVT` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/trade_balance.yaml` | `BOPGSTB` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/u6_unemployment.yaml` | `U6RATE` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/unemployment_black.yaml` | `LNS14000006` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/unemployment_hispanic.yaml` | `LNS14000009` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/unemployment_white.yaml` | `LNS14000003` | U.S. federal-agency data via FRED | Public domain (US government data; see FRED tag 'public domain: citation requested') | — | api |
| `src/content/sources/fred/unit_labor_costs.yaml` | `ULCNFB` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/us_10y.yaml` | `DGS10` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/us_2y.yaml` | `DGS2` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/us_30y.yaml` | `DGS30` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/us_3mo.yaml` | `DGS3MO` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/us_5y.yaml` | `DGS5` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/us_cpi.yaml` | `CPIAUCSL` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/us_industrial_production.yaml` | `INDPRO` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/us_population.yaml` | `POPTHM` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/us_real_gdp.yaml` | `GDPC1` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/us_retail_diesel.yaml` | `GASDESW` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/us_retail_gasoline.yaml` | `GASREGW` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |
| `src/content/sources/fred/us_unemployment.yaml` | `UNRATE` | FRED (St. Louis Fed) | Public domain (US government data) | — | api |

## UNKNOWN (0)

**Action**: VERIFY manually on the FRED series page; update YAML or this audit's heuristic table.

_(none)_
