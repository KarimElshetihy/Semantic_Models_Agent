# Phase 1 Design (Draft)

**Status:** DRAFT. Steps 1–8 and the LLM client layer (section 3a) are implemented and tested. Steps 9–10 are not written yet.
**Scope:** Phase 1 (AI Engineering Assistant, MVP) from `requirements.md` section 12, plus the features it lists in sections 15 to 20.
**Offline by default:** tests make no LLM calls (the one live test runs only when its environment variables are set), no SSAS connection, no Oracle connection, no writes to `example_models/` or `tests/fixtures/`.
**Spec file:** `requirements.md` is unchanged and is the reference for comparison. Known differences are listed in section 5.

## 1. Goal and exit gate

Exit gate (spec section 12): **demonstrate a new sample model and a safe edit to an existing model.**

Phase 1 deliverables from the spec:

| Deliverable | Features and criteria |
|---|---|
| Model creation and editing | CORE-01, CORE-02, AC-01, AC-02 |
| DAX and SQL generation | CORE-04, CORE-05, FR-04, FR-05 |
| Knowledge retrieval | CORE-10, FR-11 |
| Static checks | CORE-03 (findings), AC-03, FR-02 (validate artifacts) |
| Version comparison | ENG-06, EXT-01 |
| Reviewable diffs | CORE-12, FR-12 |
| Approved local application | CORE-11, FR-10, AC-06, AC-07 |
| Requirements assistant | BIZ-01 (phase 1 part) |
| Dependency and impact | ENG-02, ENG-03 are phase 1–2 in the spec, but see section 4, decision 3 |

## 2. Build steps

Each step has its own tests. A step is done only when its tests pass and the full suite passes.

