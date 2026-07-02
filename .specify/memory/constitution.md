<!--
Sync Impact Report
- Version change: 1.0.0 -> 1.1.0
- Modified principles:
	- III. All Unit Tests Must Pass Before Merge (NON-NEGOTIABLE) -> III. CI-Aligned Test Gate (NON-NEGOTIABLE)
	- IV. Minimum 95% Code Coverage -> IV. Coverage Visibility and Improvement
- Added sections: none
- Removed sections: none
- Templates requiring updates:
	- .specify/templates/plan-template.md: not required
	- .specify/templates/spec-template.md: not required
	- .specify/templates/tasks-template.md: not required
	- .github/agents/speckit.plan.agent.md: updated
	- .github/agents/speckit.git.commit.agent.md: updated
	- .github/agents/speckit.git.initialize.agent.md: updated
- Follow-up TODOs: none
-->

# Human-in-the-Loop Repository Constitution

## Core Principles

### I. Layered Boundaries and Clear Responsibilities
Code SHOULD preserve clear separation between workflow orchestration, domain behavior, and external integrations. New modules MUST define a single primary responsibility and avoid hidden coupling.

### II. Test-First or Test-With-Change (NON-NEGOTIABLE)
Every behavior change MUST include tests in the same change set. Teams SHOULD prefer red-green-refactor where practical, and MUST not merge behavior changes without updated or added automated tests.

### III. CI-Aligned Test Gate (NON-NEGOTIABLE)
All unit tests MUST pass before merge to main. The required baseline command is:
`python -m unittest discover -s tests -p "test_*.py" -q`
If local workflows use additional checks (for example pytest or coverage), they MAY be stricter, but they MUST not replace this baseline gate unless CI is updated first.

### IV. Coverage Visibility and Improvement
Coverage SHOULD be visible for meaningful modules and MUST trend upward over time. When coverage tooling is enabled, exclusions MUST be narrowly scoped and justified in code comments or review notes.

### V. Operational Traceability
User-impacting workflows and service endpoints MUST emit logs that are structured enough to correlate request flow and troubleshoot failures. Production deployments SHOULD include centralized log routing when platform capabilities are available.

## Testing Standards

- Baseline unit test command: `python -m unittest discover -s tests -p "test_*.py" -q`
- All tests MUST pass locally before committing merge-ready changes.
- CI/CD enforces the merge gate; a failing pipeline blocks merge.

## Quality Gates

- Semantic versioning for releases uses MAJOR.MINOR.PATCH.
- Risky or user-facing behavior changes SHOULD use explicit rollout controls where feasible.
- Continuous improvement is expected; technical debt discovered during feature work SHOULD be tracked.

## Governance

This constitution supersedes conflicting local practices for this repository. Amendments MUST be documented in the PR description that introduces the change, including rationale and impact. All PRs MUST verify compliance with these principles. Complexity must be justified.

**Version**: 1.1.0 | **Ratified**: 2025-01-01 | **Last Amended**: 2026-07-02
