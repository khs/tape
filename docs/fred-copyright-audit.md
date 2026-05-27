# FRED copyright audit

Source: HEURISTIC ONLY (no API key).

Total FRED YAMLs audited: **145**.

Bucket meanings come from FRED's Terms of Use § III:
  - `PRE-APPROVAL`: third-party copyrighted; needs licensor permission for anything beyond personal use.
  - `CITATION-REQUIRED`: third-party copyrighted but usable with proper attribution.
  - `PUBLIC-DOMAIN`: usable with citation, no permission needed.
  - `UNKNOWN`: status not resolved; verify manually.


## PRE-APPROVAL (6)

**Action**: REMOVE or obtain licensor permission BEFORE relaunch.

| YAML | Series | Declared provider | Declared license | Owner (resolved) | Source |
| --- | --- | --- | --- | --- | --- |
| `src/content/sources/fred/case_shiller.yaml` | `CSUSHPISA` | FRED (St. Louis Fed) | Public domain (US government data) | S&P / CoreLogic / Case-Shiller | heuristic |
| `src/content/sources/fred/hy_spread.yaml` | `BAMLH0A0HYM2` | FRED (St. Louis Fed) | Public domain (US government data) | ICE BofA / ICE Data Indices | heuristic |
| `src/content/sources/fred/ig_spread.yaml` | `BAMLC0A0CM` | FRED (St. Louis Fed) | Public domain (US government data) | ICE BofA / ICE Data Indices | heuristic |
| `src/content/sources/fred/sp500.yaml` | `SP500` | FRED (St. Louis Fed) | Public domain (US government data) | S&P Dow Jones Indices LLC | heuristic |
| `src/content/sources/fred/us_umich_sentiment.yaml` | `UMCSENT` | FRED (St. Louis Fed) | Public domain (US government data) | University of Michigan | heuristic |
| `src/content/sources/fred/vix.yaml` | `VIXCLS` | FRED (St. Louis Fed) | Public domain (US government data) | Cboe Global Markets / CBOE | heuristic |

## CITATION-REQUIRED (2)

**Action**: KEEP. Verify citation reads 'Source: <owner> via FRED'.

| YAML | Series | Declared provider | Declared license | Owner (resolved) | Source |
| --- | --- | --- | --- | --- | --- |
| `src/content/sources/fred/mortgage_15y.yaml` | `MORTGAGE15US` | FRED (St. Louis Fed) / Freddie Mac | Public domain (US government data) | Freddie Mac (PMMS) | heuristic |
| `src/content/sources/fred/mortgage_30y.yaml` | `MORTGAGE30US` | FRED (St. Louis Fed) | Public domain (US government data) | Freddie Mac (PMMS) | heuristic |

## PUBLIC-DOMAIN (28)

**Action**: KEEP. Verify citation acknowledges the original source.

