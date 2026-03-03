"""
Tests for the agents/ package — PlatformAgents.

Three tiers:
1. Codegen integration — define_module, execute_python, inspect_registry (tmp dirs)
2. OLTP end-to-end   — real embedded Postgres via StoreServer
3. Eval framework     — scoring math (pure Python)
"""

import dataclasses
import json
import os
import tempfile

import pytest

import agents._codegen as _cg
from agents._context import _PlatformContext
from store.columns import REGISTRY
from store.base import Storable
from agents._oltp import create_oltp_tools, create_oltp_agent
from agents._lakehouse import create_lakehouse_tools
from agents._feed import create_feed_tools
from agents._timeseries import create_timeseries_tools
from agents._document import create_document_tools
from agents._dashboard import create_dashboard_tools
from agents._query import create_query_tools
from agents._datascience import create_datascience_tools
from agents._codegen import create_codegen_tools
from agents._team import PlatformAgents, _AGENT_DESCRIPTIONS
from agents._eval.framework import (
    AgentEval, AgentEvalCase, EvalPhase,
    _score_tool_selection, _score_output_contains, _score_schema_quality,
    _score_table_creation, _score_metadata_completeness,
    _score_query_correctness, DEFAULT_DIMENSIONS,
)
from agents._eval.scorers import (
    score_naming_conventions, score_type_appropriateness,
    score_schema_completeness, score_star_schema_design, score_sql_validity,
)
from agents._eval.judges import (
    DATA_MODEL_RUBRIC, CURATION_QUALITY_RUBRIC, STAR_SCHEMA_RUBRIC,
    METADATA_QUALITY_RUBRIC, ANALYSIS_QUALITY_RUBRIC,
)
from agents._eval.datasets import (
    OLTP_EVAL_CASES, LAKEHOUSE_EVAL_CASES, QUERY_EVAL_CASES,
    DATASCIENCE_EVAL_CASES, ALL_EVAL_CASES,
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
requires_gemini = pytest.mark.skipif(not GEMINI_API_KEY, reason="GEMINI_API_KEY not set")


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def codegen_env(tmp_path):
    """Redirect codegen dirs to tmp and snapshot registry for cleanup."""
    col_dir = tmp_path / "columns" / "agent_generated"
    mod_dir = tmp_path / "models" / "agent_generated"
    col_dir.mkdir(parents=True)
    mod_dir.mkdir(parents=True)
    (col_dir / "__init__.py").write_text("")
    (mod_dir / "__init__.py").write_text("")

    orig_cols, orig_mods = _cg.COLUMNS_DIR, _cg.MODELS_DIR
    _cg.COLUMNS_DIR, _cg.MODELS_DIR = col_dir, mod_dir

    before = set(REGISTRY._columns.keys())
    yield col_dir, mod_dir

    _cg.COLUMNS_DIR, _cg.MODELS_DIR = orig_cols, orig_mods
    for k in list(REGISTRY._columns.keys()):
        if k not in before:
            del REGISTRY._columns[k]


@pytest.fixture(scope="module")
def store_server():
    """Start a real embedded Postgres for OLTP e2e tests."""
    from store.server import StoreServer
    tmp_dir = tempfile.mkdtemp(prefix="test_agents_")
    srv = StoreServer(data_dir=tmp_dir, admin_password="test_admin_pw")
    srv.start()
    srv.provision_user("agent_user", "agent_pw")
    srv.register_alias("agent_test")
    yield srv
    srv.stop()


def _get_tool(tools, name):
    return next(t for t in tools if t.__name__ == name)


# ── Tool Inventory (regression guard) ─────────────────────────────────


_EXPECTED_TOOLS = {
    "oltp": (9, ["create_dataset", "insert_records", "query_dataset",
                  "inspect_registry", "define_module", "execute_python"]),
    "lakehouse": (7, ["list_lakehouse_tables", "design_star_schema", "build_datacube"]),
    "feed": (5, ["list_md_symbols", "describe_feed_setup"]),
    "timeseries": (6, ["list_tsdb_series", "get_bars"]),
    "document": (6, ["upload_document", "search_documents"]),
    "dashboard": (9, ["create_reactive_model", "create_ticking_table",
                       "inspect_registry", "define_module"]),
    "query": (7, ["query_store", "list_all_datasets"]),
    "datascience": (7, ["compute_statistics", "run_regression"]),
}

_TOOL_CREATORS = {
    "oltp": create_oltp_tools,
    "lakehouse": create_lakehouse_tools,
    "feed": create_feed_tools,
    "timeseries": create_timeseries_tools,
    "document": create_document_tools,
    "dashboard": create_dashboard_tools,
    "query": create_query_tools,
    "datascience": create_datascience_tools,
}


class TestToolInventory:

    @pytest.mark.parametrize("agent", list(_EXPECTED_TOOLS.keys()))
    def test_tool_count_and_names(self, agent):
        expected_count, must_have = _EXPECTED_TOOLS[agent]
        tools = _TOOL_CREATORS[agent](_PlatformContext())
        names = [t.__name__ for t in tools]
        assert len(names) == expected_count, f"{agent}: expected {expected_count}, got {len(names)}: {names}"
        for name in must_have:
            assert name in names, f"{agent} missing tool: {name}"


# ── Codegen Integration (tmp dirs, no services) ──────────────────────


class TestCodegenIntegration:

    def test_inspect_registry(self):
        inspect_fn = _get_tool(create_codegen_tools(_PlatformContext()), "inspect_registry")
        result = json.loads(inspect_fn(columns_json='["symbol", "zzz_fake"]'))
        assert result["symbol"]["exists"] is True
        assert result["zzz_fake"]["exists"] is False

    def test_inspect_summary(self):
        inspect_fn = _get_tool(create_codegen_tools(_PlatformContext()), "inspect_registry")
        result = json.loads(inspect_fn(columns_json="[]"))
        assert result["total_columns"] > 0

    def test_define_column_module(self, codegen_env):
        col_dir, _ = codegen_env
        define_fn = _get_tool(create_codegen_tools(_PlatformContext()), "define_module")
        code = (
            'from store.columns import REGISTRY\n'
            'REGISTRY.define("cg_test_col", float, role="measure", unit="USD", description="Test")\n'
        )
        r = json.loads(define_fn(module_name="test_cols", code=code, module_type="columns"))
        assert r["status"] == "success", f"Failed: {r}"
        assert (col_dir / "test_cols.py").exists()
        assert REGISTRY.has("cg_test_col")

    def test_define_model_module(self, codegen_env):
        _, mod_dir = codegen_env
        ctx = _PlatformContext()
        define_fn = _get_tool(create_codegen_tools(ctx), "define_module")
        for n in ["cg_mod_a", "cg_mod_b"]:
            if not REGISTRY.has(n):
                REGISTRY.define(n, float, role="measure", unit="units", description=n)
        code = (
            'from dataclasses import dataclass\nfrom store.base import Storable\n\n'
            '@dataclass\nclass CGModel(Storable):\n    cg_mod_a: float = 0.0\n    cg_mod_b: float = 0.0\n'
        )
        r = json.loads(define_fn(module_name="test_model", code=code, module_type="models"))
        assert r["status"] == "success", f"Failed: {r}"
        assert "CGModel" in r["created_types"]
        assert ctx.get_storable_type("CGModel") is not None

    def test_execute_python(self):
        exec_fn = _get_tool(create_codegen_tools(_PlatformContext()), "execute_python")
        r = json.loads(exec_fn(code="result = 2 + 2"))
        assert r["status"] == "success" and r["result"] == 4

    def test_execute_python_print_capture(self):
        exec_fn = _get_tool(create_codegen_tools(_PlatformContext()), "execute_python")
        r = json.loads(exec_fn(code='print("hello sandbox")'))
        assert "hello sandbox" in r["output"]

    def test_execute_python_rejects_forbidden(self):
        exec_fn = _get_tool(create_codegen_tools(_PlatformContext()), "execute_python")
        assert json.loads(exec_fn(code="import os"))["status"] == "error"


# ── OLTP Codegen Pipeline (tmp dirs, no Postgres) ────────────────────


class TestOLTPCodegen:

    def test_create_dataset_full_pipeline(self, codegen_env):
        col_dir, mod_dir = codegen_env
        ctx = _PlatformContext()
        create_fn = _get_tool(create_oltp_tools(ctx), "create_dataset")

        fields = json.dumps([
            {"name": "cg_symbol", "type": "str"},
            {"name": "cg_price", "type": "float"},
            {"name": "cg_quantity", "type": "int"},
        ])
        result = json.loads(create_fn(name="CGTrade", fields_json=fields))
        assert result["status"] == "created", f"Failed: {result}"
        assert result["persistent"] is True

        # Files on disk
        assert (col_dir / "cgtrade_columns.py").exists()
        assert (mod_dir / "cgtrade_model.py").exists()

        # Column metadata
        assert REGISTRY.get("cg_symbol").role == "dimension"
        assert REGISTRY.get("cg_price").role == "measure"

        # Type in context, instantiable
        cls = ctx.get_storable_type("CGTrade")
        assert issubclass(cls, Storable)
        obj = cls()
        assert obj.cg_symbol == ""
        assert obj.cg_price == 0.0

    def test_create_reuses_existing_columns(self, codegen_env):
        ctx = _PlatformContext()
        create_fn = _get_tool(create_oltp_tools(ctx), "create_dataset")
        REGISTRY.define("cg_preexisting", float, role="measure", unit="USD", description="Pre-existing")
        fields = json.dumps([
            {"name": "cg_preexisting", "type": "float"},
            {"name": "cg_new_col", "type": "str"},
        ])
        result = json.loads(create_fn(name="CGMixed", fields_json=fields))
        assert "cg_preexisting" in result["existing_columns"]
        assert "cg_new_col" in result["new_columns"]

    def test_create_duplicate_rejected(self, codegen_env):
        ctx = _PlatformContext()
        create_fn = _get_tool(create_oltp_tools(ctx), "create_dataset")
        fields = json.dumps([{"name": "cg_dup_x", "type": "int"}])
        json.loads(create_fn(name="CGDup", fields_json=fields))
        assert "error" in json.loads(create_fn(name="CGDup", fields_json=fields))

    def test_create_invalid_type_rejected(self):
        create_fn = _get_tool(create_oltp_tools(_PlatformContext()), "create_dataset")
        assert "error" in json.loads(create_fn(
            name="Bad", fields_json=json.dumps([{"name": "x", "type": "complex_number"}]),
        ))

    def test_dashboard_bad_key_rejected(self, codegen_env):
        model_fn = _get_tool(create_dashboard_tools(_PlatformContext()), "create_reactive_model")
        assert "error" in json.loads(model_fn(
            name="BadKey", key_field="nonexistent",
            fields_json=json.dumps([{"name": "x", "type": "int"}]),
        ))


# ── OLTP End-to-End (real Postgres) ──────────────────────────────────


class TestOLTPEndToEnd:
    """Real StoreServer → create dataset → insert records → query back."""

    def test_create_and_query_round_trip(self, store_server, codegen_env):
        col_dir, mod_dir = codegen_env

        ctx = _PlatformContext(
            alias="agent_test",
            user="agent_user",
            password="agent_pw",
        )
        tools = create_oltp_tools(ctx)
        create_fn = _get_tool(tools, "create_dataset")
        insert_fn = _get_tool(tools, "insert_records")
        query_fn = _get_tool(tools, "query_dataset")

        # Create dataset
        fields = json.dumps([
            {"name": "e2e_symbol", "type": "str"},
            {"name": "e2e_price", "type": "float"},
            {"name": "e2e_quantity", "type": "int"},
        ])
        create_result = json.loads(create_fn(name="E2ETrade", fields_json=fields))
        assert create_result["status"] == "created", f"Create failed: {create_result}"

        # Insert records
        records = json.dumps([
            {"e2e_symbol": "AAPL", "e2e_price": 228.50, "e2e_quantity": 100},
            {"e2e_symbol": "GOOGL", "e2e_price": 192.30, "e2e_quantity": 50},
            {"e2e_symbol": "MSFT", "e2e_price": 415.00, "e2e_quantity": 75},
        ])
        insert_result = json.loads(insert_fn(type_name="E2ETrade", records_json=records))
        assert insert_result["inserted"] == 3, f"Insert failed: {insert_result}"
        assert insert_result["errors"] == 0
        assert len(insert_result["entity_ids"]) == 3

        # Query back
        query_result = json.loads(query_fn(type_name="E2ETrade", limit=10))
        assert query_result["count"] == 3, f"Query failed: {query_result}"
        symbols = {r["e2e_symbol"] for r in query_result["rows"]}
        assert symbols == {"AAPL", "GOOGL", "MSFT"}

    def test_insert_unknown_type_rejected(self, store_server, codegen_env):
        ctx = _PlatformContext(alias="agent_test", user="agent_user", password="agent_pw")
        insert_fn = _get_tool(create_oltp_tools(ctx), "insert_records")
        result = json.loads(insert_fn(
            type_name="NonExistent",
            records_json=json.dumps([{"x": 1}]),
        ))
        assert "error" in result

    def test_query_unknown_type_rejected(self, store_server, codegen_env):
        ctx = _PlatformContext(alias="agent_test", user="agent_user", password="agent_pw")
        query_fn = _get_tool(create_oltp_tools(ctx), "query_dataset")
        result = json.loads(query_fn(type_name="NonExistent"))
        assert "error" in result


# ── Eval Scoring (pure math) ─────────────────────────────────────────


class TestEvalScoring:

    def test_tool_selection(self):
        assert _score_tool_selection(
            AgentEvalCase(expected_tools=["create_dataset"]),
            {"actual_tools": ["create_dataset", "insert_records"]},
        ) == 1.0
        assert _score_tool_selection(
            AgentEvalCase(expected_tools=["create_dataset", "insert_records"]),
            {"actual_tools": ["list_storable_types"]},
        ) == 0.0
        assert _score_tool_selection(
            AgentEvalCase(expected_tools=["create_dataset", "insert_records"]),
            {"actual_tools": ["create_dataset"]},
        ) == 0.5

    def test_output_contains(self):
        assert _score_output_contains(
            AgentEvalCase(expected_output_contains=["symbol", "price"]),
            {"actual_output": "Created table with symbol and price fields"},
        ) == 1.0
        score = _score_output_contains(
            AgentEvalCase(expected_output_contains=["symbol", "price", "volume"]),
            {"actual_output": "Created symbol and price"},
        )
        assert abs(score - 2/3) < 0.01

    def test_schema_quality(self):
        assert _score_schema_quality(
            AgentEvalCase(expected_schema={"fields": ["symbol", "price"]}),
            {"created_schema": {"fields": [{"name": "symbol"}, {"name": "price"}]}},
        ) == 1.0

    def test_table_creation(self):
        assert _score_table_creation(
            AgentEvalCase(expected_tables=["fact_trades", "dim_instrument"]),
            {"created_tables": ["fact_trades", "dim_instrument"]},
        ) == 1.0

    def test_query_correctness(self):
        assert _score_query_correctness(
            AgentEvalCase(expected_result=42), {"query_result": 42},
        ) == 1.0
        assert _score_query_correctness(
            AgentEvalCase(expected_result=100.0), {"query_result": 95.0},
        ) == 0.95

    def test_naming_conventions(self):
        good = score_naming_conventions(AgentEvalCase(), {"created_schema": {
            "type_name": "Trade",
            "fields": [{"name": "order_id"}, {"name": "trade_price"}],
        }})
        bad = score_naming_conventions(AgentEvalCase(), {"created_schema": {
            "type_name": "trade",
            "fields": [{"name": "OrderId"}, {"name": "PRICE"}],
        }})
        assert good == 1.0
        assert bad < 0.5

    def test_sql_validity(self):
        case = AgentEvalCase()
        assert score_sql_validity(case, {"generated_sql": "SELECT * FROM trades"}) == 1.0
        assert score_sql_validity(case, {"generated_sql": "DELETE FROM trades"}) == 0.3

    def test_star_schema_design(self):
        good = score_star_schema_design(AgentEvalCase(), {"star_schema_design": {
            "fact_tables": [{"name": "fact_trades", "columns": [{"role": "measure", "type": "float"}]}],
            "dimension_tables": [{"name": "dim_instrument", "columns": [{"role": "attribute", "type": "str"}]}],
            "relationships": [{"fact": "fact_trades", "dimension": "dim_instrument", "join_key": "symbol"}],
        }})
        empty = score_star_schema_design(AgentEvalCase(), {
            "star_schema_design": {"fact_tables": [], "dimension_tables": [], "relationships": []}
        })
        assert good >= 0.8
        assert empty == 0.0


# ── Eval Data Integrity ──────────────────────────────────────────────


class TestEvalDatasets:

    def test_case_counts(self):
        assert len(OLTP_EVAL_CASES) >= 5
        assert len(LAKEHOUSE_EVAL_CASES) >= 4
        assert len(QUERY_EVAL_CASES) >= 4
        assert len(DATASCIENCE_EVAL_CASES) >= 3
        assert len(ALL_EVAL_CASES) >= 20

    def test_case_integrity(self):
        for case in ALL_EVAL_CASES:
            assert case.tags, f"Missing tags: {case.input[:40]}"
            assert case.difficulty in ("basic", "intermediate", "advanced")

    def test_rubrics(self):
        for rubric in [DATA_MODEL_RUBRIC, CURATION_QUALITY_RUBRIC,
                       STAR_SCHEMA_RUBRIC, METADATA_QUALITY_RUBRIC,
                       ANALYSIS_QUALITY_RUBRIC]:
            assert isinstance(rubric, str) and len(rubric) > 50

    def test_dimensions_and_phases(self):
        assert len(DEFAULT_DIMENSIONS) >= 7
        assert EvalPhase.TOOL_SELECTION.value < EvalPhase.END_TO_END.value
        evaluator = AgentEval(agents={}, max_phase=EvalPhase.TOOL_SELECTION)
        assert all(d.phase == EvalPhase.TOOL_SELECTION for d in evaluator.active_dimensions)


# ── PlatformAgents ────────────────────────────────────────────────────


class TestPlatformAgents:

    def test_agent_descriptions(self):
        assert len(_AGENT_DESCRIPTIONS) == 8
        for name in ["oltp", "lakehouse", "feed", "timeseries",
                      "document", "dashboard", "query", "quant"]:
            assert name in _AGENT_DESCRIPTIONS

    @requires_gemini
    def test_team_construction(self):
        team = PlatformAgents()
        assert len(team) == 8
        assert "oltp" in team

    @requires_gemini
    def test_team_subset(self):
        team = PlatformAgents(agents=["oltp", "lakehouse"])
        assert len(team) == 2
        assert "feed" not in team

    @requires_gemini
    def test_typed_properties(self):
        team = PlatformAgents(agents=["oltp", "quant"])
        assert team.oltp is not None
        assert team.quant is not None