| Step | What it builds | Depends on decision | Status |
|---|---|---|---|
| 1 | Typed measure edit: replace one measure's expression, or add a measure. Keeps the storage form of the expression and all other metadata. Tests include an end-to-end approved application into `workspaces/`. (AC-02, CORE-02) | none | **DONE:** 18 tests in `tests/unit/test_measure_edit.py`. Full suite: 267 PASS, 1 skipped (symlink). |
| 2 | Static checks on a Model.bim: names, duplicates, relationships, DAX references, empty expressions. Each finding has evidence and a suggested fix. Unreadable DAX is listed as not checked, never passed. (AC-03, CORE-03, FR-02) | none | **DONE:** code in `src/ssas_agent/validation/`, 61 tests (19 in `test_dax_scanner.py`, 42 in `test_static_checks.py`). Full suite: 328 PASS, 1 skipped (symlink). |
| 3 | Staging: copy the base model into `workspaces/{run_id}/Model.bim`, write the candidate to `workspaces/{run_id}/candidate.bim`, write `diff.json`, `diff.txt`, `run.json` and `events.jsonl` to `artifacts/{run_id}/`, then submit the proposal (stops at PROPOSED). Raw models never go into `artifacts/`, because the recorder redacts text and would not redact a model copy. (CORE-12, FR-12) | none | **DONE:** code in `src/ssas_agent/staging/`, 22 tests when built, 24 now with the category tests in `tests/unit/test_staging.py`. |
| 4 | Version comparison with breaking-change classification (ENG-06): semantic diff, a category for each change, and the text diff in one comparison. Staging writes the categories to `diff.json` and `run.json`. | none (rule from section 3 used as proposed) | **DONE:** code in `src/ssas_agent/diff/classify.py` and `compare.py`, 31 tests in `tests/unit/test_breaking_changes.py`, staging updated (24 tests). Full suite: 383 PASS, 1 skipped (symlink). |
| 3a | LLM client layer (section 3a): one client interface, OpenAI-compatible implementation with endpoint policy (local, network https, or network http behind a switch), `.env` reader, redirect refusal, bounded reply and timeout, structured reply check, mock client for tests. | none (server location still open, decision 1a) | **DONE:** code in `src/ssas_agent/llm/`, 92 unit tests, 9 policy tests, plus 1 live test (NOT_RUN unless settings are complete). Full suite: 484 PASS, 2 skipped (live test, symlink). |
| 5 | Knowledge retrieval with provenance: index a `knowledge/` folder of approved standards and examples, return matches with source file and hash. Retrieved text is data, never instructions. (CORE-10, FR-11) | decision 4 (answered: `knowledge/` folder; sample files until your files arrive) | **DONE:** code in `src/ssas_agent/knowledge/`, 21 tests in `tests/unit/test_knowledge.py` (1 symlink test skipped on this machine). Full suite: 507 PASS, 2 skipped. Keyword retrieval only; no embeddings yet. |
| 6 | Requirements assistant: a fixed template of the eight section 4 fields (business objectives, KPIs, data sources, table grain, keys, refresh, security, target SSAS version). Your entries and the model's drafts fill it; model drafts are kept only if every word is in the request. Writes artifacts/{run_id}/spec.md with the sources and a missing-definitions list. (BIZ-01 phase 1 part) | decision 1 (LLM connected) | **DONE:** code in src/ssas_agent/requirements/, 15 tests in tests/unit/test_requirements_assistant.py (mocked model). Full suite: 522 PASS, 2 skipped. A live check with the test model showed weak drafts (for example, keys placed under the wrong field); human review is required. |
| 7 | DAX and SQL generation through a provider-independent interface. DAX: the model proposes one new measure (JSON with table, name, expression); it is checked by the static checks (new errors only, and a measure the scanner cannot read is refused), then staged for approval. SQL: text-only rule checks on an Oracle statement; the result is an artifact, never written to a project. (CORE-04, CORE-05, FR-04, FR-05) | decision 1, decision 2 | **DONE:** code in `src/ssas_agent/generation/`, 36 tests (14 in `tests/unit/test_generation_dax.py`, 22 in `tests/unit/test_generation_sql.py`), mocked model. Full suite: 558 PASS, 2 skipped. Live check with the test model: SQL draft passed the checks; the DAX draft was not valid JSON in 3 attempts, so nothing was staged. After JSON-only replies were added (see decision log), 5 of 5 replies were valid JSON, but the content was weak (`=` in the expression, a name with parentheses). Staging accepted those bad values, so the form rules were added (see decision log). Full suite now: 564 PASS, 2 skipped. |
| 8 | New model creation from a JSON spec you write (section 3b). Builds `Model.bim` and the `.smproj` project file into `workspaces/{run_id}/{project}/`, and a source mapping (KPI to measure) into `artifacts/{run_id}/mapping.json`. Refused specs and refused models write nothing. (CORE-01, AC-01) | decision 5 (answered: JSON spec, format approved 28 Nov 2026) | **DONE:** code in `src/ssas_agent/newmodel/`, 36 tests in `tests/unit/test_new_model.py`. Full suite: 600 PASS, 2 skipped (symlink tests). Not opened in Visual Studio 2019 yet; that check is yours. |
| 8a | Offline M source reader (added 28 Nov 2026, user choice). Reads a Power Query partition's M text and lists the data source name, the Oracle schema.table references and the columns read, with its evidence. Only patterns found in the example models are understood; anything else is reported as "not understood", never guessed. No SQL parser (sqlglot not approved). No database contact. Output: a source list in `artifacts/{run_id}/`. (FR-03, FR-02; supports later connected work) | none (offline) | **PLANNED:** scope proposed here, not built. Build starts after your OK on this scope. |
| 9 | Approved local application to the destination chosen in decision 2. (FR-10, AC-06, AC-07) | decision 2 | not started |
| 10 | Phase 1 demonstration: a new sample model and a safe edit to an existing model, with a report. Exit gate. | steps 1–9 | not started |

## 3. Proposed rules (to confirm at review)

- **Change categories (step 4, implemented):**

  | Category | Applies to |
  |---|---|
  | breaking | An object removed (a rename counts as a removal), a changed `dataType`, or a changed relationship endpoint (`fromTable`, `fromColumn`, `toTable`, `toColumn`) |
  | review | A changed expression, a changed fact, and any other changed property (for example `isActive`, `cardinality`, `isHidden`). A person checks these. |
  | additive | An object added |
  | cosmetic | Only `description`, `displayFolder`, `formatString`, `annotations`, or the storage-form note |

  A change that touches several properties gets the most serious category. Unknown properties default to review, never to cosmetic.
- **Static check rules (step 2, implemented):**

  | Rule | Severity | Checks |
  |---|---|---|
  | SC-001 | error | Two or more tables with the same name |
  | SC-002 | error | Two or more columns with the same name in one table |
  | SC-003 | error | Two or more measures with the same name in one table |
  | SC-004 | error | Two or more relationships with the same name |
  | SC-006 | error | Table, column, measure or relationship without a name |
  | SC-010 | error | Relationship column that points at a missing table or column |
  | SC-020 | error | Qualified DAX reference to a missing table, column or measure |
  | SC-021 | error | Unqualified DAX reference matching no measure in the model and no column in its own table |
  | SC-030 | error | Calculated column with no expression |
  | SC-040 | warning | Measure with a blank or missing expression |

  Rules: names are compared ignoring case, as DAX and SSAS do. Unreadable DAX (unterminated strings or comments, unbalanced brackets, escaped `]]`) is listed under "not checked". Partitions (Power Query) and role filter expressions are listed under "not checked" in every report where they exist. Rule IDs are stable; a rule change gets a new ID.
