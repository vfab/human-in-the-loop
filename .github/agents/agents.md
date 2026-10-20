Always start your response with the phrase "Agent Active:"

# Agent Routing Guide

Use this table to select the right agent for a given task.

| Task | Agent |
|------|-------|
| Define requirements, write a spec, set acceptance criteria | Product |
| Validate a spec, review architecture, create an ADR | Architect |
| Troubleshoot a deployed/production issue to root cause | Architect |
| Write production code, implement a feature | Implementation |
| Write tests, define test cases, validate coverage | Test |
| Review a PR, enforce standards, check TDD compliance | Reviewer |
| CI/CD pipelines, infrastructure, deployments, observability wiring | DevOps |

## Full Role Definitions

- `.github/agents/architect.agent.md`
- `.github/agents/implementation.agent.md`
- `.github/agents/test.agent.md`
- `.github/agents/reviewer.agent.md`
- `.github/agents/devops.agent.md`
- `.github/agents/product.agent.md`

## Handoff Protocol (Required)

A "Handoff" section in an agent's own file is an instruction to act, not a note to summarize in your reply. When your work reaches the point described in your `## Handoff` section:

1. **Invoke the `agent` tool** targeting the named recipient agent. Do not merely state in your final reply that another agent should pick this up — call the tool. If `agent` is not in your `tools:` list, you cannot hand off; say so explicitly instead of pretending to.
2. **Pass a structured message**, not a one-line pointer. Include:
   - What you did (files/commits/PRs touched)
   - Why ownership is transferring now (what condition was met)
   - What the recipient must do next
   - Any blocking risks, open questions, or constraints they need to know
3. **Wait for and surface the result.** Report the recipient's outcome back to the user in your own final reply; do not go silent after delegating.

If you are running as a manually-selected chat mode (not delegated to via the `agent`/`task` tool by another agent), no runtime automatically switches the active agent for the user. In that case, state the handoff recommendation clearly in your reply and tell the user which agent to switch to.

## Model Allocation Policy

The `model:` field in each agent's frontmatter is a prioritized fallback list — VS Code tries each entry in order and only advances to the next if the prior one is unavailable, not based on remaining budget. This means the **first** model listed is what actually runs almost every time, so it drives the cost.

When invoking a configured custom agent, **never pass a model or reasoning-effort override**. Select the agent by role and let its frontmatter control model allocation. Prefer a matching custom agent over a built-in agent; if no custom agent matches, use the built-in agent without an explicit model override. Treat an accidental override as a routing error: stop relying on that delegated result and relaunch the work with the correct agent configuration.

Current allocation deliberately avoids `Claude Sonnet 5` as any agent's primary model, because that model was already running far over its included-usage allotment (see the credits/usage report). Instead, each agent's primary model targets a specific, currently underused included pool:

| Agent | Primary model | Why |
|---|---|---|
| Architect | Claude Opus 5 | Needs the strongest reasoning (spec validation, ADRs, production troubleshooting); Opus had large unused included headroom and no overage. |
| Product | GPT-5.4 mini | Spec writing is a light task; this pool was almost entirely idle. |
| Implementation | GPT-5.3-Codex | Coding-specialized model; had a large unused included pool with negligible overage. |
| Test | MAI-Code-1.1-Flash | Test writing is code-adjacent; this pool had by far the largest unused included allotment. |
| Reviewer | MAI-Code-1.1-Flash | Same rationale as Test — review is read-heavy, not reasoning-heavy. |
| DevOps | GPT-5.3-Codex | Infra-as-code and CI/CD authoring fit a coding-specialized model. |

`Claude Sonnet 5` remains only as Architect's last-resort fallback (after Opus 5 and GPT-5.3-Codex), and `Claude Haiku 4.5` remains a fallback for Product, Implementation, and Test — neither is a primary anywhere, so routine usage should no longer add to their overage.

This allocation cannot control every source of cost: the automatic GitHub PR-review bot (`Code Review model` in the usage report) is a separate platform feature, not one of these custom agents, and ad hoc chat sessions where a model is picked manually (including `Auto` mode) bypass this file entirely. If the exact model display name below does not match what VS Code's model picker currently exposes, the array falls through to the next entry rather than failing outright — but re-verify these strings periodically against `Chat: Open Customizations` in VS Code, since model names get renamed/retired over time.
