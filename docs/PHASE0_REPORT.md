# Phase 0 Report

**Date:** 26 November 2026
**Scope:** Phase 0 (Foundation) from `requirements.md` section 12, plus the exit gate.
**Status:** Ready for review. Phase 1 has not started, as required by `requirements.md` section 13 item 3.

## 1. Exit gate

| Gate (requirements section 12) | Result | Evidence |
|---|---|---|
| Round-trip preservation tests pass | **PASS** | 22 tests in `tests/unit/test_bim_round_trip.py`, including byte-for-byte round-trip of all four sanitized fixtures |
| Approval enforcement tests pass | **PASS** | 118 state tests and 22 workflow tests in `tests/unit/test_approval_*.py` |

The gate is met on sanitized fixtures. The original example projects were checked separately with `tools/inspect_bim_examples.py`, which reports byte-identical round-trip for all four. That is a manual check, not a test, and it is not part of the suite.

## 2. Test results

Command: `python -m pytest -v`

| Result | Count |
|---|---|
| PASS | 249 |
| FAIL | 0 |
| NOT_RUN | 1 (symlink test, environment cannot create symlinks) |
| **Total collected** | **250** |

| Test file | Tests | Covers |
|---|---|---|
| `test_approval_states.py` | 118 | Legal transitions for every state and action pair |
| `test_approval_workflow.py` | 22 | Enforced apply, stale approvals, resume, persistence, tamper detection |
| `test_audit.py` | 27 | Run IDs, redaction, artifact writes, policy integration |
| `test_bim_round_trip.py` | 22 | Round-trip, fail-closed editing, unknown-property preservation |
| `test_atomic_write.py` | 3 | Atomic replace and cleanup on failure |
| `test_inventory.py` | 27 | Counts against design section 2 and raw JSON, findings, credentials excluded |
| `test_policy.py` | 20 | Deny by default, protected folders, traversal, symlink (NOT_RUN) |
| `test_semantic_diff.py` | 9 | Identity-based diff, storage-form notes, renames, credentials |
| `test_text_diff.py` | 2 | Review text diff |

**Mocks:** none of the external services are mocked. All tests use local files and a local SQLite database. Two test-only stubs exist and are labeled here:
- `test_failed_replace_keeps_original_and_removes_temp` replaces `os.replace` to simulate a failed write.
- `test_relative_paths_are_resolved_against_project_root_not_current_directory` changes the working directory.

No test contacts SSAS, Oracle or SQL Server Agent.

**Crash simulation:** the resume test simulates a crash by writing the candidate to the target directly. It does not kill a process. This tests the logic, not the process-level behavior.

## 3. Phase 0 deliverables

| Deliverable (requirements section 12) | Status | Evidence and gaps |
|---|---|---|
| Repository | IMPLEMENTED | Folder structure, `pyproject.toml`, `.gitignore`. Git initialized 26 Nov 2026 (user request). No commit yet. |
| Configuration | IN_PROGRESS | pytest configuration in `pyproject.toml`. No `.env.example` or settings module. |
| Fixtures | IMPLEMENTED | Four sanitized `Model.bim` files in `tests/fixtures/`. Business content review still pending. |
| Structured parser | VERIFIED | `src/ssas_agent/bim/`. Round-trip and fail-closed editing tested. |
| Inventory | VERIFIED | `src/ssas_agent/inventory/`. Eight object types. |
| Approval state machine | VERIFIED | `src/ssas_agent/approval/`. Enforced apply, resume, audit trail. |
| Audit trail | VERIFIED | `src/ssas_agent/audit/` plus the SQLite log in `approval/store.py`. |
| Dependency graph interfaces | DEFERRED to Phase 2 | Listed in section 12 but moved to Phase 2 by user decision, 26 Nov 2026. See section 6. |

## 4. Feature and acceptance status

Status vocabulary per `requirements.md` section 20: PLANNED, IN_PROGRESS, IMPLEMENTED, VERIFIED, DEFERRED.

| ID | Feature | Status | Notes |
|---|---|---|---|
| CORE-02 | Model editing | IN_PROGRESS | Round-trip and unknown-property preservation verified. No typed measure-edit operation yet. |
| CORE-03 | Model understanding | VERIFIED | Eight object types inventoried. |
| CORE-11 | Human-in-the-loop | VERIFIED | State gate enforced in code. No review interface yet. |
| CORE-12 | Change tracking | IN_PROGRESS | Diffs and audit verified. Rollback not built (server rollback is Phase 4). |
| ENG-02 | Dependency analysis | PLANNED | Not built. |
| ENG-03 | Impact analysis | PLANNED | Not built. |
| ENG-06 | Model comparison | IN_PROGRESS | Added, removed, changed and text diff verified. No breaking-change classification. |
| FR-10 | Human approval | VERIFIED | Enforced for apply. Not yet connected to any write into a real project. |
| FR-12 | Audit and versioning | IN_PROGRESS | Transitions, attempts, redacted artifacts verified. Rollback information not yet recorded. |
| CORE-01, CORE-04, CORE-05, CORE-10 | Creation, DAX, SQL, knowledge | DEFERRED | Phase 1. |
| ENG-01, ENG-04 to ENG-05, ENG-07 to ENG-16 | Other engineering features | DEFERRED | Phases 2 to 5. |

