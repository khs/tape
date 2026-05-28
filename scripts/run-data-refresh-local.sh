#!/usr/bin/env bash
# Local replica of refresh-data.yml + refresh-demographics.yml.
# Runs each pipeline step in sequence, never aborts on a single
# pipeline's failure (`continue-on-error` semantics), logs progress
# with timestamps so it's easy to see what's running. Output goes
# both to the log file and stderr so a `tail -f` works.
#
# NOT checked into CI — the GitHub workflows are still the source of
# truth. This file just makes "run the whole refresh on my laptop
# without going through Actions" a single command.
set -u
cd "$(dirname "$0")/.."

LOG="/tmp/tape-data-refresh-$(date +%Y%m%d-%H%M%S).log"
echo "Log: $LOG" >&2

step() {
  local label="$1"; shift
  local ts; ts=$(date +%H:%M:%S)
  echo "" | tee -a "$LOG" >&2
  echo "[$ts] ==> $label" | tee -a "$LOG" >&2
  echo "    $*" | tee -a "$LOG" >&2
  "$@" >>"$LOG" 2>&1 || echo "[$ts] (continue-on-error) step exited $?" | tee -a "$LOG" >&2
}

# --- Market data (weekly cadence equivalent) ---
step "FRED series" python pipelines/fred_series.py
step "Yahoo quotes" python pipelines/yahoo_quotes.py
# SEC EDGAR shares-outstanding feeds yahoo_marketcap (must run BEFORE
# it). Pulls quarterly XBRL filings back to 2009 — extends marketcap
# history well beyond yfinance's ~2017 floor.
step "SEC shares outstanding" python pipelines/sec_shares.py
step "Yahoo market caps" python pipelines/yahoo_marketcap.py
step "Countries relative" python pipelines/countries_relative.py
step "World Bank GDP" python pipelines/worldbank_gdp.py
step "BLS subseries" python pipelines/bls.py
step "CBO (manual XLSX only)" python pipelines/cbo.py
step "OECD" python pipelines/oecd.py
step "Treasury TIC" python pipelines/treasury_tic.py
step "USAspending state + CD" python pipelines/usaspending.py
step "Yahoo futures" python pipelines/yahoo_futures.py

# --- Demographics (monthly cadence equivalent) ---
step "Census ACS by CD" python pipelines/census_acs_cd.py
step "Census ACS by metro" python pipelines/census_acs_metro.py
step "Census ACS national" python pipelines/census_acs_national.py
step "Derive ACS state from CD" python pipelines/derive_acs_state_from_cd.py
step "ACS choropleth derive (state)" python pipelines/census_acs_choropleth_derive_state.py
step "ACS choropleth (state direct)" python pipelines/census_acs_choropleth.py --geo state
step "ACS choropleth (county)" python pipelines/census_acs_choropleth.py --geo county
step "ACS choropleth (tract, all states)" python pipelines/census_acs_choropleth.py --geo tract --state all
step "ACS choropleth (block_group, all states)" python pipelines/census_acs_choropleth.py --geo block_group --state all
step "World Bank extended" python pipelines/worldbank_extended.py
step "USAspending metro" python pipelines/usaspending_metro.py
step "BLS metro" python pipelines/bls_metro.py
step "SSA (manual files only)" python pipelines/ssa.py

# --- Generation of source YAMLs (idempotent) ---
step "Generate ACS-CD source YAMLs" python pipelines/_generate_acs_sources.py
step "Generate ACS-national source YAMLs" python pipelines/_generate_acs_national_sources.py
step "Generate Zillow source YAMLs" python pipelines/_generate_zillow_sources.py
step "Generate state-tract chart YAMLs" python pipelines/_generate_state_tract_charts.py
step "Generate state-BG chart YAMLs" python pipelines/_generate_state_bg_charts.py
step "Generate state-atlas dashboards" python pipelines/_generate_state_atlas_dashboards.py

# --- Post-processing (matches workflow tails) ---
step "Build per-source tile summaries" python pipelines/build_summaries.py
step "Regenerate generators-index" python pipelines/_generate_generators_index.py
step "Trim source data files" python pipelines/trim_source_data.py

# --- Provider-label audit (the GH workflows run this last, --strict; the
#     local script doesn't pass --strict so a single drift doesn't tank
#     the whole run. Re-run with --strict before commit if you want a
#     clean gate). ---
step "Audit source labels (lenient)" python scripts/audit_all_sources.py

# --- Source-copy normalization + audit. Rewrites any freshly-scaffolded
#     description/notes to the house style (no fetch/impl-detail leaks,
#     title acronyms spelled out); the audit is lenient here (no --strict)
#     to match the label audit above. The GH workflows run both with the
#     strict gate. ---
step "Normalize source descriptions" python pipelines/fix_source_descriptions.py
step "Audit source descriptions (lenient)" python pipelines/audit_source_descriptions.py

# --- Alert evaluation is DELIBERATELY OMITTED from the desktop run. ---
# check_alerts.py + dispatch_alert_emails.py talk to PRODUCTION Supabase
# (the SUPABASE_SERVICE_ROLE_KEY in .env is the prod key), so running
# them from a laptop refresh would:
#   (a) send real alert emails to real users from a dev/iteration run, and
#   (b) advance each rule's last_value_seen / last_value_t against prod —
#       which would make the scheduled weekly GitHub Actions run skip the
#       very observations it needs to evaluate (the windowed evaluator
#       keys its per-run window off last_value_t).
# Alerts therefore run ONLY from the GitHub workflows. If you truly need
# to evaluate alerts locally, run check_alerts.py by hand on purpose.

echo "" | tee -a "$LOG" >&2
echo "[$(date +%H:%M:%S)] DONE. Full log: $LOG" | tee -a "$LOG" >&2
