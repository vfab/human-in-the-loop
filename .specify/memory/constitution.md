# AI Knowledge Assistant Constitution

## Core Principles

### I. SOLID & Clean Architecture
Follow SOLID principles and layered Clean Architecture: API → Service → Domain → Data. Dependencies point inward only; Domain has no outward dependencies.

### II. Test-First (NON-NEGOTIABLE)
TDD mandatory: tests written before or alongside production code. Red-Green-Refactor cycle strictly enforced. No implementation ships without corresponding tests.

### III. All Unit Tests Must Pass Before Merge (NON-NEGOTIABLE)
All unit tests must pass before any merge to `main`. This is an absolute gate — a failing unit test is a blocker, not a warning. The test command is:
`python -m pytest tests/unit/ -q --cov=. --cov-report=term-missing`

### IV. Minimum 95% Code Coverage
Minimum code coverage: **95%** measured by `pytest-cov` across `backend/`. Untestable lines (e.g. optional native drivers, third-party env-var setup) must be explicitly noted in comments and excluded from the coverage gate.

### V. Observability
All services must emit structured JSON logs to stdout. Every deployed service must have a diagnostic setting routing logs to the shared log aggregation workspace. All log entries must include a `correlation_id`. No service ships without observability.

## Testing Standards

- Unit test command: `python -m pytest tests/unit/ -q --cov=. --cov-report=term-missing`
- Frontend test command: `cd frontend && npm test`
- All tests must pass locally before committing
- CI/CD enforces the same gate — a red pipeline blocks merge

## Quality Gates

- Feature flags recommended for all new user-facing features
- Semantic versioning required (MAJOR.MINOR.BUILD)
- Continuous improvement enforced — tech debt tracked and addressed
- The Reviewer agent validates TDD compliance and standards on every PR

## Governance

This constitution supersedes all other practices. Amendments require documentation in `docs/decisions/` as an ADR. All PRs must verify compliance with these principles. Complexity must be justified. Refer to `agents/` for role responsibilities and `docs/how-to/` for process guidance.

**Version**: 1.0.0 | **Ratified**: 2025-01-01 | **Last Amended**: 2026-05-08
