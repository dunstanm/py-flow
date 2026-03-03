"""
Tests for agents/_codegen.py — AST validation, file mechanics, auto-import.

Tool-level integration tests (define_module, execute_python, inspect_registry)
live in test_data_engineers.py.
"""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents._codegen import (
    create_codegen_tools,
    load_agent_modules,
    validate_code,
)
from agents._context import _PlatformContext

# ── Fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def ctx():
    return _PlatformContext(alias="test")


@pytest.fixture
def tmp_dirs(tmp_path):
    """Redirect COLUMNS_DIR / MODELS_DIR to temp."""
    col_dir = tmp_path / "columns" / "agent_generated"
    mod_dir = tmp_path / "models" / "agent_generated"
    col_dir.mkdir(parents=True)
    mod_dir.mkdir(parents=True)
    (col_dir / "__init__.py").write_text("")
    (mod_dir / "__init__.py").write_text("")

    import agents._codegen as cg
    orig_cols, orig_mods = cg.COLUMNS_DIR, cg.MODELS_DIR
    cg.COLUMNS_DIR, cg.MODELS_DIR = col_dir, mod_dir
    yield col_dir, mod_dir
    cg.COLUMNS_DIR, cg.MODELS_DIR = orig_cols, orig_mods


# ── AST Validation (security boundary) ────────────────────────────────

class TestASTValidation:

    def test_clean_code_passes(self):
        errors = validate_code(
            'from store.columns import REGISTRY\n'
            'REGISTRY.define("x", float, role="measure", unit="USD", description="x")\n'
        )
        assert errors == []

    def test_forbidden_import_os(self):
        assert any("'os'" in e for e in validate_code("import os"))

    def test_forbidden_import_subprocess(self):
        assert any("subprocess" in e for e in validate_code("import subprocess"))

    def test_forbidden_from_import(self):
        assert any("Forbidden" in e for e in validate_code("from os.path import join"))

    def test_forbidden_builtins(self):
        for call in ["exec('x')", "eval('x')", "open('/etc/passwd')"]:
            assert validate_code(call), f"{call} should be blocked"

    def test_multiple_forbidden(self):
        assert len(validate_code("import os\nimport sys\nimport subprocess")) == 3

    def test_syntax_error(self):
        errors = validate_code("def foo(")
        assert any("SyntaxError" in e for e in errors)

    def test_safe_imports_pass(self):
        code = (
            "from store.columns import REGISTRY\n"
            "from store.base import Storable\n"
            "from dataclasses import dataclass\n"
            "import math\nimport json\n"
        )
        assert validate_code(code) == []


# ── File mechanics (backup, cleanup, path traversal) ──────────────────

class TestFileMechanics:

    def test_rejects_path_traversal(self, ctx, tmp_dirs):
        define = create_codegen_tools(ctx)[1]
        r = json.loads(define(module_name="../../../etc/passwd", code="x=1", module_type="columns"))
        assert r["status"] == "error"

    def test_rejects_invalid_module_type(self, ctx, tmp_dirs):
        define = create_codegen_tools(ctx)[1]
        r = json.loads(define(module_name="test", code="x=1", module_type="evil"))
        assert r["status"] == "error"

    def test_overwrite_creates_backup(self, ctx, tmp_dirs):
        col_dir, _ = tmp_dirs
        define = create_codegen_tools(ctx)[1]
        define(module_name="ver", code="x = 1", module_type="columns")
        define(module_name="ver", code="x = 2", module_type="columns")
        assert list(col_dir.glob("ver.bak.*"))
        assert "x = 2" in (col_dir / "ver.py").read_text()

    def test_exec_failure_removes_file(self, ctx, tmp_dirs):
        col_dir, _ = tmp_dirs
        define = create_codegen_tools(ctx)[1]
        r = json.loads(define(module_name="broken", code="z = undefined_var + 1", module_type="columns"))
        assert r["status"] == "error"
        assert not (col_dir / "broken.py").exists()


# ── Auto-import (module loading) ─────────────────────────────────────

class TestAutoImport:

    def test_empty_dir(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        assert load_agent_modules(d) == []

    def test_skips_underscore(self, tmp_path):
        d = tmp_path / "m"
        d.mkdir()
        (d / "__init__.py").write_text("")
        (d / "_private.py").write_text("x = 1")
        assert load_agent_modules(d) == []

    def test_loads_valid(self, tmp_path):
        d = tmp_path / "m"
        d.mkdir()
        (d / "hello.py").write_text("LOADED = True\n")
        assert "hello" in load_agent_modules(d)

    def test_bad_module_doesnt_crash(self, tmp_path):
        d = tmp_path / "m"
        d.mkdir()
        (d / "bad.py").write_text("raise RuntimeError('boom')\n")
        assert load_agent_modules(d) == []

    def test_nonexistent_dir(self):
        assert load_agent_modules(Path("/nonexistent/path")) == []
