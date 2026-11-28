"""Offline M source reader (step 8a): reads what each partition's SQL reads, with M line numbers.

No database is contacted. Each test states the SQL or M text it reads, so the expected results can be checked
by eye. The fixture test reads a real example model and checks a few lines against the file."""

import json
from pathlib import Path

import pytest

from ssas_agent.msource import (
    SOURCES_FILE_NAME,
    ReadingStatus,
    read_model_sources,
    read_partition,
    record_source_report,
    sources_payload,
)
from ssas_agent.msource.native_query import find_native_query
from ssas_agent.msource.sql_reading import read_sql
from ssas_agent.policy import PathPolicy

ORACLE_SOURCE = "Oracle/oracle-host:1521/oracle_service"
RUN_ID = "run-sources-001"
FIXTURE_MODEL = Path(__file__).resolve().parents[1] / "fixtures" / "EOPM_MODEL" / "Model.bim"
CLOSING_OPTIONS = ", null, [EnableFolding=true])\nin\n    Source"


def native_query_m(sql: str, data_source: str = ORACLE_SOURCE, closing: str = CLOSING_OPTIONS) -> str:
    """M text shaped like the example models: the SQL is one M string, with quotes doubled."""
    escaped_sql = sql.replace('"', '""')
    return f'let\n    Source = Value.NativeQuery(#"{data_source}", "{escaped_sql}"{closing}'


def m_partition(m_text: str) -> dict:
    return {"name": "P", "mode": "import", "source": {"type": "m", "expression": m_text.split("\n")}}


def model_with_partitions(*tables: tuple[str, dict]) -> dict:
    return {
        "name": "SemanticModel",
        "model": {"tables": [{"name": name, "partitions": [partition]} for name, partition in tables]},
    }


@pytest.fixture
def project(tmp_path):
    return PathPolicy(project_root=tmp_path)


# ---- SQL reading -------------------------------------------------------------------------------


def test_simple_select_gives_tables_and_plain_columns_with_lines():
    # Line 5 SELECT, 6 t.id, 7 t.name, 8 FROM, 9 sales_orders
    reading = read_sql("SELECT\n    t.id,\n    t.name\nFROM\n    sales_orders t", first_line=5)

    assert [(r.reference, r.line) for r in reading.references] == [("sales_orders", 9)]
    assert [(c.name, c.line) for c in reading.columns] == [("id", 6), ("name", 7)]
    assert reading.select_all is False
    assert reading.problems == () and reading.notes == ()


def test_schema_qualified_table_is_split_into_schema_and_name():
    reading = read_sql("SELECT x FROM HR.EMPLOYEES")

    assert reading.references[0].schema == "HR"
    assert reading.references[0].name == "EMPLOYEES"


def test_alias_after_a_plain_column_keeps_the_source_column_name():
    reading = read_sql("SELECT b.id partner_id, a.name AS partner FROM x a JOIN y b ON a.k = b.k")

    assert [(c.name, c.alias) for c in reading.columns] == [("id", "partner_id"), ("name", "partner")]


def test_expression_column_is_left_out_and_noted_while_plain_columns_stay():
    reading = read_sql("SELECT coalesce(a, 0) amount,\n    customer_id\nFROM sales")

    assert [c.name for c in reading.columns] == ["customer_id"]
    assert reading.notes == ("select list has expressions; those columns are not listed",)


def test_null_literal_is_an_expression_not_a_column():
    reading = read_sql("SELECT NULL AS placeholder, id FROM sales")

    assert [c.name for c in reading.columns] == ["id"]
    assert reading.notes == ("select list has expressions; those columns are not listed",)


def test_select_star_sets_select_all_and_lists_no_columns():
    reading = read_sql("SELECT * FROM DIM_DATE")

    assert reading.select_all is True
    assert reading.columns == ()


def test_common_table_expression_name_is_not_a_source_table():
    reading = read_sql("WITH recent AS (SELECT id FROM orders) SELECT r.id FROM recent r JOIN customers c ON 1 = 1")

    assert [r.name for r in reading.references] == ["orders", "customers"]


