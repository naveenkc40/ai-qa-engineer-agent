# Five-minute demo

## Before the interview

- Create `.env` locally with `GEMINI_API_KEY`, `QA_BASE_URL`, `QA_USERNAME`, and `QA_PASSWORD`.
- Install dependencies and Chromium as described in the README.
- Ensure the target account is a disposable demo account; never open `.env` or `storage_state` on screen.
- Keep [`examples/`](../examples/) open as a deterministic fallback if network or model access is unavailable.

## 0:00–0:45 — Frame the problem

“LLMs write plausible UI tests, but plausible selectors and diagnoses are not safe. This project separates reasoning from observation and adds deterministic gates before generated code can execute.”

Show the README architecture diagram and point out the sequence from requirement analysis to final report.

## 0:45–1:30 — Show the evidence boundary

Open `application_context/authenticated_application_map.json`. Show an observed product, its `data-test` value, and the authenticated page URL. Explain that credentials created a local Playwright session snapshot but credentials themselves are neither persisted in this map nor sent into the generation prompt.

Open `TestGenerationAgent._grounding_check`. Highlight that cited evidence must exist and unsupported URL/locator literals convert the response to `cannot_generate`.

## 1:30–2:30 — Run one story

Run:

```bash
python app.py
```

Enter:

```text
As a shopper, I want to add Sauce Labs Backpack to my cart so that I can purchase it later.
```

Narrate the five progress stages. If a live dependency fails, switch immediately to the checked-in examples and state that they are illustrative structures, not recorded performance evidence.

## 2:30–3:30 — Inspect the output

Open the printed `reports/runs/<run-id>/final_report.json`. Show:

- the original requirement and structured scenarios;
- generated versus skipped results and `missing_evidence`;
- execution status and artifact paths;
- measured latency/count fields;
- overall `PASSED`, `FAILED`, `PARTIAL`, or `BLOCKED` status.

Emphasize that rate and ratio fields are derived from this run. There are no benchmark claims.

## 3:30–4:20 — Demonstrate failure safety

Use [`examples/rca_result.json`](../examples/rca_result.json) or a real failed run. Explain ordered deterministic failure classification, explicit missing evidence, and why a setup failure before page creation never invokes the model for page-level speculation.

Mention that screenshots and traces are collected best-effort on failed browser tests.

## 4:20–5:00 — Close with engineering judgment

State the honest limitations: discovery is SauceDemo-specific, grounding is literal-pattern based rather than full semantic verification, authenticated state is not yet restored by the execution fixture, and model-assisted RCA requires human confirmation.

Close with the next engineering steps: pluggable discovery adapters, authenticated execution, AST-based validation, schema versioning, and artifact redaction/retention.
