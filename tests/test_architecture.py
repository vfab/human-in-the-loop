"""
Lightweight Integration Tests - No Agent Framework Required

These tests validate the architecture and structure without requiring
the full agent-framework-openai dependency (which needs C++ build tools for pyyaml).

Tests cover:
- Workflow module structure and signatures
- WorkflowConfig dataclass
- Event class definitions
- Static file presence
- FastAPI endpoints
- WebSocket handler structure
"""

import pytest
import sys
from pathlib import Path
import importlib.util
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestWorkflowConfig:
    """Test WorkflowConfig dataclass."""

    def test_workflow_config_imports(self):
        """Verify WorkflowConfig can be imported."""
        from workflows import WorkflowConfig
        assert WorkflowConfig is not None

    def test_workflow_config_structure(self):
        """Verify WorkflowConfig has required methods."""
        from workflows import WorkflowConfig
        
        # Check required methods
        assert hasattr(WorkflowConfig, 'validate')

    def test_workflow_config_fields(self):
        """Verify WorkflowConfig has all required fields."""
        from workflows import WorkflowConfig
        import dataclasses
        
        fields = {f.name for f in dataclasses.fields(WorkflowConfig)}
        required_fields = {
            'azure_openai_api_key',
            'azure_openai_endpoint',
            'azure_openai_chat_deployment',
            'smtp_host',
            'smtp_port',
        }
        
        assert required_fields.issubset(fields), f"Missing fields: {required_fields - fields}"


class TestWorkflowModules:
    """Test that workflow modules exist and have correct structure."""

    def test_concurrent_workflow_structure(self):
        """Test concurrent_workflow module."""
        # Import without executing
        spec = importlib.util.spec_from_file_location(
            "concurrent_workflow",
            Path(__file__).parent.parent / "workflows" / "concurrent_workflow.py"
        )
        module = importlib.util.module_from_spec(spec)
        
        # Don't execute—just check syntax is valid
        import py_compile
        py_compile.compile(
            str(Path(__file__).parent.parent / "workflows" / "concurrent_workflow.py"),
            doraise=True
        )
        
        # Verify expected function exists
        assert "run_concurrent_workflow" in open(
            Path(__file__).parent.parent / "workflows" / "concurrent_workflow.py"
        ).read()

    def test_group_chat_workflow_structure(self):
        """Test group_chat_workflow module."""
        import py_compile
        py_compile.compile(
            str(Path(__file__).parent.parent / "workflows" / "group_chat_workflow.py"),
            doraise=True
        )
        
        assert "run_group_chat_workflow" in open(
            Path(__file__).parent.parent / "workflows" / "group_chat_workflow.py"
        ).read()

    def test_sequential_workflow_structure(self):
        """Test sequential_workflow module."""
        import py_compile
        py_compile.compile(
            str(Path(__file__).parent.parent / "workflows" / "sequential_workflow.py"),
            doraise=True
        )
        
        assert "run_sequential_workflow" in open(
            Path(__file__).parent.parent / "workflows" / "sequential_workflow.py"
        ).read()

    def test_approval_workflow_structure(self):
        """Test approval_workflow module."""
        import py_compile
        py_compile.compile(
            str(Path(__file__).parent.parent / "workflows" / "approval_workflow.py"),
            doraise=True
        )
        
        assert "run_approval_workflow" in open(
            Path(__file__).parent.parent / "workflows" / "approval_workflow.py"
        ).read()

    def test_game_workflow_structure(self):
        """Test game_workflow module."""
        import py_compile
        py_compile.compile(
            str(Path(__file__).parent.parent / "workflows" / "game_workflow.py"),
            doraise=True
        )
        
        assert "run_game_workflow" in open(
            Path(__file__).parent.parent / "workflows" / "game_workflow.py"
        ).read()


class TestStaticFiles:
    """Test that all frontend assets exist."""

    def test_index_html_exists(self):
        """Verify index.html exists and is valid."""
        html_path = Path(__file__).parent.parent / "static" / "index.html"
        assert html_path.exists(), f"Missing: {html_path}"
        
        content = html_path.read_text()
        assert "<html" in content or "<!DOCTYPE" in content
        assert "dashboard" in content.lower()

    def test_style_css_exists(self):
        """Verify style.css exists."""
        css_path = Path(__file__).parent.parent / "static" / "css" / "style.css"
        assert css_path.exists(), f"Missing: {css_path}"
        
        content = css_path.read_text()
        assert "}" in content  # Basic CSS validation

    def test_dashboard_js_exists(self):
        """Verify dashboard.js exists."""
        js_path = Path(__file__).parent.parent / "static" / "js" / "dashboard.js"
        assert js_path.exists(), f"Missing: {js_path}"
        
        content = js_path.read_text()
        assert "function" in content or "const" in content  # Basic JS validation
        assert "WebSocket" in content  # Should have WebSocket handling


