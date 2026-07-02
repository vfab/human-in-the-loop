<!--
Sync Impact Report
- Version change: 1.2.0 -> 1.3.0
- Modified principles:
	- III. Unit and Integration Test Gate (NON-NEGOTIABLE) -> III. Unit and Integration Test and CI Monitoring Gate (NON-NEGOTIABLE)
- Added sections:
	- Post-Push CI/CD Monitoring
- Removed sections: none
- Templates requiring updates:
	- .github/agents/speckit.git.commit.agent.md: updated
- Follow-up TODOs: none
-->

# Human-in-the-Loop Repository Constitution

## Core Principles

### I. Layered Boundaries and Clear Responsibilities
Code SHOULD preserve clear separation between workflow orchestration, domain behavior, and external integrations. New modules MUST define a single primary responsibility and avoid hidden coupling.

### II. TDD Required (NON-NEGOTIABLE)
All feature and bug-fix work MUST follow Red-Green-Refactor. Authors MUST write failing tests before implementation changes and keep tests in the same change set as production code.

### III. Unit and Integration Test and CI Monitoring Gate (NON-NEGOTIABLE)
All unit tests and integration tests MUST pass before merge to main. The required baseline command is:
`python -m unittest discover -s tests -p "test_*.py" -q`
If local workflows use additional checks (for example pytest or coverage), they MAY be stricter, but they MUST not replace this baseline gate unless CI is updated first.
After every push that includes code or infrastructure changes, authors MUST monitor CI/CD execution to completion and treat failures as blocking until resolved.

### IV. Coverage Visibility and Improvement
Coverage SHOULD be visible for meaningful modules and MUST trend upward over time. When coverage tooling is enabled, exclusions MUST be narrowly scoped and justified in code comments or review notes.

### V. Operational Traceability
User-impacting workflows and service endpoints MUST emit logs that are structured enough to correlate request flow and troubleshoot failures. Production deployments SHOULD include centralized log routing when platform capabilities are available.

## Testing Standards

- Baseline unit test command: `python -m unittest discover -s tests -p "test_*.py" -q`
- Integration test suites MUST exist for cross-component and external-service flows.
- All tests MUST pass locally before committing merge-ready changes.
- CI/CD enforces the merge gate; a failing pipeline blocks merge.

## Integration CI/CD Gate

- CI/CD MUST run integration tests in addition to unit tests on pull requests and on merges to `main`.
- Integration tests MUST be treated as blocking checks, not informational checks.

## Post-Push CI/CD Monitoring

- After each push, authors MUST check workflow status and confirm pass/fail outcomes.
- If any required workflow fails, authors MUST investigate logs, apply fixes, and re-run CI/CD until required checks pass.

## Quality Gates

- Semantic versioning for releases uses MAJOR.MINOR.PATCH.
- Risky or user-facing behavior changes SHOULD use explicit rollout controls where feasible.
- Continuous improvement is expected; technical debt discovered during feature work SHOULD be tracked.

## Governance

This constitution supersedes conflicting local practices for this repository. Amendments MUST be documented in the PR description that introduces the change, including rationale and impact. All PRs MUST verify compliance with these principles. Complexity must be justified.

**Version**: 1.3.0 | **Ratified**: 2025-01-01 | **Last Amended**: 2026-07-02
