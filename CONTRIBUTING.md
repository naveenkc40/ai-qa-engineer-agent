# Contributing

Thank you for helping improve the Evidence-Grounded Agentic Quality Engineering Platform. Changes should preserve the boundary between probabilistic reasoning, deterministic validation, and runtime evidence.

## Environment setup

Use Python 3.10–3.12 to match the GitHub Actions matrix:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m playwright install chromium
```

Copy `.env.example` to `.env` only when working with live authentication or model-backed flows. Use a disposable test account and never commit the resulting file or browser state.

## Branch naming

Use a short, descriptive branch name such as:

- `feature/pluggable-discovery`
- `fix/grounding-selector-check`
- `docs/ci-gate-explanation`
- `test/rca-timeout-classification`

Keep each branch and pull request focused on one coherent change.

## Testing expectations

Before opening a pull request, run:

```bash
ruff check .
python -m pytest
```

Changes to agents, orchestration, validation, or utilities should add or update deterministic tests. The default suite excludes generated/external browser tests. If a change affects those tests, explain the prepared environment and provide relevant evidence without publishing secrets or authenticated artifacts.

To reproduce the CI coverage command:

```bash
python -m pytest \
  --cov=agents \
  --cov=tools \
  --cov-report=term-missing \
  --cov-report=xml:coverage.xml
```

Coverage is evidence for review; the repository currently does not enforce a minimum threshold.

## Docker validation

Consider Docker validation for dependency, Playwright, browser-runtime, or container changes:

```bash
docker build -t ai-qe-agent .
docker run --rm ai-qe-agent ruff check .
docker run --rm ai-qe-agent python -m pytest
```

Document why Docker validation was not applicable when a pull request changes container-relevant behavior but was not tested locally.

## Pull-request expectations

- Explain the problem, approach, risk, and validation performed.
- Keep technical and metric claims traceable to code, tests, or retained non-sensitive evidence.
- Do not claim benchmark, coverage, adoption, productivity, or enterprise results that were not measured.
- Update documentation when behavior, configuration, trust boundaries, or operator steps change.
- Preserve the safe failure path: unsupported generated output must not execute.
- Avoid unrelated formatting or behavioral changes.
- Complete the repository pull-request checklist.

## Secrets and authentication artifacts

Never commit or attach:

- `.env` or environment-specific configuration containing secrets;
- LLM/API keys, passwords, access tokens, cookies, or session identifiers;
- Playwright `storage_state` or similarly named authentication-state files;
- authenticated screenshots, traces, videos, HAR files, browser logs, or execution reports unless they have been deliberately reviewed and redacted.

Before pushing, inspect `git status`, the staged diff, and newly added artifacts. If a secret was committed, treat it as exposed: rotate or revoke it and remove it from repository history through the appropriate incident process.
