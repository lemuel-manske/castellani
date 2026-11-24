# Contributing

This document defines the workflow for making changes to Castellani.

These rules are mandatory for every task, regardless of language or service. Follow them alongside the repository's engineering and testing conventions.

## 1. Start from `main`

- Begin every new task on a **fresh branch created from the current `main`**. Fetch or otherwise verify the latest remote `main` before branching; do not branch from an existing feature branch or reuse a previous task branch.
- Use a short, descriptive branch name (for example, `feat/coordinator-admission` or `fix/gateway-shutdown`).
- Keep unrelated changes out of the task branch. Never commit directly to `main`.
- If the working tree contains pre-existing changes, preserve them; do not discard, overwrite, or include them without permission. Resolve any conflict with the fresh-branch requirement before editing.

## 2. Understand the project before changing it

- Read the relevant [ADRs](docs/adr/README.md) and [testing conventions](docs/testing.md) **before writing or modifying code**.
- Read the applicable contracts, including [OpenAPI](contracts/openapi/api.yaml) and [message contracts](contracts/README.md), as appropriate to the task.
- Inspect the affected implementation and its tests. Reuse established patterns where they fit; do not assume existing behavior or infer requirements from filenames alone.
- Treat accepted ADRs and specifications as authoritative. If a requested change conflicts with them, explain the conflict and obtain approval before proceeding.

## 3. Plan and execute in reviewable steps

1. Before implementation, break the task into **no more than 10 ordered steps**. Each step must have a concrete outcome that the user can review. Prefer fewer steps for small changes; a task may consist of one step.
2. Share the proposed plan with the user **and obtain explicit approval before starting the first implementation step**.
3. Implement **only the currently approved step**. Keep its scope narrow; do not silently start the next step or bundle future work into it.
4. **Refactor before declaring a step complete.** Review all code touched by the step for duplicated logic, unclear or crossed boundaries, misplaced public/shared functionality, unnecessary wrappers, inconsistent APIs and names, and package/module organization. Consolidate genuinely reusable code at the correct ownership boundary without introducing speculative abstractions. Check that tests exercise the behavior through the intended public API. Resolve issues discovered within the approved scope before proceeding; raise architectural changes beyond that scope for review.
5. Run the relevant formatter, tests, static checks, and integration checks after this refactoring pass. If refactoring reveals a regression, fix it before ending the step.
6. At the end of **every step**, report what changed, the relevant files, verification performed and its results, the refactoring review (duplication, boundaries, and package/module layout), and any open questions or deviations. Provide a commit reference or diff when available.
7. **Stop and return control to the user for review.** Continue to the next step **only after explicit user approval**. Silence, lack of objections, or a previous approval does not authorize later steps.
8. If new discoveries materially change the plan, present a revised plan (still at most 10 steps) and get approval before following it.

For documentation-only changes, a single reviewable step is usually sufficient. Do not invent extra steps to reach a quota.

## 4. Make semantic commits

- Use **Conventional Commits** for every commit: `<type>(<optional-scope>): <imperative summary>`.
- Common types: `feat`, `fix`, `docs`, `test`, `refactor`, `build`, `ci`, and `chore`. Use `!` or a `BREAKING CHANGE:` footer for breaking changes.
- Make commits cohesive and appropriately scoped to the approved step. Do not mix unrelated modifications or use vague subjects such as `updates` or `fix stuff`.
- Prefer committing each completed step separately so the user can inspect its exact changes. Do not amend or rewrite previously reviewed commits without approval.

## 5. Verify and hand off

- Follow [testing conventions](docs/testing.md): favor readable behavioral tests, meaningful integration coverage, deterministic synchronization, and reusable focused fixtures.
- Run the relevant formatters, tests, and checks exposed by the affected service's `Makefile`, plus any checks required by the change. Report failures and anything that could not be run; never claim unperformed checks passed.
- Keep documentation aligned with the authoritative ADRs, specifications, and conventions; do not duplicate design details in service READMEs.
- At each review checkpoint, summarize the step's result and **explicitly request approval** before proceeding.
- Do not merge, open a pull request, or perform unrelated cleanup unless the user has authorized that action. Completing the final step does not imply permission to merge.