| YAML | Series | Declared provider | Declared license | Owner (resolved) | Source |
| --- | --- | --- | --- | --- | --- |
| `src/content/sources/fred/avg_hourly_earnings_all.yaml` | `CES0500000003` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Labor Statistics | heuristic |
| `src/content/sources/fred/continuing_claims.yaml` | `CCSA` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Employment & Training Administration | heuristic |
| `src/content/sources/fred/core_cpi.yaml` | `CPILFESL` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Labor Statistics | heuristic |
| `src/content/sources/fred/core_pce.yaml` | `PCEPILFE` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Economic Analysis | heuristic |
| `src/content/sources/fred/cpi_energy.yaml` | `CPIENGSL` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Labor Statistics | heuristic |
| `src/content/sources/fred/cpi_food.yaml` | `CPIUFDSL` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Labor Statistics | heuristic |
| `src/content/sources/fred/cpi_medical.yaml` | `CPIMEDSL` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Labor Statistics | heuristic |
| `src/content/sources/fred/cpi_rent.yaml` | `CUUR0000SEHA` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Labor Statistics | heuristic |
| `src/content/sources/fred/cpi_shelter.yaml` | `CUUR0000SAH1` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Labor Statistics | heuristic |
| `src/content/sources/fred/cpi_yoy.yaml` | `CPIAUCSL (transformation=pc1)` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Labor Statistics | heuristic |
| `src/content/sources/fred/dc_cpi.yaml` | `CUUSA311SA0` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Labor Statistics | heuristic |
| `src/content/sources/fred/fed_funds.yaml` | `FEDFUNDS` | FRED (St. Louis Fed) | Public domain (US government data) | Board of Governors of the Federal Reserve System | heuristic |
| `src/content/sources/fred/gdp_deflator.yaml` | `GDPDEF` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Economic Analysis | heuristic |
| `src/content/sources/fred/headline_pce.yaml` | `PCEPI` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Economic Analysis | heuristic |
| `src/content/sources/fred/housing_starts.yaml` | `HOUST` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Census Bureau | heuristic |
| `src/content/sources/fred/initial_claims.yaml` | `ICSA` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Employment & Training Administration | heuristic |
| `src/content/sources/fred/payrolls.yaml` | `PAYEMS` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Labor Statistics | heuristic |
| `src/content/sources/fred/recession_probability_ny_fed.yaml` | `RECPROUSM156N` | FRED (St. Louis Fed) | Public domain (US government data) | Federal Reserve Bank of St. Louis | heuristic |
| `src/content/sources/fred/tips_10y.yaml` | `DFII10` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Treasury | heuristic |
| `src/content/sources/fred/tips_5y.yaml` | `DFII5` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Treasury | heuristic |
| `src/content/sources/fred/us_10y.yaml` | `DGS10` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Treasury | heuristic |
| `src/content/sources/fred/us_2y.yaml` | `DGS2` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Treasury | heuristic |
| `src/content/sources/fred/us_30y.yaml` | `DGS30` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Treasury | heuristic |
| `src/content/sources/fred/us_3mo.yaml` | `DGS3MO` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Treasury | heuristic |
| `src/content/sources/fred/us_5y.yaml` | `DGS5` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Treasury | heuristic |
| `src/content/sources/fred/us_cpi.yaml` | `CPIAUCSL` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Labor Statistics | heuristic |
| `src/content/sources/fred/us_real_gdp.yaml` | `GDPC1` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Economic Analysis | heuristic |
| `src/content/sources/fred/us_unemployment.yaml` | `UNRATE` | FRED (St. Louis Fed) | Public domain (US government data) | U.S. Bureau of Labor Statistics | heuristic |

## UNKNOWN (109)

**Action**: VERIFY manually on the FRED series page; update YAML or this audit's heuristic table.