- **Edit storage (step 1, done):** an expression keeps its original form. A string stays a string, and a list of lines stays a list. A new multi-line expression is stored as a list, as Visual Studio does.

## 3a. LLM layer (client built; decided 27 Nov 2026)

**Client layer status:** implemented in `src/ssas_agent/llm/`: settings (`config.py`), the `.env` reader (`env_file.py`), endpoint policy (`endpoint.py`), the client interface (`client.py`), the OpenAI-compatible client (`openai_compatible.py`), the structured reply check (`structured.py`), and the scripted mock client for tests (`scripted.py`). Fixed choices are enums: `ChatRole`, `UrlScheme`, `EndpointKind`, `LlmSetting` (setting names), `SwitchValue`, `StructuredEvent`. Safety measures in the client: the endpoint is checked when the client is created; redirects are refused; environment proxy variables are ignored (a proxy would receive prompts outside the endpoint policy); the reply size is capped at 1 MB; requests have a timeout; the API key is sent only as a bearer header and is hidden from `repr` and from error messages.

**Endpoint location (decided 27 Nov 2026, location still unknown):** the agent accepts three cases, and the choice is made by configuration, not code:
- `local`: loopback (`localhost`, `127.x.x.x`, `::1`) over http or https. Allowed by default.
- `network_https`: a host listed in `SSAS_AGENT_LLM_ALLOWED_HOSTS`, over https. Preferred for a network server.
- `network_http`: a listed host over plain http. Allowed only when `SSAS_AGENT_LLM_ALLOW_INSECURE_HTTP=true`. This switch is a design choice of mine (default off), because prompts carry model metadata. Kept by user decision, 27 Nov 2026.

**Settings sources (decided 27 Nov 2026):** real environment variables, then the project's `.env` file, then defaults. `.env` is read only through the path policy. The policy allows reading exactly one root file, `.env` (`READABLE_FILES`), and never writing it. `.env.example` is committed with placeholders; `.env` is git-ignored. Malformed `.env` lines are refused with a line number and key name, never the value.

The agent is LLM-driven. The LLM proposes plans, DAX, SQL and candidate edits. Deterministic code validates, enforces policy and applies changes only through approval.

- **Provider:** a local LLM behind an **OpenAI-compatible chat API**. The model is not chosen yet. The structure must allow many models to be tried later, and fine-tuning may follow.
- **Interface:** one small client protocol (send messages, receive text). One implementation for OpenAI-compatible HTTP, configured by base URL, model name and an optional API key. A fake client in tests returns scripted answers and is labeled as mocked.
- **Configuration:** base URL, model name and key come from environment variables or `.env` (git-ignored). No model name or URL is hard-coded.
- **Policy:** the endpoint must be on an allowlist enforced in code, not in the prompt. Model metadata and sample data are sent only to allowlisted endpoints.
- **Evaluation:** a benchmark of fixed tasks on the fixtures, graded by deterministic checks (round-trip, static checks, exact diff). This lets different models be compared with the same evidence.
- **Output contract:** the LLM returns structured output that is parsed and validated. Invalid output is refused and recorded, never applied.
- **Target projects:** generated and edited projects are similar to the examples: SSAS 2019 Tabular, compatibility level 1500, Oracle sources, Power Query partitions, Visual Studio layout.

## 3b. New model spec (step 8, format approved 28 Nov 2026)

You write one JSON file per model. It describes structure only. It holds no credentials: a key that looks like a password, secret, token, username or credential is refused, and its value is never shown.

