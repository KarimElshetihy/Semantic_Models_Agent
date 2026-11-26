"""Inspect the tabular Model.bim files in a folder (default: example_models/).

Read-only. Prints the structural facts and round-trip checks used by the
Phase 0 design. Never writes any files.

Run from the project root:
    python tools/inspect_bim_examples.py [folder]
"""

import collections

from bim_format import (
    EXAMPLES_ROOT,
    expression_form,
    expression_text,
    find_model_files,
    has_bom,
    load_document,
    m_partition_shape,
    project_label,
    resolve_root_from_arguments,
    round_trips_byte_for_byte,
)


def tables_of(model):
    return model.get("tables", [])


def all_columns(model):
    return [column for table in tables_of(model) for column in table.get("columns", [])]


def all_measures(model):
    return [measure for table in tables_of(model) for measure in table.get("measures", [])]


def all_partitions(model):
    return [partition for table in tables_of(model) for partition in table.get("partitions", [])]


def report_round_trip(raw_bytes, document):
    matches = round_trips_byte_for_byte(raw_bytes, document)
    print(f"  round-trip byte-identical: {matches} | BOM: {has_bom(raw_bytes)}")


def report_structure(model):
    tables = tables_of(model)
    columns = all_columns(model)
    calculated_columns = sum(column.get("type") == "calculated" for column in columns)
    print(f"  tables: {len(tables)} | columns: {len(columns)} | calculated columns: {calculated_columns}"
          f" | measures: {len(all_measures(model))}"
          f" | relationships: {len(model.get('relationships', []))}"
          f" | roles: {len(model.get('roles', []))}")
    print(f"  lineageTag on tables: {sum('lineageTag' in table for table in tables)}/{len(tables)}"
          f" | table names unique: {len({table['name'] for table in tables}) == len(tables)}")


def report_relationship_identity(model):
    relationships = model.get("relationships", [])
    names = [relationship.get("name") for relationship in relationships]
    named = sum(name is not None for name in names)
    unique = len(set(filter(None, names))) == named
    print(f"  relationships with name: {named}/{len(relationships)} | names unique: {unique}")


def report_expression_storage(model):
    measures = all_measures(model)
    calculated = [column for column in all_columns(model) if column.get("type") == "calculated"]
    measure_forms = collections.Counter(expression_form(m.get("expression")) for m in measures)
    column_forms = collections.Counter(expression_form(c.get("expression")) for c in calculated)
    line_breaks = any(
        isinstance(m.get("expression"), list) and any("\n" in line or "\r" in line for line in m["expression"])
        for m in measures
    )
    print(f"  measure expression forms: {dict(measure_forms)} | column expression forms: {dict(column_forms)}")
    print(f"  list-form lines contain embedded line breaks: {line_breaks}")


def report_m_partitions(model):
    shapes = collections.Counter()
    for partition in all_partitions(model):
        source = partition.get("source", {})
        if source.get("type") == "m":
            shapes[m_partition_shape(expression_text(source.get("expression")))] += 1
    print(f"  M partition shapes: {dict(shapes)}")


def report_findings(model):
    for column in all_columns(model):
        if column.get("type") == "calculated" and not column.get("expression"):
            print(f"  finding: calculated column without expression: {column.get('name')}")
    for partition in all_partitions(model):
        source = partition.get("source", {})
        if source.get("type") == "m" and "DateTime.LocalNow" in expression_text(source.get("expression")):
            print("  finding: M partition uses DateTime.LocalNow (non-deterministic)")
            break


def inspect_model(model_path, root):
    raw_bytes, document = load_document(model_path)
    model = document["model"]
    print("=" * 70)
    print(project_label(model_path, root), "|", model_path.relative_to(root))
    report_round_trip(raw_bytes, document)
    report_structure(model)
    report_relationship_identity(model)
    report_expression_storage(model)
    report_m_partitions(model)
    report_findings(model)


def main():
    root = resolve_root_from_arguments(EXAMPLES_ROOT)
    for model_path in find_model_files(root):
        inspect_model(model_path, root)


if __name__ == "__main__":
    main()
