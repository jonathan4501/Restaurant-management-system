# Agent brief — read this before touching the repository

You are one of several AI coding agents building RENZY. Each agent owns one workstream (`WS-NN.md` in
this folder). This brief is the contract between you, the other agents, and the person who reviews
your pull request.

## Reading order

1. `/CLAUDE.md` — binding rules and scope boundaries. Ten minutes. Non-negotiable.
2. Your `docs/tasks/WSNN-*.md` — goal, owned paths, exit criteria.
3. `docs/07-backend-architecture.md` and `docs/08-api-contract.md` — the interfaces you build on and expose.
4. `docs/03-data-model.md` — only the tables your workstream touches.
5. `docs/decisions/` — read an ADR before changing anything it decided.

You do not need `01`, `02`, `04`, `05` to start. Read them if you want the why.

## Rules of engagement

- **Branch** `ws/NN-name` from `main`. One workstream, one branch, one PR. Rebase on `main` before
  opening the PR.
- **Stay inside your owned paths.** If you need a change elsewhere (a new field in `core`, an event in
  `orders/events.py`), write it in the PR description under "Requests to other workstreams" and, if you
  are blocked, implement it behind a clearly named function in your own app and note the duplication.
  Do not edit another workstream's files.
- **Every write goes through the command runner** (`apps/core/commands.py::run_command`). No view writes
  a projection table. No `Model.save()` on `orders`, `order_items`, `table_sessions`, `shifts`,
  `payments` outside a projector. No `delete()` anywhere except tests.
- **Money is `int` pesewas.** If you write `float`, `Decimal` or `/ 100` outside `formatPesewas` and
  the one rounding helper in `totals.py`, you have a bug.
- **Every `POST` needs `Idempotency-Key`.** Use `CommandView`; it handles it. Tests use the
  `command_client` fixture which sets one per call.
- **Tenant scope is automatic.** Never call `.unscoped()` outside migrations, `rebuild_projections` and
  the allow-list in `apps/core/tests/test_invariants.py`.
- **Timestamps come from the server.** Store the client's clock in `client_created_at`; never sort by it.
- **Nothing is hard-deleted.** `is_active`, `revoked_at`, `voided_at`.
- **Tests before done.** Every state transition and every money calculation has one. Run `make check`
  (or `docker compose -f infra/compose.dev.yml exec api make check`) before every commit.
- **Commits**: conventional, tagged with the workstream: `feat(ws05): settle session when balance is zero`.
- **Dependencies**: adding one requires a one-line justification in the PR. Prefer what is already in
  `pyproject.toml` / `package.json`.
- **OpenAPI**: if you add or change an endpoint, run `make openapi` and `make types` and commit both
  outputs. CI fails on drift.
- **Prototype**: `docs/prototype/renzy-demo.html` is visual reference only. It predates ADR-0005 and
  ADR-0001: it computes tax lines, logs a fake GRA event, and hard-deletes voided orders. Copy the look,
  never the logic.
- **Labels**: the owner's gross figure is "Money taken" or "Total collected". Never "Revenue", never "Profit".
- **Scope**: if your task seems to need tax, a payment gateway, inventory, delivery or a native app —
  stop and write the question in your PR. Do not build it.

## What "done" means

- Every exit criterion in your task file is met and demonstrated by a test or a documented manual step.
- `make check` is green. No new `# type: ignore` in money or state-transition code.
- The PR description has: what was built, how to verify it, requests to other workstreams, anything
  you deliberately left out and why.

## When you are unsure

Prefer the interpretation that a careful engineer at a restaurant would choose, write down the
assumption in the PR, and keep going. Ask only when the readings would produce materially different
code — then ask in the PR, and build the rest.