- Where: `specs/` in the project root. The agent can read it and cannot write to it. This folder was added to the read policy on 28 Nov 2026 (user choice). The spec is read through the path policy (`read_spec_file`).
- Top level: `spec_version` (1), `project_name` (letter first, then letters, digits or `_`, max 64), `compatibility_level` (1500 only), `culture` (optional, default `en-US`), `data_source`, `tables`, `relationships`, `measures`. Unknown keys are refused.
- `data_source`: `name` (Power Query must refer to this same name, for example `#"Oracle sample"`), `kind` (`oracle` only), `server` (a placeholder such as `<set in Visual Studio>`).
- `tables[]`: `name`, `grain` (text), `power_query` (Oracle M text, or null for no partition), `columns[]`.
- `columns[]`: `name`, `data_type` (string, int64, decimal, double, boolean, dateTime), `source_column` (optional, default the name), `is_key` (optional, default false).
- `relationships[]`: `from_table`, `from_column`, `to_table`, `to_column`. Both ends must exist.
- `measures[]`: `table`, `name`, `expression` (DAX, no leading `=`), `kpi` (the requirement this measure answers; required, so every measure is traceable).

Rules that apply to measures are the step 7 form rules (`validation/measure_form.py`). The built model must pass the static checks with no errors. Power Query text is copied as written and listed as not checked.

Output: `workspaces/{run_id}/{project}/Model.bim` and `{project}.smproj` (no deployment server, no user settings, CRLF); `artifacts/{run_id}/mapping.json` (tables, columns, relationships, measures with their KPIs; no Power Query text, no server). Nothing is written to a real project; applying the candidate is step 9.

## 4. Decisions needed from you

These affect the steps listed above. Recommendations are marked.

1. **LLM provider.** *Answered:* a local LLM behind an OpenAI-compatible API (section 3a). Still open:
   - 1a. *Partly answered 27 Nov 2026:* the location is not known yet; the code supports local, network https, and network http (see section 3a). Still open: the server address and its scheme, once your colleague confirms them. They go in `.env`, not in code.
   - 1b. The model itself is not needed now. It is chosen later through configuration.
2. **Where approved changes are written.** Options:
   - a. Workspace only. You copy the approved file into your Visual Studio project yourself. *(Recommended: no policy change.)*
   - b. A project folder you name. It becomes one explicit allowlisted write target in the policy, and nothing else is opened up.
3. **Dependency reporting before an edit.** Spec section 4.1 asks for downstream dependencies before an edit is applied. The dependency graph was moved to Phase 2. Options:
   - a. Phase 1 reports "dependencies not checked" in every proposal. The graph is built in Phase 2. *(Recommended: matches your earlier decision and is honest about coverage.)*
   - b. A narrow reference check in Phase 1: find which other measures and columns mention the edited object. Not a full graph.
4. **Knowledge source.** Which folder of approved standards and examples should be indexed in step 5, and who approves its content?
5. **New model input (step 8).** What format should the sample schema take? Options: a JSON spec file you write, or a table list extracted from one of your example models.
6. **SQL parsing dependency.** Step 7 may need `sqlglot` for Oracle SQL checks. Approve the dependency, or keep Phase 1 SQL checks to text-only rules?

## 5. Known differences from the spec

- **Oracle, not T-SQL.** Spec section 3 assumes SQL Server source queries. Your models use Oracle only, so Phase 1 SQL generation targets Oracle. `requirements.md` is not changed yet, as you asked.
- **Dependency graph** is in Phase 2 in this plan, not Phase 0 or 1 (decision 3).
- **Fixture content review** is still in progress. It does not block Phase 1 because fixtures are used only for tests.

## 6. Test plan