| YAML | Series | Declared provider | Declared license | Owner (resolved) | Source |
| --- | --- | --- | --- | --- | --- |
| `src/content/sources/fred/avg_hourly_earnings.yaml` | `AHETPI` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/building_permits.yaml` | `PERMIT` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/capacity_util.yaml` | `TCU` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/cny_usd.yaml` | `DEXCHUS` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/dc_case_shiller.yaml` | `WDXRSA` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/dc_median_listing.yaml` | `MEDLISPRI47900` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/dc_payrolls.yaml` | `WASH911NA` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/dc_unemployment_rate.yaml` | `WASH911URN` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/fed_balance_sheet.yaml` | `WALCL` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/federal_debt_pct_gdp.yaml` | `GFDEGDQ188S` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/federal_debt_total.yaml` | `GFDEBTN` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/federal_defense.yaml` | `FDEFX` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/federal_defense_spending.yaml` | `FDEFX` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/federal_deficit_pct_gdp.yaml` | `FYFSGDA188S` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/federal_interest.yaml` | `A091RC1Q027SBEA` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/federal_interest_pct_gdp.yaml` | `FYOIGDA188S` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/federal_medicaid.yaml` | `W729RC1Q027SBEA` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/federal_medicare.yaml` | `W824RC1Q027SBEA` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/federal_nondefense_spending.yaml` | `FNDEFX` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/federal_outlays_pct_gdp.yaml` | `FYONGDA188S` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/federal_receipts_pct_gdp.yaml` | `FYFRGDA188S` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/federal_social_security.yaml` | `W823RC1Q027SBEA` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/federal_subsidies.yaml` | `B096RC1Q027SBEA` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/homeowner_vacancy.yaml` | `RHVRUSQ156N` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/industrial_production_mining.yaml` | `IPMINE` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/jolts_openings.yaml` | `JTSJOL` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/labor_participation.yaml` | `CIVPART` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/m2.yaml` | `M2SL` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/manufacturing_employment.yaml` | `MANEMP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/manufacturing_weekly_hours.yaml` | `AWHMAN` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/median_home_price.yaml` | `MSPUS` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/median_listing_price.yaml` | `MEDLISPRIUS` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/months_supply.yaml` | `MSACSR` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/nasdaq.yaml` | `NASDAQCOM` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/nat_gas_henry_hub.yaml` | `DHHNGSP` | FRED (St. Louis Fed) / EIA | Public domain (US government data, EIA) | — | unresolved |
| `src/content/sources/fred/nber_recession.yaml` | `USREC` | FRED (St. Louis Fed) / NBER | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/new_home_sales.yaml` | `HSN1F` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/personal_income.yaml` | `PI` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/ppi_data_processing_hosting.yaml` | `PCU518210518210` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/ppi_semiconductor.yaml` | `PCU33443344` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/prime_age_participation.yaml` | `LNS11300060` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/productivity_mfg.yaml` | `OPHMFG` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/productivity_nfb.yaml` | `OPHNFB` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/quits_rate.yaml` | `JTSQUR` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/rental_vacancy.yaml` | `RRVRUSQ156N` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/retail_sales.yaml` | `RSAFS` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/sahm_rule.yaml` | `SAHMREALTIME` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/saving_rate.yaml` | `PSAVERT` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/sloos_cc_tightening.yaml` | `DRTSCLCC` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/sloos_ci_loans_tightening.yaml` | `DRTSCILM` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ak.yaml` | `AKPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_al.yaml` | `ALPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ar.yaml` | `ARPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_az.yaml` | `AZPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ca.yaml` | `CAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_co.yaml` | `COPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ct.yaml` | `CTPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_dc.yaml` | `DCPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_de.yaml` | `DEPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_fl.yaml` | `FLPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ga.yaml` | `GAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_hi.yaml` | `HIPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ia.yaml` | `IAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_id.yaml` | `IDPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_il.yaml` | `ILPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_in.yaml` | `INPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ks.yaml` | `KSPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ky.yaml` | `KYPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_la.yaml` | `LAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ma.yaml` | `MAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_md.yaml` | `MDPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_me.yaml` | `MEPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_mi.yaml` | `MIPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_mn.yaml` | `MNPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_mo.yaml` | `MOPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ms.yaml` | `MSPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_mt.yaml` | `MTPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_nc.yaml` | `NCPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_nd.yaml` | `NDPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ne.yaml` | `NEPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_nh.yaml` | `NHPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_nj.yaml` | `NJPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_nm.yaml` | `NMPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_nv.yaml` | `NVPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ny.yaml` | `NYPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_oh.yaml` | `OHPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ok.yaml` | `OKPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_or.yaml` | `ORPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_pa.yaml` | `PAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ri.yaml` | `RIPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_sc.yaml` | `SCPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_sd.yaml` | `SDPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_tn.yaml` | `TNPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_tx.yaml` | `TXPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_ut.yaml` | `UTPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_va.yaml` | `VAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_vt.yaml` | `VTPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_wa.yaml` | `WAPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_wi.yaml` | `WIPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_wv.yaml` | `WVPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/state_population_wy.yaml` | `WYPOP` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/stlfsi.yaml` | `STLFSI4` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/trade_balance.yaml` | `BOPGSTB` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/u6_unemployment.yaml` | `U6RATE` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/unit_labor_costs.yaml` | `ULCNFB` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/us_industrial_production.yaml` | `INDPRO` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/us_population.yaml` | `POPTHM` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/us_retail_diesel.yaml` | `GASDESW` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
| `src/content/sources/fred/us_retail_gasoline.yaml` | `GASREGW` | FRED (St. Louis Fed) | Public domain (US government data) | — | unresolved |