def test_from_and_join_inside_a_subquery_are_both_references():
    reading = read_sql("SELECT s.id FROM (SELECT id FROM orders) s LEFT JOIN payments p ON p.id = s.id")

    assert [r.name for r in reading.references] == ["orders", "payments"]


def test_words_inside_string_literals_and_comments_are_not_read():
    sql = "SELECT id FROM orders -- JOIN fake_table\nWHERE note = 'FROM not_a_table'"

    reading = read_sql(sql)

    assert [r.name for r in reading.references] == ["orders"]


def test_comma_joined_tables_are_noted_as_not_listed():
    reading = read_sql("SELECT a.id FROM orders a, customers c WHERE a.cid = c.id")

    assert "comma-joined tables after FROM are not listed" in reading.notes


def test_comma_inside_a_subquery_in_from_is_not_a_comma_join():
    reading = read_sql("SELECT s.id FROM (SELECT a, b FROM orders) s")

    assert not any("comma-joined" in note for note in reading.notes)


def test_union_reads_every_table_but_only_the_first_select_columns():
    reading = read_sql("SELECT id FROM orders UNION ALL SELECT id FROM refunds")

    assert [r.name for r in reading.references] == ["orders", "refunds"]
    assert [c.name for c in reading.columns] == ["id"]
    assert any("UNION" in note for note in reading.notes)


def test_sql_without_select_and_from_is_a_problem_not_a_guess():
    reading = read_sql("DELETE FROM orders")

    assert reading.references == ()
    assert reading.problems == ("no top-level SELECT ... FROM found",)


def test_unterminated_string_literal_is_reported_as_a_problem():
    reading = read_sql("SELECT 'unterminated FROM orders")

    assert reading.references == ()
    assert reading.problems


# ---- Native query shape -------------------------------------------------------------------------


def test_native_query_gives_data_source_sql_and_start_line():
    query = find_native_query(native_query_m("SELECT x\nFROM y"))

    assert query is not None
    assert query.data_source == ORACLE_SOURCE
    assert query.sql == "SELECT x\nFROM y"
    assert query.sql_start_line == 2
    assert query.notes == ()


def test_doubled_quotes_in_the_m_string_become_one_quote_in_the_sql():
    query = find_native_query(native_query_m('SELECT "Full Name" FROM t'))

    assert query.sql == 'SELECT "Full Name" FROM t'


def test_steps_after_the_native_query_are_read_with_a_note():
    m_text = (
        'let\n    Source = Value.NativeQuery(#"src", "SELECT x FROM y", null),\n'
        "    Filtered = Table.SelectRows(Source, each true)\nin\n    Filtered"
    )

    query = find_native_query(m_text)

    assert query.sql == "SELECT x FROM y"
    assert query.notes == ("later Power Query steps are not read",)


def test_two_native_query_calls_in_one_partition_are_not_read():
    m_text = native_query_m("SELECT x FROM y") + "\n" + native_query_m("SELECT z FROM w")

    assert find_native_query(m_text) is None


def test_m_text_that_is_not_a_native_query_is_not_read():
    assert find_native_query('let\n    Source = Oracle.Database("host"),\nin\n    Source') is None


def test_unclosed_sql_literal_is_not_read():
    assert find_native_query('let\n    Source = Value.NativeQuery(#"src", "SELECT x FROM y') is None


# ---- Partition status ------------------------------------------------------------------------------


def test_clean_native_query_partition_is_understood():
    reading = read_partition("FACT", m_partition(native_query_m("SELECT t.id FROM sales t")))

    assert reading.status is ReadingStatus.UNDERSTOOD
    assert reading.data_source == ORACLE_SOURCE
    assert reading.notes == ()


def test_partition_with_an_expression_column_is_partial():
    reading = read_partition("FACT", m_partition(native_query_m("SELECT coalesce(a, 0) x FROM sales")))

    assert reading.status is ReadingStatus.PARTIAL


