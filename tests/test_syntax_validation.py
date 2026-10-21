#!/usr/bin/env python3
"""
Quick Syntax and Import Validation Tests

These tests run first and catch basic issues:
- Import errors
- Syntax errors
- Missing dependencies
- Configuration structure

Run with: pytest tests/test_syntax_validation.py -v
"""

import logging
from pathlib import Path
import sys

import pytest

# Setup path
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)


class TestSyntaxValidation:
    """Basic syntax and import validation."""

    def test_workflows_package(self):
        """Test workflows package imports."""
        try:
            import workflows
            assert workflows is not None
            logger.info("✓ workflows package imports")
        except Exception as e:
            pytest.fail(f"Failed to import workflows: {e}")

    def test_workflow_config(self):
        """Test WorkflowConfig imports and can be instantiated."""
        try:
            from workflows import WorkflowConfig
            config = WorkflowConfig.from_env()
            assert config is not None
            logger.info("✓ WorkflowConfig imports and instantiates")
        except Exception as e:
            pytest.fail(f"Failed to create WorkflowConfig: {e}")

    def test_main_py_syntax(self):
        """Test main.py has valid Python syntax."""
        import py_compile
        import tempfile
        
        main_path = Path(__file__).parent.parent / "main.py"
        try:
            py_compile.compile(str(main_path), doraise=True)
            logger.info("✓ main.py has valid syntax")
        except py_compile.PyCompileError as e:
            pytest.fail(f"main.py syntax error: {e}")

    def test_all_workflows_syntax(self):
        """Test all workflow files have valid Python syntax."""
        import py_compile
        
        workflows_dir = Path(__file__).parent.parent / "workflows"
        for py_file in workflows_dir.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            
            try:
                py_compile.compile(str(py_file), doraise=True)
                logger.info(f"✓ {py_file.name} has valid syntax")
            except py_compile.PyCompileError as e:
                pytest.fail(f"{py_file.name} syntax error: {e}")

    def test_concurrent_workflow_structure(self):
        """Test concurrent_workflow module structure."""
        try:
            from workflows.concurrent_workflow import run_concurrent_workflow
            assert callable(run_concurrent_workflow)
            logger.info("✓ concurrent_workflow has run_concurrent_workflow")
        except Exception as e:
            pytest.fail(f"concurrent_workflow structure invalid: {e}")

    def test_group_chat_workflow_structure(self):
        """Test group_chat_workflow module structure."""
        try:
            from workflows.group_chat_workflow import run_group_chat_workflow
            assert callable(run_group_chat_workflow)
            logger.info("✓ group_chat_workflow has run_group_chat_workflow")
        except Exception as e:
            pytest.fail(f"group_chat_workflow structure invalid: {e}")

    def test_sequential_workflow_structure(self):
        """Test sequential_workflow module structure."""
        try:
            from workflows.sequential_workflow import run_sequential_workflow
            assert callable(run_sequential_workflow)
            logger.info("✓ sequential_workflow has run_sequential_workflow")
        except Exception as e:
            pytest.fail(f"sequential_workflow structure invalid: {e}")

    def test_approval_workflow_structure(self):
        """Test approval_workflow module structure."""
        try:
            from workflows.approval_workflow import run_approval_workflow
            assert callable(run_approval_workflow)
            logger.info("✓ approval_workflow has run_approval_workflow")
        except Exception as e:
            pytest.fail(f"approval_workflow structure invalid: {e}")

    def test_game_workflow_structure(self):
        """Test game_workflow module structure."""
        try:
            from workflows.game_workflow import run_game_workflow
            assert callable(run_game_workflow)
            logger.info("✓ game_workflow has run_game_workflow")
        except Exception as e:
            pytest.fail(f"game_workflow structure invalid: {e}")

    def test_static_files_exist(self):
        """Test that required static files exist."""
        static_dir = Path(__file__).parent.parent / "static"
        
        required_files = [
            "index.html",
            "css/style.css",
            "js/dashboard.js",
        ]
        
        for file_path in required_files:
            full_path = static_dir / file_path
            if not full_path.exists():
                pytest.fail(f"Missing static file: {file_path}")
            logger.info(f"✓ static/{file_path} exists")

    def test_workflows_init_structure(self):
        """Test workflows/__init__.py has WorkflowConfig."""
        try:
            from workflows import WorkflowConfig
            
            # Check key methods
            assert hasattr(WorkflowConfig, 'from_env')
            assert hasattr(WorkflowConfig, 'validate')
            
            logger.info("✓ WorkflowConfig has from_env and validate methods")
        except Exception as e:
            pytest.fail(f"WorkflowConfig structure invalid: {e}")


class TestDependencies:
    """Check critical dependencies."""

    def test_fastapi_available(self):
        """Test FastAPI is available."""
        try:
            import fastapi
            logger.info(f"✓ FastAPI {fastapi.__version__} available")
        except ImportError:
            pytest.skip("FastAPI not installed (will fail during F5 launch)")

    def test_uvicorn_available(self):
        """Test Uvicorn is available."""
        try:
            import uvicorn
            logger.info(f"✓ Uvicorn {uvicorn.__version__} available")
        except ImportError:
            pytest.skip("Uvicorn not installed (will fail during F5 launch)")

    def test_dotenv_available(self):
        """Test python-dotenv is available."""
        try:
            import dotenv
            logger.info("✓ python-dotenv available")
        except ImportError:
            pytest.skip("python-dotenv not installed")

    def test_agent_framework_available(self):
        """Test agent-framework is available."""
        try:
            import agent_framework
            logger.info("✓ agent-framework available")
        except ImportError:
            pytest.skip("agent-framework not installed (runtime dependency)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