| Test file | Covers | Status |
|---|---|---|
| `tests/unit/test_measure_edit.py` (18 tests) | Typed measure edits, storage forms, refusals, exact diffs, end-to-end approved application to `workspaces/` | PASS |
| `tests/unit/test_dax_scanner.py` (19 tests) | DAX reference scanning, string and comment handling, unreadable text refused | PASS |
| `tests/unit/test_static_checks.py` (42 tests) | Each rule with a planted defect; clean model; case-insensitive names; the four fixtures (HISTORICAL shows the known `Add Column2` finding only) | PASS |
| `tests/unit/test_staging.py` (24 tests) | Staging writes, hash binding, review files, refused inputs write nothing, approve, apply and verify after staging, tampered candidate refused, categories in review files | PASS |
| `tests/unit/test_breaking_changes.py` (31 tests) | Each category rule on synthetic changes; real edits to a fixture (expression, added measure, rename, data type, removed relationship, description); payload holds no expression text | PASS |
| `tests/unit/test_llm_config.py` (22 tests) | Required and optional settings, defaults, blank values, API key hidden from `repr`, number and on/off switch ranges | PASS |
| `tests/unit/test_llm_env_file.py` (23 tests) | `.env` format (comments, `export`, quotes, inline comments, BOM, CRLF), line-numbered errors that never show values, duplicate keys, reads through the policy, environment overrides file | PASS |
| `tests/unit/test_knowledge.py` (21 tests, 1 skipped) | Indexing with SHA-256 hashes, skip reasons (type, size, encoding, outside policy), deterministic ranking, provenance, reference blocks that mark retrieved text as data and cannot be closed early by planted markers; real sample folder | PASS |
| `tests/unit/test_requirements_assistant.py` (15 tests, MOCKED MODEL) | Eight-field template, your entries over drafts, grounding rule (all words from the request), model failure recorded as a note, Markdown table and missing list, write only to artifacts | PASS |
| `tests/unit/test_policy_settings_file.py` (9 tests) | Only the root `.env` is readable; never writable; lookalike names and other root files stay denied | PASS |
| `tests/unit/test_llm_endpoint.py` (16 tests) | Loopback allowed; network host refused unless allowlisted; https allowed; plain http refused unless the switch is on; credentials, schemes and missing host refused | PASS |
| `tests/unit/test_llm_openai_client.py` (16 tests, MOCKED SERVER) | Request shape, bearer header, reply parsing, HTTP errors, timeout, unreachable endpoint, redirect refused, oversized reply, proxy ignored. Uses a local fake server, not a model. | PASS |
| `tests/unit/test_llm_structured_output.py` (15 tests, MOCKED CLIENT) | One JSON object only, fenced block, typed fields, boolean is not an integer, refused reply recorded without its text | PASS |
| `tests/integration/test_llm_live.py` (2 tests, LIVE) | One plain prompt, and one structured reply (up to 3 attempts), to the configured endpoint. Runs when settings are complete (environment or `.env`); NOT_RUN otherwise. | PASS on 27 Nov 2026 against local Ollama, model `qwen2.5:0.5b` (connectivity test only) |
| `tests/unit/test_generation_dax.py` (17 tests, MOCKED MODEL) | Staging a new measure on a copy of RETA, candidate and review files written, prompt context, unknown column refused (SC-020), unreadable DAX not checked, duplicate name, unknown table, blank fields, bad replies retried up to 3 attempts, unreachable model not retried, brackets in name refused, leading `=` refused, dotted name allowed | PASS |
| `tests/unit/test_generation_sql.py` (22 tests) | Clean and refused statements, literals and comments not scanned, one statement only, balanced parentheses, unclosed literal or comment, warnings, not-checked notes, artifact-only recording, event without statement text | PASS |
| `tests/unit/test_new_model.py` (36 tests) | Valid spec parsed into typed objects; 14 refusal cases with reasons (compatibility level, spec version, project name, source kind, unknown keys, data type, empty tables, duplicate names ignoring case, missing reference, unknown table, brackets and leading `=` in measures, required flags); a credential key refused without showing its value; built model has no credential, round-trips byte for byte and passes the static checks; project file has CRLF and no user or deployment settings; candidate written only under `workspaces/`; mapping has KPIs and no Power Query text or server; refused model writes nothing; existing folder never overwritten; invalid run ID refused; `specs/` readable but not writable; spec read through the policy; a spec outside readable folders refused; missing and non-UTF-8 spec files refused | PASS |
| Steps 9–10 | Not written yet | NOT_RUN |

Mocked tests are labeled as mocked. The live test contacts the configured endpoint only when its environment variables are set. No Phase 1 test contacts SSAS or Oracle.

## 7. Decision log

