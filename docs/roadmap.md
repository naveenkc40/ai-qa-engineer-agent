# Roadmap

This roadmap distinguishes code that exists in the repository from possible future work. Every item under **Planned** is not currently implemented.

## Implemented

- Schema-constrained requirement analysis through `RequirementAgent`.
- Environment-based SauceDemo authentication and Playwright storage-state creation.
- Authenticated SauceDemo application discovery with observed UI, ARIA, locator, network-resource, and selected stateful cart-flow evidence.
- Scenario-relevant evidence selection and citation catalogs for test generation.
- Deterministic post-generation checks for supported URLs, selectors, test IDs, role/name pairs, labels, filenames, completeness, and citations.
- Safe `cannot_generate` results when required evidence is absent or output fails grounding.
- Isolated pytest execution of accepted generated tests with retained runtime evidence.
- Ordered deterministic failure pre-classification and evidence-bounded, model-assisted RCA.
- `QAOrchestrator` workflow coordination, per-run metrics, partial-failure handling, and JSON reports.
- Deterministic CI on Python 3.10–3.12, Docker validation, and a Jenkins validation pipeline.

## Planned — not currently implemented

- Pluggable application-discovery adapters beyond the current SauceDemo-specific implementation.
- An API testing agent.
- A test-data agent for controlled setup, isolation, and cleanup.
- A multi-LLM provider abstraction.
- An LLM evaluation framework for repeatable generation and RCA assessment.
- A quality-intelligence dashboard for trends and workflow evidence.
- A separately governed AI integration CI stage for model- and external-browser-dependent tests.
- AST-based and semantic validation beyond the current literal grounding checks.
- Schema versioning and machine-readable metric definitions.
- Configurable artifact redaction and retention policies.
- Explicit unauthenticated-scenario support alongside authenticated execution.

Planned items describe direction only. They should not be read as available features, delivery commitments, or performance claims.
