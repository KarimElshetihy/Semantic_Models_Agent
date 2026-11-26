# Phase 0 Design (Draft)

**Status:** DRAFT. Nothing in this document is implemented yet.
**Scope:** Phase 0 foundation from `requirements.md` section 12. Offline only: no LLM calls, no SSAS connection, no Oracle connection, no writes to `example_models/`.

## 1. Goal and exit gate

Build the deterministic core that every later phase depends on:

1. Byte-faithful load and save of `Model.bim`.
2. Read-only inventory of tables, columns, measures, partitions, relationships, roles and data sources.
3. Semantic diff keyed by object identity.
4. A persisted approval state machine with enforcement.
5. Audit records and a write policy that denies by default.

Exit gate (from the spec): round-trip preservation and approval enforcement tests pass on sanitized fixtures.

## 2. Evidence from the example projects

Facts checked against the four Visual Studio 2019 projects in `example_models/`. Reproduce with `python tools/inspect_bim_examples.py`. The same command accepts a folder argument, for example `tests/fixtures`.

| Project | Tables | Columns (calculated) | Measures | Relationships | Roles | Notes |
|---|---|---|---|---|---|---|
| EOPM_MODEL | 17 | 150 (2) | 0 | 18 | 0 | No git |
| EF_MOF_GOV_PAY | 28 | 351 (20) | 10 | 65 | 0 | Empty calculated column `Add Column2` in `EPAY`; 2 bidirectional relationships |
| MOF_MODEL | 19 | 187 (7) | 32 | 23 | 6 | 7 bidirectional relationships around `RLS_*` tables; `Config.json.template` |
| RETA_MODEL | 8 | 111 (2) | 4 | 9 | 0 | Deployment set to `DoNotProcess` |

Structural facts that shape the design:

- **Round-trip works with plain JSON.** `json.dumps(indent=2, ensure_ascii=False)` with `\n` replaced by `\r\n` and no trailing newline reproduces all four `Model.bim` files byte for byte. No BOM in any file.
- **No `lineageTag` anywhere.** Object identity must come from names. Table names are unique in every model. Relationships have unique `name` values in every model.
- **Expressions have two storage forms.** Measures and column expressions are either a string or a list of lines. List items never contain embedded line breaks. Writes must keep the original form to keep diffs small.
- **Power Query (M) everywhere.** 73 M partitions: 69 native-query-only, 1 native query plus steps, 3 other. All sources are Oracle (`Oracle/dwhdbhq-scan:1521/dwhdb_srv`).
- **No password is stored.** Each data source records an authentication kind (`UsernamePassword`) and an Oracle account name. The account name and server string are replaced in fixtures.
- **Findings to report, not fix:**
  - `Add Column2` in `EF_MOF_GOV_PAY` is a calculated column with no expression.
  - `DIM_DATE` partitions in three projects call `DateTime.LocalNow`, so their output changes over time.
  - Role name typo `Minstries` in `MOF_MODEL`. Renaming breaks clients, so it stays.

## 3. Decisions already made

| Decision | Source |
|---|---|
| Example projects stay local and out of version control; sanitized copies go in `tests/fixtures/` | User, 26 Nov 2026 |
| Target is SSAS 2019, compatibility level 1500 | User |
| Oracle is the only source for now | User |
| Fixtures keep table and column names; server, service and account names are replaced | User, 26 Nov 2026 |
| `example_models/` is git-ignored | User, 26 Nov 2026 |
| `Config.json.template` is used by the company CI/CD pipeline; deferred until the CI/CD phase | User, 26 Nov 2026 |

## 4. Proposed layout

Only the Phase 0 modules are listed. Later modules from the spec's suggested structure are not created yet.

```text
Semantic-Model-Agent/
  .gitignore                   # done
  docs/
    PHASE0_DESIGN.md
  example_models/              # local only, git-ignored
  tests/
    fixtures/                  # done: sanitized Model.bim copies of the four projects
    unit/
  tools/                       # done: repository scripts, not part of the agent
    bim_format.py              # shared Model.bim reading and serialization helpers
    inspect_bim_examples.py    # read-only structure and round-trip report
    scan_sensitive_strings.py  # read-only scan for values that must not be shared
    sanitize_fixtures.py       # builds and verifies tests/fixtures from example_models
  src/
    ssas_agent/
      bim/                     # load, serialize, expression form handling
      inventory/               # read-only object listing and summary
      diff/                    # semantic diff by identity
      approval/                # state machine and SQLite persistence
      audit/                   # run records and artifact hashes
      policy/                  # path and operation allowlist, deny by default
  workspaces/                  # isolated candidates, gitignored
  artifacts/                   # diffs, transition logs, reports, gitignored
```

Dependencies: Python standard library and `pytest` only. `pydantic` is deferred to Phase 1 for typed tool inputs. `sqlglot` and an Oracle driver are deferred to Phase 1 and Phase 2 respectively.

