# Local Job Search Dashboard

A Python dashboard for manually discovering, reviewing and tracking Denmark student-job opportunities. Built through AI-assisted development: I defined the requirements, refined the search and review workflow, and reviewed the results. The application runs locally without a ChatGPT subscription.

## What it does
- Per-website search controls and a separate candidate review inbox.
- Public-site discovery adapters, plus a dedicated Playwright/Chromium browser for JobTeaser and LinkedIn. Sign in directly in the local browser.
- Publication-date checks, duplicate detection and preservation of removed jobs and user edits.
- Saved-job sorting by fit and deadline, application statuses, dates, notes and document attachments.
- Search-health reporting that distinguishes checked, partial, blocked and unverifiable coverage.

## AI-assisted development, not an autonomous AI agent
AI assistance was used to develop and revise the software. The published runtime uses Python rules, HTML/structured-data parsing and browser automation. It does not independently call an LLM, generate application drafts or infer verified candidate suitability. User review remains necessary. No applications or employer messages are submitted.

## Setup (Windows)
1. Install Python 3.12 or newer with pip from python.org.
2. Download this repository ZIP and extract it to a writable folder.
3. Run `SETUP.cmd` to create a local environment and install Playwright Chromium.
4. Run `OPEN-DASHBOARD.cmd`. The local service listens at `http://127.0.0.1:8765`.
5. Open a supported site, sign in yourself if required, and use its search button. Review coverage and candidates before saving.

Alternatively run `python setup_independent.py`, then `.venv\Scripts\python.exe launch_local.py`. For server-only use, run `.venv\Scripts\python.exe dashboard_server.py` and open the localhost URL in a browser.

Empty records and a generic local preferences file are created automatically. Edit preferences locally; some Denmark/student/technical search rules and UI constraints are still hard-coded and require code changes to customize. This is a personal-project prototype, not a configurable commercial product.

## Limitations and verification
- Public-source adapters depend on each site's markup and available original posting dates.
- Browser searches are bounded to ten result pages and forty relevant details, not exhaustive inventories.
- New browser discovery requires an original publication date within seven days. Unknown dates and login/website failures are reported rather than presented as successful coverage.
- Fixture tests check publication freshness, login detection, duplicate handling and a two-page search loop. Live signed-in portal reliability and real browser persistence require validation on the user's PC.
- Fit, English eligibility, exact workplace, actual cycle route and monthly working hours need human verification. Weekly hours are not an actual monthly roster.
- Searches are manual; there is no installed scheduler or reminder service in this repository. Dashboard deadline information is available for review.

## Privacy
The repository contains code and an empty-data initializer only. Browser sessions, saved jobs, contact information, CVs, application history and logs are excluded. `.local-browser/profile` contains private browser sessions: never publish it. The service binds to loopback and uses a per-process token for write requests. Keep it local.

## Tests
Run `python -m unittest test_browser_search -v`. These tests use fixtures and make no live job-site requests; the optional real Chromium test is skipped by default.

## Project structure
- `index.html`: dashboard interface.
- `dashboard_server.py`: local records API and validation.
- `independent_search.py`: public discovery, freshness and deduplication.
- `browser_search.py`: dedicated browser worker and bounded searches.
- `browser_import.py`: validation and import of supported page results.
- `initialize_data.py`: empty local storage setup.
- `setup_independent.py`, `launch_local.py`: installation and startup.
- `test_browser_search.py`: fixture tests.

## Development decisions
See [PROJECT.md](PROJECT.md) for the problem, workflow and personal contribution.
