# Physical Pallet Weight Two-Decimal Precision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve physical pallet weights to two decimal places so `10.35` is saved and displayed as `10.35`, while keeping the existing optional autosave workflow and 100 kg maximum.

**Architecture:** Replace the feature branch's integer-tenths persistence with integer hundredths. M007 creates the final hundredths schema for databases that have not received this unshipped feature; M008 deterministically upgrades developer databases that already recorded the earlier M007 by multiplying every valid stored tenth by ten. Backend parsing remains authoritative, the browser parser mirrors it, and roll-weight presentation outside the physical-pallet-derived columns remains unchanged.

**Tech Stack:** Python 3, FastAPI, direct `sqlite3`, pytest, vanilla JavaScript ES modules, Node test runner, repository-local Playwright.

**Spec:** `docs/superpowers/specs/2026-09-09-physical-pallet-weight-design.md`

## Global Constraints

- Preserve blank-as-clear, `.`/`,` separators, positive values only, and the inclusive `100.00 kg` maximum.
- Accept integers, one decimal, or two decimals; normalize saved pallet weights to exactly two displayed decimals. Reject more than two fractional digits rather than silently accepting an unbounded-precision typo.
- Store exact integer hundredths; do not use binary floating-point for parsing or persistence.
- Existing valid M007 values migrate exactly with `weight_hundredths = weight_tenths * 10`, preserving card, pallet, and timestamp fields.
- Keep optimistic concurrency, immediate autosave, completion validation, and all non-pallet roll-weight behavior unchanged.
- Use temporary databases for tests and browser verification. Do not mutate the runtime database during verification.
- Do not stage or commit without explicit user authorization.

---

### Task 1: Two-decimal parser, persistence, and presentation contract

**Files:**
- Modify: `tests/test_physical_pallet_weights.py`
- Modify: `tests/js/pallet_weight_autosave_core.test.mjs`
- Modify: `tests/test_terminal_pallet_summary.py`
- Modify: `app/pallet_summary.py`
- Modify: `app/static/js/pallet_weight_autosave_core.mjs`
- Modify: `app/db.py`

**Interfaces:**
- Produces: `parse_physical_pallet_weight(raw, pallet_number) -> (weight_hundredths | None, error | None)`
- Produces: `parsePalletWeightDraft(rawValue) -> {kind: "valid", hundredths: number}` for valid values.
- Produces: two-decimal `pallet_weight_display`, `pallet_weight_input`, and pallet-inclusive gross displays.

- [x] Write failing literal tests proving `10.35 -> 1035 -> "10.35"`, `12.5 -> 1250 -> "12.50"`, `100 -> 10000 -> "100.00"`, and `0.01 -> 1 -> "0.01"` in Python, route JSON, shared summary, and JavaScript.
- [x] Run the focused Python and Node tests and verify that they fail against integer-tenths behavior.
- [x] Change the pure parsers and persistence query names from tenths to hundredths. Format the physical pallet and gross-with-pallet values with two decimals; retain the existing one-decimal formatting of gross-without-pallet and net values.
- [x] Run the focused parser, route, summary, and Node tests and verify they pass.

### Task 2: Deterministic SQLite precision migration

**Files:**
- Modify: `tests/test_migrations.py`
- Modify: `app/schema.py`
- Modify: `app/migrations.py`
- Modify: direct test/fixture SQL and audit scripts that consume the column contract.

**Interfaces:**
- Produces: final `card_pallet_weights.weight_hundredths INTEGER CHECK 1..10000` schema.
- Produces: M008 `physical_pallet_weight_hundredths` compatibility migration for databases with the earlier M007 tenths table.

- [x] Write failing migration tests for the final schema and exact `125 -> 1250` conversion with timestamps preserved; retain the existing malformed-schema, rollback, idempotence, integrity, and foreign-key safeguards.
- [x] Run the focused migration tests and verify failures are caused by the missing hundredths schema/M008.
- [x] Make M007 create the final schema for fresh/unreleased installs. Implement M008 to no-op on the exact final schema or rebuild the exact legacy M007 schema and multiply stored values by ten; reject every other table shape atomically.
- [x] Update direct SQL fixtures and internal names to the final column contract, then run migration and affected workflow tests.

### Task 3: Contract documentation and verification

**Files:**
- Modify: `docs/superpowers/specs/2026-09-09-physical-pallet-weight-design.md`
- Modify: `docs/implementation-notes/physical-pallet-weight.md`
- Modify: relevant browser verifier expectations under `scripts/`.

**Interfaces:**
- Produces: durable documentation of the exact two-decimal contract and migration assessment.

- [x] Replace the superseded integer-tenths/one-decimal physical-pallet rules with integer-hundredths/two-decimal rules, while explicitly leaving roll-weight formatting unchanged.
- [x] Verify `10.35` through the live autosave UI against a temporary database and capture one screenshot under `artifacts/ui-checks/physical-pallet-weight-two-decimal/`.
- [x] Run syntax/import checks, focused tests, the full Python and Node suites, `git diff --check`, SQLite integrity checks, and inspect the bounded diff.