## 5. BIM document design

**Canonical representation: the raw JSON dictionary.** Typed views are built on top for inventory and diffs. Typed models (for example, pydantic) would drop properties they do not know about, which breaks round-trip preservation for future Visual Studio and TOM versions.

Load:

1. Read bytes. Record SHA-256 of the raw bytes. Record BOM presence and line-ending style.
2. Decode as UTF-8 and parse JSON.

Save:

1. Serialize with 2-space indent, `ensure_ascii=False`, CRLF, no trailing newline.
2. Before any edit is allowed, serialize the unmodified document and compare with the original bytes.
3. If they differ, **refuse edits for that file** and report why. Fail closed rather than rewrite a file the tool cannot reproduce.
4. Write atomically: temporary file in the same directory, flush, then `os.replace`.

Expressions:

- Keep the original form (string or list). When an edit produces a new expression, split it into lines only if the original was a list.
- M partitions are opaque text in Phase 0. The M expression is inventoried and hashed but never edited.
- Oracle SQL inside `Value.NativeQuery` is extracted for inventory only. Parsing and dialect handling belong to the Oracle adapter in Phase 1.

## 6. Inventory

Read-only. One record per object, keyed by identity:

| Object | Identity |
|---|---|
| Table | `table:{name}` |
| Column | `column:{table}/{name}` |
| Measure | `measure:{table}/{name}` |
| Partition | `partition:{table}/{name}` |
| Relationship | `relationship:{name}` |
| Role | `role:{name}` |
| Role table permission | `role-permission:{role}/{table}` |
| Data source | `datasource:{name}` |

Each record holds the object's property dictionary, its expression hash where present, and any findings from the rule list in section 2.

## 7. Semantic diff

- Compare two inventories by identity. Output: added, removed, changed.
- For changed objects, report the changed property names. Compare expressions after joining lines, so a change of storage form alone is reported separately as `expression form changed`.
- Renames appear as remove plus add. Rename detection is out of scope until a stable identity exists.
- Also produce a text diff of the serialized files for review artifacts (`difflib`).

## 8. Approval state machine

States: `DRAFT`, `PROPOSED`, `REVISION_REQUESTED`, `APPROVED`, `APPLIED`, `VERIFIED`, `FAILED`, `REJECTED`, `CANCELLED`.

Transitions:

| From | To | Trigger |
|---|---|---|
| DRAFT | PROPOSED | submit |
| PROPOSED | APPROVED | approve (binds hashes, see below) |
| PROPOSED | REVISION_REQUESTED | request revision |
| REVISION_REQUESTED | DRAFT | revise |
| PROPOSED | REJECTED | reject (terminal) |
| APPROVED | DRAFT | edit after approval (invalidates approval) |
| APPROVED | APPLIED | apply (checks below) |
| APPLIED | VERIFIED | verification passes |
| APPLIED | FAILED | verification fails |
| DRAFT, PROPOSED, REVISION_REQUESTED, APPROVED | CANCELLED | cancel |

Cancel is not allowed from APPLIED. A change that has been written must end as VERIFIED or FAILED, so the recorded state always matches the file on disk. This narrows the design's "any non-terminal" rule on purpose.

Terminal states: VERIFIED, FAILED, REJECTED, CANCELLED.

Every refused operation is recorded in an `attempts` table with the action, actor and reason, and then raised. Invalid transitions are checked before anything else, so a refused approve from DRAFT is an invalid transition, not a missing proposal.

An approval binds to:

- run ID
- proposal ID
- base file SHA-256 (the target before the change)
- candidate file SHA-256 (the target after the change)
- target path
- operation summary hash

Apply is allowed only when the state is `APPROVED`, the approved path is still the resolved target, the candidate file hashes to the approved candidate hash, and the current target hash is either the base hash (write) or the candidate hash (already in place). Any other combination raises `StaleApprovalError` and records the attempt. The policy is checked before any write.

Apply outcomes: `WRITTEN`, `ALREADY_IN_PLACE` (resume after a crash between write and record, so nothing is written again), and `ALREADY_APPLIED` (a second apply on an applied run).

Persistence: SQLite in `artifacts/state/workflow.sqlite3`. One row per transition with run ID, from-state, to-state, action, actor, timestamp, the canonical JSON payload, and its SHA-256. The current state is derived from the last transition, so the log is the source of truth. `verify_integrity` recomputes each payload hash to detect tampering.

Known limits in Phase 0: no concurrency control between two processes writing the same run, and no authentication of actors. Both belong to later phases.

## 9. Policy

Deny by default. Every decision returns allow or deny with a reason, and the reason is written to the audit log.

