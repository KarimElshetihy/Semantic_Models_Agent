# Phase 1 traceability matrix

Maps the requirement IDs in `requirements.md` to the Phase 1 steps in `docs/PHASE1_DESIGN.md` and to the test files
that cover them. Requirements are not changed; this matrix is the comparison the requirements ask for (section 20).

**Status values:** PLANNED, IN_PROGRESS, IMPLEMENTED, VERIFIED, DEFERRED.
**Test values:** PASS, FAIL, NOT_RUN. A mocked test is labelled as mocked and is never counted as a live test.

Mocked tests use a scripted LLM or a fake endpoint. The only test that calls a real endpoint is
`tests/integration/test_llm_live.py`, and it runs only when the settings in `.env` are complete.

## Test status (last full run: 684 passed, 2 not run)

| Test set | Count | Result | Note |
|---|---|---|---|
| Unit tests that pass | 682 | PASS | Mocked or offline. Includes the exit-gate demonstration (15 tests, no LLM call). |
| `tests/integration/test_llm_live.py` | 2 | PASS | Live: a real call to the endpoint in `.env` (local Ollama). Shows connectivity only; no quality claim. |
| Symlink tests (`test_knowledge.py`, `test_policy.py`) | 2 | NOT_RUN | Windows needs an extra privilege to create symlinks on this machine. |
| Failures | 0 | | |

## Requirements to phase 1 steps and tests

| ID | Requirement (short) | Phase 1 step | Status | Tests | Notes |
|---|---|---|---|---|---|
| FR-01 | New model from requirements | 8, 10 | VERIFIED | `tests/unit/test_new_model.py`, `tests/unit/test_exit_gate.py` | Not opened in Visual Studio 2019 yet. That check is the user's. |
| FR-02 | Read, understand, safely modify Model.bim | 1, 2, 9 | VERIFIED | `tests/unit/test_measure_edit.py`, `tests/unit/test_static_checks.py`, `tests/unit/test_delivery.py` | |
| FR-03 | Data modeling proposals (facts, dimensions, keys) | 8a | IN_PROGRESS | `tests/unit/test_m_sources.py` | Source reading is built offline. Proposing facts, dimensions and keys is DEFERRED to Phase 2 (ENG-01). |
| FR-04 | DAX engineering | 7 | VERIFIED | `tests/unit/test_generation_dax.py` (mocked) | With the small local test model the drafts were weak; the static checks and form rules catch the bad ones. |
| FR-05 | SQL engineering (Oracle) | 7 | VERIFIED | `tests/unit/test_generation_sql.py` (mocked) | Text-only rule checks. No SQL is run (Phase 2). |
| FR-06 | Optimization | none | DEFERRED | | Phase 3. |
| FR-07 | Troubleshooting | none | DEFERRED | | Phase 2 to 3. |
| FR-08 | DAX vs SQL result validation | none | DEFERRED | | Phase 2 (AC-04). |
| FR-09 | Refresh job automation | none | DEFERRED | | Phase 4. |
| FR-10 | Human approval before execution | 9 | VERIFIED | `tests/unit/test_approval_workflow.py`, `tests/unit/test_approval_states.py`, `tests/unit/test_delivery.py` | The approver's name is typed, not verified. |
| FR-11 | Knowledge with provenance | 5 | VERIFIED | `tests/unit/test_knowledge.py` | Keyword retrieval only; no embeddings. |
| FR-12 | Audit, versioning, rollback information | 3, 4, 9 | VERIFIED | `tests/unit/test_audit.py`, `tests/unit/test_staging.py`, `tests/unit/test_breaking_changes.py`, `tests/unit/test_delivery.py` | The original model is kept in `workspaces/{run_id}/`. A rollback action is not built (Phase 4). |
| CORE-01 | Model creation | 8 | VERIFIED | `tests/unit/test_new_model.py`, `tests/unit/test_exit_gate.py` | |
| CORE-02 | Model editing with metadata preserved | 1, 9 | VERIFIED | `tests/unit/test_measure_edit.py`, `tests/unit/test_delivery.py` | |
| CORE-03 | Model understanding (inventory, findings) | 0 to 2 | VERIFIED | `tests/unit/test_inventory.py`, `tests/unit/test_static_checks.py`, `tests/unit/test_dax_scanner.py` | |
| CORE-04 | DAX generation | 7 | VERIFIED | `tests/unit/test_generation_dax.py` (mocked) | |
| CORE-05 | SQL generation | 7 | VERIFIED | `tests/unit/test_generation_sql.py` (mocked) | Artifact only; never written to a project. |
| CORE-06 | Performance optimization | none | DEFERRED | | Phase 3. |
| CORE-07 | Troubleshooting | none | DEFERRED | | Phase 2 to 3. |
| CORE-08 | Data validation against the source | none | DEFERRED | | Phase 2. |
| CORE-09 | Refresh automation | none | DEFERRED | | Phase 4. |
| CORE-10 | Knowledge base | 5 | VERIFIED | `tests/unit/test_knowledge.py` | |
| CORE-11 | Human-in-the-loop review | 3, 9 | VERIFIED | `tests/unit/test_approval_workflow.py`, `tests/unit/test_delivery.py` | Approve, reject and revise are in the state machine. |
| CORE-12 | Change tracking: versions, exact diffs, audit | 3, 4 | VERIFIED | `tests/unit/test_staging.py`, `tests/unit/test_breaking_changes.py`, `tests/unit/test_text_diff.py` | Server rollback is Phase 4. |
| AC-01 | Sample schema to candidate model with mapping | 8, 10 | VERIFIED | `tests/unit/test_new_model.py`, `tests/unit/test_exit_gate.py` | |
| AC-02 | Add or change one measure, with exact diff | 1, 4, 9 | VERIFIED | `tests/unit/test_measure_edit.py`, `tests/unit/test_breaking_changes.py`, `tests/unit/test_delivery.py` | |
| AC-03 | Invalid relationship or expression: evidence and fix | 2 | VERIFIED | `tests/unit/test_static_checks.py`, `tests/unit/test_dax_scanner.py` | |
| AC-04 | SQL vs DAX results on an authorized test database | none | DEFERRED | | Phase 2. |
| AC-05 | Refresh-job script, not enabled automatically | none | DEFERRED | | Phase 4. |
| AC-06 | Reject unauthorized writes, stale approvals, out-of-scope targets | 9, 10 | VERIFIED | `tests/unit/test_policy.py`, `tests/unit/test_policy_settings_file.py`, `tests/unit/test_approval_workflow.py`, `tests/unit/test_delivery.py`, `tests/unit/test_exit_gate.py` | |
| AC-07 | Resume a persisted run without repeating writes | 9 | VERIFIED | `tests/unit/test_approval_workflow.py`, `tests/unit/test_delivery.py` | |
| AC-08 | Optimization report: measured versus recommended | none | DEFERRED | | Phase 3. |
| AC-09 | Build or process on a test SSAS instance, or NOT_RUN | 10 | DEFERRED | | Not run: no SSAS instance is used. The demonstration reports this. |
| AC-10 | Automated tests for round-trip, approval, SQL/DAX comparison, failures | 0 to 10 | IN_PROGRESS | `tests/unit/test_bim_round_trip.py`, `tests/unit/test_approval_workflow.py`, `tests/unit/test_delivery.py` | Round-trip and approval are covered. The SQL/DAX comparison is DEFERRED (Phase 2). |
| BIZ-01 | Requirements assistant | 6 | VERIFIED | `tests/unit/test_requirements_assistant.py` (mocked) | Human review is required; drafts were weak with the small local model. |
| ENG-02 | Dependency analysis | none | DEFERRED | | Decision 3: moved to Phase 2. Reports say "dependencies not checked". |
| ENG-03 | Impact analysis | none | DEFERRED | | Decision 3: moved to Phase 2. |
| ENG-06 | Model comparison and breaking-change classes | 4 | VERIFIED | `tests/unit/test_breaking_changes.py`, `tests/unit/test_semantic_diff.py` | |
| EXT-01 | Round-trip keeps metadata; exact and semantic diffs agree | 0 to 1 | VERIFIED | `tests/unit/test_bim_round_trip.py`, `tests/unit/test_semantic_diff.py`, `tests/unit/test_text_diff.py` | |

