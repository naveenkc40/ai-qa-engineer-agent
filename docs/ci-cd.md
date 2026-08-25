# CI/CD design

The repository keeps deterministic code validation in pull-request gates and separates generated/external browser tests that depend on live application state, credentials, network availability, or model output.

## GitHub Actions

### Python CI

[`ci.yml`](../.github/workflows/ci.yml) runs on pushes and pull requests targeting `main`.

- Matrix validation on Python 3.10, 3.11, and 3.12.
- Runtime and development dependency installation from the pinned requirements files.
- Static analysis with `ruff check .`.
- Deterministic pytest selected by [`pytest.ini`](../pytest.ini).
- Coverage measurement for `agents` and `tools`, with terminal and Cobertura XML output.
- JUnit XML and `coverage.xml` upload for every matrix entry, including failed runs when files exist.

### Docker validation

[`docker.yml`](../.github/workflows/docker.yml) runs on pushes and pull requests targeting `main`, and supports manual dispatch.

- Builds [`Dockerfile`](../Dockerfile) through Buildx without pushing an image.
- Uses GitHub Actions cache for build layers.
- Runs Ruff inside the built image.
- Runs the deterministic pytest suite with coverage inside the container.
- Uploads container JUnit and coverage evidence from `docker-test-results/`.

The Docker base image is Microsoft's Playwright Python image at the same Playwright version pinned in `requirements.txt`.

## Jenkins

[`Jenkinsfile`](../Jenkinsfile) implements the same validation intent for a Jenkins worker with Python 3.10+, virtual-environment support, and Docker:

1. **Environment Setup** creates a native virtual environment, verifies Python 3.10+, and installs pinned runtime/development dependencies.
2. **Static Analysis** runs Ruff in the native environment.
3. **Deterministic Tests** runs pytest with JUnit and coverage XML output.
4. **Docker Build** builds a job-number-tagged local image.
5. **Container Validation** runs Ruff and deterministic pytest in that image.
6. **Evidence Publishing** publishes JUnit results and archives native/container test evidence, coverage XML, and any configured execution evidence.

The `post` section attempts evidence publication even after an earlier failure, then removes the job virtual environment and local image. Jenkins retention is configured for 30 builds and 10 artifact sets.

## Why AI/browser tests are outside the PR gate

Tests under `tests/generated/` are automatically marked `generated`, `external`, and `e2e` during collection. The default pytest expression excludes `generated` and `external`, so both GitHub Actions and Jenkins run the deterministic component/orchestrator suite by default.

Generated browser tests can require an external target, valid credentials, unexpired Playwright storage state, installed browser support, and application data in a particular state. Some workflow stages also depend on Gemini and can vary between calls. Treating those dependencies as a required PR signal would mix source-code regressions with model, network, authentication, target-environment, and test-data failures.

An explicit future AI integration stage can run these tests in a controlled environment with secret injection, disposable accounts/data, artifact redaction, retention rules, and a separately understood failure policy. Until that exists, generated/external tests should be invoked intentionally rather than by weakening the deterministic gate.

## Local parity

```bash
ruff check .
python -m pytest \
  --cov=agents \
  --cov=tools \
  --cov-report=term-missing \
  --cov-report=xml:coverage.xml

docker build -t ai-qe-agent .
docker run --rm ai-qe-agent ruff check .
docker run --rm ai-qe-agent python -m pytest
```

Coverage is measured and published as evidence; no minimum threshold is currently configured.