- **Read:** `example_models/`, `tests/fixtures/`, `workspaces/`, `artifacts/`.
- **Write:** `workspaces/` (candidate changes) and `artifacts/` (audit output only). Never `example_models/` and never `tests/fixtures/`. The second write folder was added so audit output can be written under the same rules.
- Relative paths resolve against the project root, not the current directory. Paths are resolved with `Path.resolve()` (so `..` and symlinks are followed) and checked with `is_relative_to`. Lookalike folders such as `workspaces_evil/` do not match.
- Unknown operations are denied.
- Phase 0 has no write path to a real project. Phase 1 adds approved local application, and that path must call the policy before any write.

## 10. Audit

Per run, under `artifacts/{run_id}/`:

- `run.json`: run ID, input SHA-256, candidate SHA-256 (added by the approval layer)
- `diff.json`: semantic diff (added in the approval layer)
- `diff.txt`: serialized text diff
- `events.jsonl`: append-only event log, one JSON object per line, UTC timestamps
- transition log (JSON, mirrors SQLite; added with the approval layer)

Rules:

- Run IDs are `YYYYMMDDTHHMMSSZ-xxxxxxxx`. A run ID must match `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`, so it can never contain path characters.
- Artifact file names must be plain names. Nested paths are rejected.
- Every write goes through the path policy and an atomic replace.
- Credential values are redacted from every written text and event: JSON `"Username"`, `"Password"` and `"pwd"` properties, and connection-string `Password=`, `Pwd=`, `User ID=`, `UID=` pairs.

## 11. Test plan

Tests are offline and use sanitized fixtures. Status vocabulary per spec: PASS, FAIL, NOT_RUN. All are NOT_RUN until implemented.

| Test | Covers | Status |
|---|---|---|
| `test_fixture_round_trips_byte_for_byte` (4 fixtures) | Round-trip preservation (EXT-01, AC-10) | PASS |
| `test_save_without_edit_keeps_bytes_identical` (4 fixtures) | Unedited save changes no bytes | PASS |
| `test_lf_line_endings_refuse_edit`, `test_bom_file_refuses_edit`, `test_trailing_newline_refuses_edit` | Fail-closed behavior (section 5) | PASS |
| `test_lf_file_save_is_refused_and_leaves_file_unchanged` | Refused save leaves the file untouched | PASS |
| `test_unknown_property_survives_edit_and_save` | Preservation of unrelated metadata | PASS |
| `test_edit_changes_only_the_edited_value` | Exact diff of a single edit | PASS |
| `test_failed_replace_keeps_original_and_removes_temp` | Atomic write | PASS |
| `test_headline_counts_match_design_document`, `test_every_object_type_matches_raw_json_counts` (4 fixtures) | Inventory against section 2 and against raw JSON counts | PASS |
| `test_m_partition_shapes_match_design_document`, `test_empty_calculated_column_is_reported_in_historical_model`, `test_local_now_partitions_are_reported` | Derived facts and findings | PASS |
| `test_credentials_are_not_inventoried`, `test_role_members_are_counted_not_copied`, `test_expression_text_is_not_stored_in_the_inventory` | Sensitive values kept out of the inventory | PASS |
| `test_expression_hash_is_the_same_for_string_and_list_forms`, `test_duplicate_table_names_are_rejected` | Stable hashes; fail-closed identity rules | PASS |
| `test_measure_expression_edit_is_the_only_change`, `test_new_column_is_added`, `test_removed_relationship_is_reported` | Exact diff reports only the changed object (EXT-01) | PASS |
| `test_changed_property_is_reported_by_name`, `test_expression_storage_form_change_is_a_note_not_an_expression_change` | Property names and storage-form notes | PASS |
| `test_renamed_table_appears_as_removed_and_added`, `test_credential_change_alone_is_not_a_model_change`, `test_role_member_count_change_is_reported_as_fact` | Renames, credentials and members | PASS |
| `test_unified_text_diff` tests in `tests/unit/test_text_diff.py` | Review text diff | PASS |
| `test_apply_refused_when_candidate_changed_after_approval`, `test_apply_refused_when_target_changed_after_approval` (`test_approval_workflow.py`) | Stale approvals refused (AC-06) | PASS |
| `test_edit_after_approval_invalidates_it`, `test_apply_is_refused_before_approval_and_leaves_target_unchanged` | Approval enforcement (AC-06) | PASS |
| `test_resume_after_crash_between_write_and_record_does_not_rewrite`, `test_second_apply_is_idempotent` | Resume without duplicate writes (AC-07) | PASS |
| `test_only_listed_transitions_are_legal` (every state × action pair) | Legal transitions only | PASS |
| `test_stored_payloads_pass_integrity_check`, `test_tampered_payload_fails_integrity_check` | Audit log tamper detection | PASS |
| `test_state_survives_a_new_store_and_workflow` | Persisted state across restarts | PASS |
| `test_write_to_protected_folders_is_denied_with_reason`, `test_write_outside_allowed_folders_is_denied_by_default`, `test_read_outside_allowed_folders_is_denied_by_default` | Deny by default, protected folders (AC-06) | PASS |
| `test_parent_folder_traversal_into_protected_area_is_denied`, `test_traversal_out_of_project_is_denied`, `test_lookalike_folder_name_is_not_a_match`, `test_unknown_operation_is_denied` | Traversal, lookalike names, unknown operations | PASS |
| `test_symlink_inside_workspaces_pointing_to_protected_folder_is_denied` | Symlink escape | SKIPPED: this Windows account cannot create symlinks |
| `test_recorder_refuses_artifacts_root_inside_protected_folder`, `test_unsafe_run_ids_are_rejected` | Audit writes go through the policy; run IDs cannot escape | PASS |
| `test_credentials_are_redacted_in_text_artifacts`, `test_credentials_are_redacted_in_events`, `test_redaction_patterns` | Redaction | PASS |
| `test_artifact_names_must_be_plain_file_names`, `test_write_leaves_no_temporary_files` | Artifact names and atomic writes | PASS |

