# Project overview and contribution

## Problem
Repeated job searches across multiple websites made it difficult to compare fit, track deadlines and preserve application notes. The goal was a local tool that could keep working without access to a paid chat service.

## My contribution
I defined and iteratively refined the requirements: manual per-site searches, recent publication windows, fit/deadline ordering, duplicate handling, application statuses and explicit eligibility gaps. I used AI assistance to implement and revise the dashboard and browser workflow, reviewed search results, and adjusted the rules based on practical issues such as uncertain posting dates and unreliable coverage. Code generation assistance is acknowledged; I do not claim independently writing every line.

## Workflow
User starts a search -> adapter/browser reads supported pages -> original dates and duplicates are checked -> candidates enter a review inbox -> user verifies fit and eligibility -> saved jobs appear with statuses, notes and deadlines.

## Implementation
Python local HTTP service, HTML/CSS/JavaScript dashboard, public-site parsers and Playwright Chromium. A worker thread owns the browser. Local JSON overlays preserve user edits. Coverage and unknowns are surfaced rather than hidden.

## Evidence and boundaries
Tests use controlled fixtures for date validation, blocked/login detection, removed-job deduplication and pagination. They do not establish exhaustive or reliable live coverage. No measured time savings or autonomous AI-agent capabilities are claimed. Future work includes portal robustness, configurable rules and stronger end-to-end verification.