Acceptance criteria (requirements section 11):

| ID | Criterion | Status | Notes |
|---|---|---|---|
| AC-02 | Modify one measure, preserve metadata, show exact diff | IN_PROGRESS | Preservation tested at document level. The measure-edit operation is not built. |
| AC-06 | Reject unauthorized writes, stale approvals, out-of-scope paths | **PASS** | Covered by policy, approval and audit tests. |
| AC-07 | Resume without duplicating completed writes | **PASS** | Covered by the resume-after-crash and second-apply tests. Crash is simulated (see section 2). |
| AC-10 | Automated tests cover round-trip, approval, SQL/DAX comparison, failure handling | IN_PROGRESS | Round-trip, approval and failure handling covered. SQL/DAX comparison deferred to Phase 2. |
| AC-01, AC-03, AC-04, AC-05, AC-08, AC-09 | Creation, diagnosis, SQL/DAX reconciliation, job scripts, optimization, SSAS build | DEFERRED | Later phases. AC-09 also needs an SSAS test instance. |

Expanded criteria (requirements section 20):

| ID | Criterion | Status | Notes |
|---|---|---|---|
| EXT-01 | Round-trip preserves metadata; exact and semantic diffs agree | IN_PROGRESS | Both halves are tested, but not as one combined check that they agree. |
| EXT-02 to EXT-12 | Later-phase criteria | DEFERRED or PLANNED | Not in Phase 0 scope. |

## 5. Traceability: requirement to tests

| Requirement | Tests | Result |
|---|---|---|
| Round-trip preservation (EXT-01, AC-10) | `test_fixture_round_trips_byte_for_byte`, `test_save_without_edit_keeps_bytes_identical` | PASS |
| Fail-closed editing | `test_lf_line_endings_refuse_edit`, `test_bom_file_refuses_edit`, `test_trailing_newline_refuses_edit`, `test_lf_file_save_is_refused_and_leaves_file_unchanged` | PASS |
| Unrelated metadata preserved | `test_unknown_property_survives_edit_and_save`, `test_edit_changes_only_the_edited_value` | PASS |
| Atomic writes | `test_failed_replace_keeps_original_and_removes_temp`, `test_write_leaves_no_temporary_files` | PASS |
| Inventory matches design counts | `test_headline_counts_match_design_document`, `test_every_object_type_matches_raw_json_counts` | PASS |
| Findings reported, not fixed | `test_empty_calculated_column_is_reported_in_historical_model`, `test_local_now_partitions_are_reported` | PASS |
| Credentials and role members kept out | `test_credentials_are_not_inventoried`, `test_role_members_are_counted_not_copied`, `test_expression_text_is_not_stored_in_the_inventory` | PASS |
| Semantic diff by identity (EXT-01) | `test_measure_expression_edit_is_the_only_change`, `test_new_column_is_added`, `test_removed_relationship_is_reported` | PASS |
| Storage-form changes are notes | `test_expression_storage_form_change_is_a_note_not_an_expression_change` | PASS |
| Renames not detected (documented limit) | `test_renamed_table_appears_as_removed_and_added` | PASS |
| Deny by default (AC-06) | `test_write_outside_allowed_folders_is_denied_by_default`, `test_read_outside_allowed_folders_is_denied_by_default`, `test_unknown_operation_is_denied` | PASS |
| Protected folders (AC-06) | `test_write_to_protected_folders_is_denied_with_reason`, `test_target_outside_workspaces_is_refused_at_submit` | PASS |
| Traversal and lookalikes (AC-06) | `test_parent_folder_traversal_into_protected_area_is_denied`, `test_traversal_out_of_project_is_denied`, `test_lookalike_folder_name_is_not_a_match` | PASS |
| Symlink escape | `test_symlink_inside_workspaces_pointing_to_protected_folder_is_denied` | NOT_RUN |
| Run IDs cannot escape | `test_unsafe_run_ids_are_rejected`, `test_recorder_rejects_unsafe_run_id_before_creating_anything` | PASS |
| Redaction (artifacts and events) | `test_credentials_are_redacted_in_text_artifacts`, `test_credentials_are_redacted_in_events`, `test_redaction_patterns` | PASS |
| Legal transitions only | `test_only_listed_transitions_are_legal` (every state and action pair), `test_cancel_is_refused_after_apply` | PASS |
| Stale approval refused (AC-06) | `test_apply_refused_when_candidate_changed_after_approval`, `test_apply_refused_when_target_changed_after_approval` | PASS |
| Edit invalidates approval | `test_edit_after_approval_invalidates_it` | PASS |
| Apply requires approval | `test_apply_is_refused_before_approval_and_leaves_target_unchanged`, `test_apply_without_any_approval_record_is_refused` | PASS |
| Resume without duplicate writes (AC-07) | `test_resume_after_crash_between_write_and_record_does_not_rewrite`, `test_second_apply_is_idempotent` | PASS |
| Persistence across restarts | `test_state_survives_a_new_store_and_workflow` | PASS |
| Tamper detection | `test_stored_payloads_pass_integrity_check`, `test_tampered_payload_fails_integrity_check` | PASS |