def test_partition_with_steps_after_the_query_is_partial():
    m_text = native_query_m("SELECT id FROM sales", closing=", null),\n    Filtered = Table.SelectRows(Source, each true)\nin\n    Filtered")

    reading = read_partition("FACT", m_partition(m_text))

    assert reading.status is ReadingStatus.PARTIAL
    assert "later Power Query steps are not read" in reading.notes


def test_partition_with_unreadable_sql_is_not_understood():
    reading = read_partition("FACT", m_partition(native_query_m("DELETE FROM sales")))

    assert reading.status is ReadingStatus.NOT_UNDERSTOOD
    assert reading.sql.problems == ("no top-level SELECT ... FROM found",)


def test_generated_date_partition_is_not_understood_with_a_clear_note():
    reading = read_partition("DIM_DATE", m_partition("let\n    Source = #date(2020, 1, 1)\nin\n    Source"))

    assert reading.status is ReadingStatus.NOT_UNDERSTOOD
    assert reading.notes == ("generated values (#date), not read from a source",)


def test_unrecognised_power_query_shape_is_not_understood():
    reading = read_partition(
        "OTHER", m_partition('let\n    Source = Excel.Workbook(File.Contents("x.xlsx"))\nin\n    Source')
    )

    assert reading.status is ReadingStatus.NOT_UNDERSTOOD
    assert reading.notes[0].startswith("Power Query shape not recognised")


def test_calculated_partition_is_not_applicable():
    partition = {"name": "P", "source": {"type": "calculated", "expression": "DATATABLE(...)"}}

    reading = read_partition("CALC", partition)

    assert reading.status is ReadingStatus.NOT_APPLICABLE
    assert reading.sql is None


# ---- Model level and report -----------------------------------------------------------------------


def test_read_model_sources_reads_every_partition_in_table_order():
    data = model_with_partitions(
        ("FACT", m_partition(native_query_m("SELECT id FROM sales"))),
        ("DIM", m_partition(native_query_m("SELECT coalesce(a, 0) x FROM dim"))),
    )

    readings = read_model_sources(data)

    assert [(r.table, r.status) for r in readings] == [
        ("FACT", ReadingStatus.UNDERSTOOD),
        ("DIM", ReadingStatus.PARTIAL),
    ]


def test_report_is_written_under_artifacts_with_counts_and_no_sql_text(tmp_path, project):
    data = model_with_partitions(("FACT", m_partition(native_query_m("SELECT id FROM sales"))))

    path = record_source_report(project, Path("artifacts"), RUN_ID, data)

    assert path == tmp_path / "artifacts" / RUN_ID / SOURCES_FILE_NAME
    report_text = path.read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["counts"]["understood"] == 1
    assert report["tables"][0]["references"][0]["reference"] == "sales"
    assert "SELECT" not in report_text
    assert (tmp_path / "artifacts" / RUN_ID / "events.jsonl").exists()


def test_payload_counts_every_status_even_when_zero():
    payload = sources_payload(())

    assert payload["counts"] == {"understood": 0, "partial": 0, "not_understood": 0, "not_applicable": 0}


def test_example_model_reads_hand_checked_lines():
    data = json.loads(FIXTURE_MODEL.read_bytes().decode("utf-8-sig"))
    partition = next(
        table for table in data["model"]["tables"] if table["name"] == "TRX_INVOICES"
    )["partitions"][0]

    reading = read_partition("TRX_INVOICES", partition)

    assert reading.status is ReadingStatus.PARTIAL
    assert [(r.name, r.line) for r in reading.sql.references] == [
        ("erp_contract_invoice_collection", 29),
        ("erp_project_contract_map", 30),
    ]
    assert [(c.name, c.line) for c in reading.sql.columns][:3] == [
        ("customer_id", 17),
        ("contract_id", 18),
        ("contract_number", 19),
    ]
    assert reading.sql.columns[-1].name == "business_unit_id"
    assert reading.sql.columns[-1].line == 27