| Decision | Source |
|---|---|
| Start Phase 1 now, keep `requirements.md` unchanged for comparison | User, 26 Nov 2026 |
| Dependency graph moves to Phase 2 | User, 26 Nov 2026 |
| Git initialized; Phase 0 commit `9087475` is on `main` and pushed to `origin` | User, 26 Nov 2026 |
| Fixture content review in progress | User, 26 Nov 2026 |
| LLM is local, behind an OpenAI-compatible API; model not chosen; structure first, try many models later | User, 27 Nov 2026 |
| LLM endpoint location not decided: build with localhost on the allowlist, add others later | User, 27 Nov 2026 |
| Endpoint location unknown: support local, network https, or network http; the choice is configuration | User, 27 Nov 2026 |
| Live tests fail (not skip) when settings exist but the server is unreachable (kept as current behaviour) | User confirmed 27 Nov 2026 |
| Settings from a `.env` file (reader needed, with `.env.example`); environment variables override the file | User, 27 Nov 2026 |
| Plain http to a network host requires an explicit switch, default off | Agent proposed; user confirmed 27 Nov 2026 |
| Policy allows reading the root `.env` file only (exact file, never written) | Agent proposed; user confirmed 27 Nov 2026 |
| Fixed choices in code use enums | User, 27 Nov 2026 |
| Knowledge folder starts with two SAMPLE files marked NOT APPROVED; the user replaces them with approved standards. Retrieval is keyword-based and deterministic | User, 27 Nov 2026 (sample now); keyword retrieval confirmed 27 Nov 2026 |
| Policy allows reading the `knowledge/` folder (read only) | Agent proposed; user confirmed 27 Nov 2026 |
| Requirements: a fixed template first; the user or the model fills it; a model draft is kept only if all its words come from the request; output in artifacts/ | User, 27 Nov 2026 (template, artifacts); word rule Agent proposed, to confirm |
| Local test server: Ollama on this machine with the small model `qwen2.5:0.5b`, for connectivity tests only; the final model is still not chosen | User, 27 Nov 2026 (install and test model approved); final model not chosen |
| Runtime uses the standard library only; pytest 8.4.2 is the only test dependency, pinned in `requirements.txt`; project venv in `.venv` (git-ignored) | Agent proposed; user confirmed 27 Nov 2026 |
| Approved changes written to workspace only; no policy change | User, 27 Nov 2026 |
| Dependencies: report "not checked" in Phase 1; full graph in Phase 2 | User, 27 Nov 2026 |
| Knowledge source: a `knowledge/` folder in the repo, filled by the user | User, 27 Nov 2026 |
| New projects: Model.bim plus the project settings needed; no other Visual Studio files | User, 27 Nov 2026 |
| New model input: a JSON spec file written by the user | User, 27 Nov 2026 |
| SQL checks are text-only; sqlglot not approved | User, 27 Nov 2026 |
| Generated and edited projects look like the example projects | User, 27 Nov 2026 |
| Step 7 DAX: the model proposes one new measure only (no edit of existing measures); the candidate is staged for approval | User, 27 Nov 2026 |
| Step 7 SQL: text-only checks; the candidate is an artifact, never written to a project | User, 27 Nov 2026 |
| Step 7 demo model: RETA_MODEL (copied to a temporary folder in tests) | User, 27 Nov 2026 |
| Step 7 DAX drafts: up to 3 attempts when the reply is not valid JSON; the model's own errors are never applied | Agent proposed, 27 Nov 2026 (to confirm) |
| Structured replies ask the server for a JSON object only (`response_format: json_object`); plain text replies are unchanged. Checked with the local test server, 27 Nov 2026 | User chose this option, 27 Nov 2026 |
| Step 7 form rules: a measure name with `[` or `]` is refused, and an expression starting with `=` is refused. Dots and `#` stay allowed because 42 production names use dots and 12 use `#` (scan of all 8 models: no brackets, no leading `=`). Parentheses are not in production but are legal in SSAS names, so they stay allowed (a choice you can change). Found by a test run, fixed 27 Nov 2026 | User chose to compare with production models; agent applied the rule, 27 Nov 2026 |
| The word rule (every word from the request) applies to requirements drafts only, not to DAX or SQL | Agent proposed, 27 Nov 2026 (to confirm) |
| Step 8 output: Model.bim plus the `.smproj` project file; no other Visual Studio files | User, 28 Nov 2026 |
| Step 8 Power Query: you write the Oracle M text in the spec; the code copies it and lists it as not checked | User, 28 Nov 2026 |
| Step 8 spec format (section 3b) approved as the starting point | User, 28 Nov 2026 |
| Measure form rules (refuse `[` `]` in names and a leading `=`) shared by steps 7 and 8 from `validation/measure_form.py`; dots and `#` allowed | Agent applied after comparing with the 8 example models, 27 Nov 2026 |
| Spec file location: a new read-only `specs/` folder (policy change: read added, write not added) | User chose this option, 28 Nov 2026 |
| Local Ollama server restarted on 28 Nov 2026 (it was not running); live tests then passed | Operational note |
| Plan: an offline M source reader is added to Phase 1 as step 8a (no database). Connected reads of the SQL engine and live schema inspection stay in Phase 2 | User chose this option, 28 Nov 2026 |
| Step 8 sample spec `specs/SAMPLE_SALES.json` and its output (`workspaces/run-sample-spec-001/`, `artifacts/run-sample-spec-001/`) generated 28 Nov 2026; not yet opened in Visual Studio 2019 | Agent, 28 Nov 2026; user will test in VS 2019 later |