## 6. Gaps and deviations

1. **Dependency graph interfaces deferred to Phase 2.** Section 12 of `requirements.md` lists them as a Phase 0 deliverable. The user decided on 26 Nov 2026 to build them in Phase 2. `requirements.md` has not been updated yet, so it still shows them under Phase 0 (see section 9).
2. **Symlink protection not verified.** This Windows account cannot create symlinks. The test is written and skipped. It should run on a machine with developer mode enabled.
3. **Cancel is narrower than the spec.** Cancel is not allowed after apply. This is a deliberate change, recorded in `docs/PHASE0_DESIGN.md` section 8.
4. **Policy write folders include `artifacts/`.** The design was updated to allow this so audit output can be written under the same rules.
5. **Inventory covers eight object types only.** The examples contain no hierarchies, perspectives, calculation groups or cultures, so those paths are untested. They are not in the inventory.
6. **Compatibility level is 1500 only.** All examples are SSAS 2019. Other levels are untested.
7. **Layout files are not read.** `Model.bim.layout` files are excluded from the fixtures and never touched. No test checks that they survive a real edit workflow.
8. **No concurrency control and no actor authentication.** Two processes working on the same run are not guarded against. Actors are recorded but not verified. Both belong to later phases.
9. **Renames are not detected.** A renamed object appears as removed plus added. This is documented and tested.
10. **Oracle SQL is not parsed.** Inventory stores a hash of the M expression only. Oracle dialect handling is a Phase 1 requirement.
11. **Requirements assumption needs updating.** `requirements.md` section 3 assumes SQL Server T-SQL sources. The examples use Oracle only. The spec should be updated at the review.

## 7. Findings in the example projects (reported, not fixed)

| Finding | Where | Status |
|---|---|---|
| Calculated column without expression (`Add Column2`) | `EF_MOF_GOV_PAY`, table `EPAY` | Reported by inventory |
| M partition uses `DateTime.LocalNow` | `DIM_DATE` in `EOPM_MODEL`, `MOF_MODEL`, `RETA_MODEL` | Reported by inventory |
| Role name typo `Minstries` | `MOF_MODEL` | Noted in design. Not auto-detected. Renaming would break clients. |
| Bidirectional relationships around row-level security tables | `MOF_MODEL` (7), `EF_MOF_GOV_PAY` (2) | Not flagged by any rule yet. Best-practice rules are Phase 2 (ENG-04). |

## 8. Decisions recorded

| Decision | Source |
|---|---|
| Example projects stay local and are git-ignored; sanitized copies in `tests/fixtures/` | User |
| Fixtures keep table and column names; server, service and account names replaced | User |
| Target is SSAS 2019 (compatibility level 1500) | User |
| Oracle is the only source for now | User |
| `Config.json.template` is used by the company CI/CD pipeline and is deferred to that phase | User |
| Dependency graph interfaces move from Phase 0 to Phase 2 | User, 26 Nov 2026 |
| Initialize git now (no commit yet) | User, 26 Nov 2026 |

## 9. Open items for the review

1. **In progress:** fixture content review. Someone who knows the business must confirm that the kept SQL and labels are not confidential (section 8, `tests/fixtures/`).
2. **Pending:** run the symlink test on a machine with developer mode, to close gap 2.
3. **Pending:** update `requirements.md` for two changes: move dependency graph interfaces from section 12 (Phase 0) to Phase 2, and change section 3 to Oracle-only sources (gap 11). Not edited without your approval.
4. **In progress:** approve Phase 0 before Phase 1 begins. Phase 1 has not started.
5. **Done:** git initialized (no commit yet). Dependency graph decision made (Phase 2).