Features outside Phase 1 (ENG-01, ENG-04, ENG-05, ENG-07 to ENG-16, OPS-01 to OPS-06, BIZ-02 to BIZ-08, and
the Phase 2 to 6 parts of FR and CORE) are DEFERRED to the phase that the requirements assign them to.

## Sample inputs and outputs

- Input: `specs/SAMPLE_SALES.json`, the JSON spec for the new sample model (step 8).
- Input: `tests/fixtures/RETA_MODEL/Model.bim`, the existing model that the safe edit reads (read only).
- Output: `workspaces/{run}-model/SAMPLE_SALES/` (model and project file), `artifacts/{run}-model/mapping.json`.
- Output: `output/Model.bim`, the edited model at the named destination, after your approval.
- Output: `artifacts/{run}/exit_gate_report.md`, the generated exit-gate report.

To run the demonstration in your project root (it writes `output/Model.bim`, so run it once):

    python -m ssas_agent demo --actor YOUR_NAME

Type `approve` when asked. The demonstration refuses to start if `output/Model.bim` already exists.

## Changed-file summary (phase 1, by area)

- Policy and writes: `src/ssas_agent/policy/` (destination folder option, apply target), `src/ssas_agent/staging/` (target model option).
- Approval and apply: `src/ssas_agent/approval/workflow.py` (submitted proposal lookup), `src/ssas_agent/delivery/` (approve, apply, verify, prompts).
- Command line: `src/ssas_agent/cli/main.py`, `src/ssas_agent/__main__.py` (`approve`, `apply`, `demo`).
- New model: `src/ssas_agent/newmodel/`, `specs/SAMPLE_SALES.json`.
- Source reading (offline): `src/ssas_agent/msource/`.
- Generation and LLM: `src/ssas_agent/generation/`, `src/ssas_agent/llm/`, `src/ssas_agent/requirements/`, `src/ssas_agent/knowledge/`.
- Exit gate: `src/ssas_agent/demo/`, `tests/unit/test_exit_gate.py`.
- Tests: one file per area under `tests/unit/`; the live test under `tests/integration/`.

Known limitations are listed in `docs/PHASE1_DESIGN.md` (section 5 and the step rows) and in the generated report.