Mocked tests are labeled as mocked. No test in Phase 0 claims SSAS or Oracle validation.

## 12. Sanitized fixtures (done)

`python tools/sanitize_fixtures.py` builds `tests/fixtures/{project}/Model.bim` for each of the four projects.

- Only `Model.bim` is copied. Layout files, build output, IDE state, `.smproj` files and nested `.git` folders are left behind. The `.smproj` files hold deployment servers and database names, so they stay out of the fixtures.
- Replaced in the raw text, so all other bytes are preserved:
  - Oracle server string `dwhdbhq-scan:1521/dwhdb_srv` becomes `oracle-host:1521/oracle_service`.
  - Oracle account name becomes `oracle_user`.
- Kept: table, column, measure and relationship names, and the Oracle SQL. These are needed for realistic tests. The files contain no data values.
- The script fails if a fixture is invalid JSON, no longer round-trips byte for byte, or still contains a replaced value.
- Verified: each fixture has the same object counts as its original, round-trips byte for byte, and `python tools/scan_sensitive_strings.py tests/fixtures` finds no host, address, email, URL or path values.

Not verified: that the Oracle SQL and Arabic labels in the kept names are free of business-confidential content. That is a content review, not something a script can decide.

## 13. Open items

1. **Fixture content review. In progress.** Names and SQL are kept as decided. Someone who knows the business should confirm that nothing in the kept SQL or labels is confidential before fixtures are shared outside the team.
2. **Git repository initialized** on 26 Nov 2026 at the user's request. No commit yet. `example_models/`, `.env`, `workspaces/`, `artifacts/` and Python cache folders are ignored and do not appear in `git status`.
2a. **Dependency graph interfaces moved to Phase 2** by user decision, 26 Nov 2026. `requirements.md` section 12 still lists them under Phase 0. That file is not edited until the user approves.
3. **`Config.json.template`** in `MOF_MODEL` is used by the company CI/CD pipeline. Deferred: ignored in Phase 0, to be studied in the CI/CD phase (Phase 4, ENG-13).
4. **Findings are reported, not fixed:** the empty calculated column, the `DateTime.LocalNow` partitions, and the role name typo.
5. **Phase 1 prerequisites:** Oracle SQL dialect handling and an Oracle driver are needed before SQL generation or validation.

## 14. Build order

1. Sanitized fixtures and `.gitignore` entries. **Done.**
2. `bim/` load, serialize, and round-trip gate, with the round-trip tests. **Done:** 25 tests in `tests/unit/test_bim_round_trip.py` and `tests/unit/test_atomic_write.py` pass. Run with `python -m pytest`.
3. `inventory/` and its count test. **Done:** 52 tests pass in `tests/unit/` (bim, atomic write, inventory). Run with `python -m pytest`. Credentials and role members are excluded. Expression text is stored as a SHA-256 hash only.
4. `diff/` and its diff test. **Done:** 63 tests pass in `tests/unit/`. Diff compares by identity, lists changed property names, reports storage-form changes as notes, and does not detect renames.
5. `policy/` and `audit/`. **Done:** 109 tests pass, 1 skipped (symlink test, see section 11). Policy is deny-by-default. Audit writes go through the policy, use atomic writes, and redact credentials.
6. `approval/` state machine and its enforcement tests. **Done:** 249 tests pass, 1 skipped (symlink). Apply re-checks the approval against the files on disk and goes through the policy before any write. Refusals are recorded as attempts.
7. Phase 0 report: **Done.** See `docs/PHASE0_REPORT.md`. 249 PASS, 1 NOT_RUN (symlink), 0 FAIL. The dependency graph interface is deferred to Phase 2 (section 13, item 2a).

Stop at the Phase 0 review boundary before starting Phase 1.
