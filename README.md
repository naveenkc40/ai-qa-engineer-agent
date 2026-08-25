# Evidence-Grounded Agentic Quality Engineering Platform

An agentic quality engineering platform that turns natural-language requirements into evidence-grounded Playwright tests, executes only deterministically accepted output, and carries runtime evidence into structured root-cause analysis (RCA).

[![CI](https://github.com/naveenkc40/ai-qa-engineer-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/naveenkc40/ai-qa-engineer-agent/actions/workflows/ci.yml)
[![Docker validation](https://github.com/naveenkc40/ai-qa-engineer-agent/actions/workflows/docker.yml/badge.svg)](https://github.com/naveenkc40/ai-qa-engineer-agent/actions/workflows/docker.yml)
[![Python 3.10–3.12](https://img.shields.io/badge/python-3.10%E2%80%933.12-3776AB?logo=python&logoColor=white)](https://github.com/naveenkc40/ai-qa-engineer-agent/blob/main/.github/workflows/ci.yml)
[![Playwright 1.62.0](https://img.shields.io/badge/Playwright-1.62.0-2EAD33?logo=playwright&logoColor=white)](https://github.com/naveenkc40/ai-qa-engineer-agent/blob/main/requirements.txt)

This portfolio project explores the engineering boundary between probabilistic AI reasoning, deterministic validation, and browser/runtime evidence. It does not claim that an LLM replaces quality-engineering judgment.

## Problem being solved

LLMs can draft plausible tests quickly, but plausible selectors, routes, application states, and diagnoses are unsafe in an automation pipeline. This project observes an authenticated application first, constrains generation to that evidence, rejects unsupported output in code, and retains execution artifacts for evidence-bounded RCA.

## Key capabilities

- Converts requirements into structured, independently executable scenarios.
- Authenticates through Playwright with environment-provided credentials and saves runtime-only browser state.
- Discovers observed pages, products, controls, locator candidates, ARIA data, and network resources.
- Gives test generation only scenario-relevant application evidence and exact citation references.
- Rejects unsupported URLs, selectors, test IDs, role/name pairs, labels, filenames, or evidence citations before execution.
- Runs accepted tests in isolated pytest subprocesses and retains stdout, stderr, screenshots, traces, and browser errors when available.
- Applies deterministic failure classification before optional evidence-bounded model analysis.
- Persists per-run reports, outcomes, measured durations, and grounding counts.

## Architecture

`QAOrchestrator` coordinates six implemented specialist agents and persists the workflow result. The main evidence path is:

```text
Requirement → RequirementAgent → AuthenticationAgent → ApplicationDiscoveryAgent
            → evidence/application map → TestGenerationAgent
            → deterministic grounding gate → ExecutionAgent → Playwright/pytest evidence
            → RCAAgent → final report
```

See [Architecture](docs/architecture.md) for the Mermaid diagram, trust boundaries, contracts, and failure behavior.

## Evidence grounding and hallucination control

Discovery writes an authenticated application map. Generation receives only the scenario-relevant subset and must cite exact `path=value` entries from a generated evidence catalog. A deterministic post-generation gate rejects invented URLs, selectors, test IDs, role/name pairs, labels, unsafe filenames, missing code, and unknown citations. Rejected scenarios become `cannot_generate` results and are never executed.

Grounded means supported by the captured map and implemented literal checks—not proof of functional correctness in every application state. The current gate is not a complete Python semantic verifier.

RCA consumes pytest output and available browser artifacts. Known setup and browser failures are classified without an LLM. Other failures are pre-classified before model analysis; the returned classification is restored deterministically, and missing evidence is reported explicitly. RCA is advisory and should be confirmed by a human.

## Agent responsibilities

| Component | Implemented responsibility |
|---|---|
| `RequirementAgent` | Convert requirement prose into schema-constrained scenarios. |
| `AuthenticationAgent` | Log in and save Playwright `storage_state` using environment credentials. |
| `ApplicationDiscoveryAgent` | Reopen the authenticated session and collect application and stateful-flow evidence. |
| `TestGenerationAgent` | Draft a test or return `cannot_generate`, then validate cited facts and supported literals. |
| `ExecutionAgent` | Permit only grounded generated results, run pytest in isolation, and retain execution evidence. |
| `RCAAgent` | Deterministically classify known failures and bound optional model analysis to supplied evidence. |
| `QAOrchestrator` | Sequence stages, continue independent scenarios, calculate run metrics, and write reports. |

## End-to-end workflow

1. The user enters a requirement; `RequirementAgent` derives structured scenarios.
2. The orchestrator reuses a valid authenticated map or invokes authentication and discovery.
3. `TestGenerationAgent` selects relevant evidence and asks Gemini for schema-constrained output.
4. The deterministic grounding gate accepts the test or records why it cannot be generated.
5. `ExecutionAgent` runs each accepted test in a separate pytest process.
6. `RCAAgent` analyzes every failed/error result from retained evidence.
7. The orchestrator writes `workflow_result.json` and `final_report.json` under `reports/runs/<run-id>/`.

## Quick start

Prerequisites: Python 3.10 or newer and a Chromium-compatible host.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m playwright install chromium
cp .env.example .env
```

Configure `.env` with a Gemini key, target URL, and credentials for a disposable test account:

```dotenv
GEMINI_API_KEY=your_key
QA_BASE_URL=https://www.saucedemo.com
QA_USERNAME=your_username
QA_PASSWORD=your_password
```

Then run:

```bash
python app.py
```

Enter a multiline requirement and type `END` on its own line. The current discovery implementation is tailored to SauceDemo's inventory DOM. A valid checked-in application map can be reused; otherwise authentication creates local `application_context/storage_state.json` before discovery.

The checked-in [examples](examples/) follow a sample cart requirement through analysis, grounding, execution, RCA, and reporting. Example metric fields are deliberately `null` where they are not measurements from a recorded run.

## Docker execution

The image uses Microsoft's Playwright Python runtime matching Playwright 1.62.0 and installs runtime plus development dependencies.

```bash
docker build -t ai-qe-agent .
docker run --rm ai-qe-agent ruff check .
docker run --rm ai-qe-agent python -m pytest
```

Running the live workflow requires supplying runtime environment values. Do not bake `.env`, API keys, credentials, or browser state into the image.

## Testing

The default pytest configuration deliberately excludes tests marked `generated` or `external`:

```bash
ruff check .
python -m pytest
python -m pytest --cov=agents --cov=tools --cov-report=term-missing
```

Files under `tests/generated/` are collection-marked as generated, external, and end-to-end. Run them only in an explicitly prepared environment with a valid target application and authentication state; they are not part of the deterministic PR gate.

## CI/CD

- [GitHub Actions CI](.github/workflows/ci.yml) runs Ruff and deterministic pytest with coverage on Python 3.10, 3.11, and 3.12, then uploads JUnit and coverage XML artifacts.
- [Docker validation](.github/workflows/docker.yml) builds the image, runs Ruff and deterministic pytest inside it, and uploads container test evidence.
- [Jenkinsfile](Jenkinsfile) provides native setup/static-analysis/tests, Docker build/container validation, and evidence publication stages.

See [CI/CD design](docs/ci-cd.md) for gate boundaries and artifact details.

## Security model

- Credentials come from environment variables; authentication state is runtime-only.
- `.env`, storage-state patterns, reports, browser traces, screenshots, logs, and coverage output are ignored from source control and the Docker build context.
- Credentials are not intentionally added to generation prompts or workflow reports.
- Application maps and browser artifacts can still contain sensitive observations and must be reviewed before sharing.
- Generated code is not trusted solely because an LLM returned it; deterministic grounding status is required before execution.

See [Security policy](SECURITY.md) for reporting guidance and handling rules.

## Current verified metrics

Verified locally on 2026-08-25 using the repository's default deterministic gate:

| Metric | Verified value |
|---|---:|
| Deterministic tests | 53 passed |
| Generated/external browser tests excluded by default | 9 deselected |
| Configured coverage (`agents` + `tools`) | 60% |
| GitHub Actions Python matrix | 3.10, 3.11, 3.12 |
| Container runtime | Playwright/Python image, validated by a dedicated workflow |

The test run collected 62 tests in total. These are repository validation facts, not benchmark, accuracy, adoption, productivity, or enterprise-usage claims.

Per-workflow operational metrics are calculated rather than hard-coded: phase latency, summed execution duration, grounding success rate, generated-to-skipped ratio, and generated/skipped/passed/failed/error counts.

## Repository structure

```text
.
├── agents/                 # Specialist agents and orchestrator
├── application_context/    # Application maps; runtime storage state is ignored
├── docs/                   # Architecture, CI/CD, demo, and roadmap
├── examples/               # Illustrative structured inputs and outputs
├── tests/                  # Deterministic tests and isolated generated browser tests
├── tools/                  # Supporting authentication, discovery, and file utilities
├── .github/workflows/      # Python CI and Docker validation
├── app.py                  # Interactive CLI entry point
├── Dockerfile              # Reproducible Playwright/Python runtime
├── Jenkinsfile             # Jenkins validation pipeline
├── pytest.ini              # Default deterministic test selection
└── pyproject.toml          # Ruff target configuration
```

## Roadmap

Implemented and planned capabilities are separated in [Roadmap](docs/roadmap.md). Planned items are proposals and are not represented as current functionality.

## Contributing

See [Contributing guide](CONTRIBUTING.md) for environment setup, branch/PR expectations, required validation, and secret-handling rules.

## License

No license file is currently present. Until the maintainers add one, the repository should not be assumed to grant open-source reuse rights; this is also why no license badge is shown.
