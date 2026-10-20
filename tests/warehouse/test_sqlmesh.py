"""Run the warehouse's SQLMesh unit tests (warehouse/tests/*.yaml) under pytest."""

from __future__ import annotations

from sqlmesh import Context

from export.modelo import WAREHOUSE_DIR


def test_sqlmesh_unit_tests_pass() -> None:
    context = Context(paths=str(WAREHOUSE_DIR))
    try:
        result = context.test()
    finally:
        context.close()
    assert result.testsRun > 0
    assert result.wasSuccessful(), [str(f) for _, f in result.failures + result.errors]