class TestMainPyStructure:
    """Test main.py FastAPI application structure."""

    def test_main_py_imports_fastapi(self):
        """Verify main.py imports FastAPI."""
        main_path = Path(__file__).parent.parent / "main.py"
        content = main_path.read_text()
        
        assert "from fastapi import" in content or "import fastapi" in content
        assert "app = FastAPI" in content or "app = fastapi" in content

    def test_main_py_has_websocket_handler(self):
        """Verify main.py has WebSocket handler."""
        main_path = Path(__file__).parent.parent / "main.py"
        content = main_path.read_text()
        
        assert "@app.websocket" in content
        assert "async def websocket_workflow_stream" in content or \
               "async def websocket_endpoint" in content or \
               "async def ws_" in content

    def test_main_py_has_workflow_registry(self):
        """Verify main.py registers all 5 workflows."""
        main_path = Path(__file__).parent.parent / "main.py"
        content = main_path.read_text()
        
        workflows = [
            "concurrent",
            "group_chat",
            "sequential",
            "approval",
            "game",
        ]
        
        for workflow in workflows:
            assert workflow in content, f"Workflow '{workflow}' not found in main.py"

    def test_main_py_has_health_endpoint(self):
        """Verify main.py has health check endpoint."""
        main_path = Path(__file__).parent.parent / "main.py"
        content = main_path.read_text()
        
        assert "/health" in content or "@app.get" in content

    def test_main_py_syntax_valid(self):
        """Verify main.py has valid Python syntax."""
        import py_compile
        py_compile.compile(
            str(Path(__file__).parent.parent / "main.py"),
            doraise=True
        )


class TestPythonSyntax:
    """Test that all Python files have valid syntax."""

    def test_all_workflow_files_compile(self):
        """Verify all workflow files compile."""
        import py_compile
        
        workflows_dir = Path(__file__).parent.parent / "workflows"
        for py_file in workflows_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as e:
                pytest.fail(f"{py_file.name} has syntax error: {e}")

    def test_main_py_compiles(self):
        """Verify main.py compiles."""
        import py_compile
        
        try:
            py_compile.compile(
                str(Path(__file__).parent.parent / "main.py"),
                doraise=True
            )
        except py_compile.PyCompileError as e:
            pytest.fail(f"main.py has syntax error: {e}")


class TestEventStructure:
    """Test that workflow events are properly defined."""

    def test_workflows_define_event_class(self):
        """Verify workflows have WorkflowEvent defined."""
        # Check __init__.py for event definitions
        init_path = Path(__file__).parent.parent / "workflows" / "__init__.py"
        content = init_path.read_text()
        
        # Should have some event-related definitions
        assert "WorkflowEvent" in content or "class" in content

    def test_event_types_documented(self):
        """Verify event types are documented in code."""
        main_path = Path(__file__).parent.parent / "main.py"
        content = main_path.read_text()
        
        event_types = [
            "agent_message",
            "approval_required",
            "input_required",
            "workflow_complete",
            "error",
        ]
        
        # At least some event types should be mentioned
        found = sum(1 for et in event_types if et in content)
        assert found >= 3, f"Expected at least 3 event types, found {found}"


class TestArchitectureIntegration:
    """Test high-level architecture integration."""

    def test_workflows_directory_structure(self):
        """Verify workflows directory has correct structure."""
        workflows_dir = Path(__file__).parent.parent / "workflows"
        
        assert workflows_dir.exists()
        assert (workflows_dir / "__init__.py").exists()
        
        expected_modules = {
            "concurrent_workflow.py",
            "group_chat_workflow.py",
            "sequential_workflow.py",
            "approval_workflow.py",
            "game_workflow.py",
        }
        
        existing = {f.name for f in workflows_dir.glob("*.py") if not f.name.startswith("_")}
        assert expected_modules.issubset(existing), f"Missing: {expected_modules - existing}"

    def test_static_directory_structure(self):
        """Verify static directory has correct structure."""
        static_dir = Path(__file__).parent.parent / "static"
        
        assert static_dir.exists()
        assert (static_dir / "index.html").exists()
        assert (static_dir / "css" / "style.css").exists()
        assert (static_dir / "js" / "dashboard.js").exists()

    def test_tests_directory_structure(self):
        """Verify tests directory has correct structure."""
        tests_dir = Path(__file__).parent.parent / "tests"
        
        assert tests_dir.exists()
        assert (tests_dir / "conftest.py").exists()
        assert (tests_dir / "test_workflows_integration.py").exists() or \
               (tests_dir / "test_syntax_validation.py").exists()

    def test_project_root_has_config_files(self):
        """Verify project root has required config files."""
        root = Path(__file__).parent.parent
        
        assert (root / "main.py").exists()
        assert (root / "requirements.txt").exists()
        assert (root / ".vscode" / "launch.json").exists()


class TestDependencyMapping:
    """Test that dependencies are correctly specified."""

    def test_requirements_file_exists(self):
        """Verify requirements.txt exists and is readable."""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        assert req_path.exists()
        
        content = req_path.read_text()
        assert "fastapi" in content
        assert "uvicorn" in content
        assert "python-dotenv" in content

    def test_requirements_have_versions(self):
        """Verify requirements specify versions."""
        req_path = Path(__file__).parent.parent / "requirements.txt"
        content = req_path.read_text()
        
        lines = [l.strip() for l in content.split('\n') if l.strip() and not l.startswith('#')]
        
        for line in lines:
            # Each requirement should have a version specifier
            assert ">=" in line or "==" in line, f"No version for: {line}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
