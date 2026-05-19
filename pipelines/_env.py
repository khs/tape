"""
Shared dotenv loader for every pipeline that needs an API key.

Why this is one module instead of inline `from dotenv import
load_dotenv; load_dotenv()` at the top of each pipeline:
  - One import to maintain instead of N copies.
  - Comments live in one place explaining what env vars we use.
  - In GitHub Actions, environment variables are already set
    via the workflow's `env:` block; load_dotenv() is a no-op
    if there's no .env file, so this is safe to import
    unconditionally.

Environment variables consumed by the pipelines (May 2026):
  CENSUS_API_KEY  — tract + block-group ACS fetches (required;
                    state + county work without it but slow).
                    Sign up: https://api.census.gov/data/key_signup.html
  BEA_API_KEY     — every BEA endpoint (required, 36 chars).
                    Sign up: https://apps.bea.gov/API/signup/index.cfm

Local development: drop a `.env` file in the repo root (already
covered by .gitignore's `.env*` pattern). Format:
  CENSUS_API_KEY=...your-key...
  BEA_API_KEY=...your-key...

Production: GitHub Actions secrets are surfaced as env vars via
the workflow file (`env: BEA_API_KEY: ${{ secrets.BEA_API_KEY }}`),
not via .env. load_dotenv() finds no .env there and silently
no-ops, which is correct.
"""
from dotenv import load_dotenv

# Search upward from the importing pipeline's location for a .env
# file — find_dotenv() default behavior. If nothing's found,
# environment variables already set by the calling shell / CI take
# precedence (load_dotenv NEVER overwrites a pre-set var unless
# you pass override=True).
load_dotenv()
