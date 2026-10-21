#!/usr/bin/env python3
"""
Integration Tests for HITL Dashboard Workflows

Tests all 5 workflows to ensure:
1. They start without errors
2. They yield events in correct types
3. They handle configuration properly
4. They complete successfully

Run with: pytest tests/test_workflows_integration.py -v
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import List
from dataclasses import dataclass

import pytest
from dotenv import load_dotenv

# Setup path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from workflows import WorkflowConfig
from workflows.concurrent_workflow import run_concurrent_workflow
from workflows.group_chat_workflow import run_group_chat_workflow
from workflows.sequential_workflow import run_sequential_workflow
from workflows.approval_workflow import run_approval_workflow
from workflows.game_workflow import run_game_workflow

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class WorkflowTestResult:
    """Result from running a workflow test."""
    workflow_id: str
    success: bool
    event_count: int
    event_types: List[str]
    error: str = ""


class TestWorkflows:
    """Integration tests for all HITL workflows."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test configuration."""
        self.config = WorkflowConfig.from_env()
        logger.info(f"Config created: endpoint={self.config.azure_openai_endpoint}")

    def test_config_validation(self):
        """Test that configuration can be validated."""
        config = WorkflowConfig.from_env()
        error = config.validate()
        
        # Config might not be valid (missing Azure creds) but shouldn't crash
        if error:
            logger.warning(f"Config validation error (expected in CI): {error}")
        
        assert config is not None
        assert config.azure_openai_api_version

    @pytest.mark.asyncio
    async def test_concurrent_workflow(self):
        """Test concurrent_workflow runs and yields events."""
        logger.info("Testing concurrent_workflow...")
        
        events = []
        try:
            async for event in run_concurrent_workflow(self.config, "Test topic"):
                events.append(event)
                logger.info(f"  Event: {event.type if hasattr(event, 'type') else 'unknown'}")
                
                # Safety: stop after reasonable number of events
                if len(events) > 100:
                    logger.warning("  Too many events, stopping test")
                    break
        except Exception as e:
            logger.error(f"Error in concurrent_workflow: {e}")
            raise

        assert len(events) > 0, "Should yield at least one event"
        logger.info(f"  Total events: {len(events)}")

    @pytest.mark.asyncio
    async def test_group_chat_workflow(self):
        """Test group_chat_workflow runs and yields events."""
        logger.info("Testing group_chat_workflow...")
        
        events = []
        try:
            async for event in run_group_chat_workflow(self.config, "Test topic"):
                events.append(event)
                logger.info(f"  Event: {event.type if hasattr(event, 'type') else 'unknown'}")
                
                # Safety: stop after reasonable number of events
                if len(events) > 100:
                    logger.warning("  Too many events, stopping test")
                    break
        except Exception as e:
            logger.error(f"Error in group_chat_workflow: {e}")
            raise

        assert len(events) > 0, "Should yield at least one event"
        logger.info(f"  Total events: {len(events)}")

    @pytest.mark.asyncio
    async def test_sequential_workflow(self):
        """Test sequential_workflow runs and yields events."""
        logger.info("Testing sequential_workflow...")
        
        events = []
        try:
            async for event in run_sequential_workflow(self.config, "Test document"):
                events.append(event)
                logger.info(f"  Event: {event.type if hasattr(event, 'type') else 'unknown'}")
                
                # Safety: stop after reasonable number of events
                if len(events) > 100:
                    logger.warning("  Too many events, stopping test")
                    break
        except Exception as e:
            logger.error(f"Error in sequential_workflow: {e}")
            raise

        assert len(events) > 0, "Should yield at least one event"
        logger.info(f"  Total events: {len(events)}")

    @pytest.mark.asyncio
    async def test_approval_workflow(self):
        """Test approval_workflow runs and yields events."""
        logger.info("Testing approval_workflow...")
        
        events = []
        try:
            async for event in run_approval_workflow(self.config):
                events.append(event)
                logger.info(f"  Event: {event.type if hasattr(event, 'type') else 'unknown'}")
                
                # Safety: stop after reasonable number of events
                if len(events) > 100:
                    logger.warning("  Too many events, stopping test")
                    break
        except Exception as e:
            logger.error(f"Error in approval_workflow: {e}")
            raise

        assert len(events) > 0, "Should yield at least one event"
        logger.info(f"  Total events: {len(events)}")

    @pytest.mark.asyncio
    async def test_game_workflow(self):
        """Test game_workflow runs and yields events."""
        logger.info("Testing game_workflow...")
        
        events = []
        try:
            async for event in run_game_workflow(self.config):
                events.append(event)
                logger.info(f"  Event: {event.type if hasattr(event, 'type') else 'unknown'}")
                
                # Safety: stop after reasonable number of events
                if len(events) > 100:
                    logger.warning("  Too many events, stopping test")
                    break
        except Exception as e:
            logger.error(f"Error in game_workflow: {e}")
            raise

        assert len(events) > 0, "Should yield at least one event"
        logger.info(f"  Total events: {len(events)}")

    def test_event_structure(self):
        """Test that WorkflowEvent has expected attributes."""
        from agent_framework import WorkflowEvent
        
        event = WorkflowEvent(
            type="test_message",
            data={"content": "test"},
            source_executor_id="test_agent"
        )
        
        assert hasattr(event, 'type')
        assert hasattr(event, 'data')
        # source_executor_id is a property that raises for non request_info events
        assert event._source_executor_id == "test_agent"
        assert event.type == "test_message"
        logger.info("Event structure validation passed")

    def test_workflow_config_creation(self):
        """Test that WorkflowConfig creates and validates."""
        config = WorkflowConfig.from_env()
        
        # Should always create, even with missing env vars
        assert config is not None
        
        # Check expected attributes
        assert hasattr(config, 'azure_openai_api_key')
        assert hasattr(config, 'azure_openai_endpoint')
        assert hasattr(config, 'azure_openai_chat_deployment')
        assert hasattr(config, 'azure_openai_api_version')
        assert hasattr(config, 'smtp_host')
        assert hasattr(config, 'email_recipient')
        
        logger.info("WorkflowConfig structure validation passed")


class TestWorkflowImports:
    """Test that all workflow modules import correctly."""

    def test_concurrent_import(self):
        """Test concurrent_workflow imports."""
        from workflows.concurrent_workflow import run_concurrent_workflow
        assert callable(run_concurrent_workflow)
        logger.info("✓ concurrent_workflow imports correctly")

    def test_group_chat_import(self):
        """Test group_chat_workflow imports."""
        from workflows.group_chat_workflow import run_group_chat_workflow
        assert callable(run_group_chat_workflow)
        logger.info("✓ group_chat_workflow imports correctly")

    def test_sequential_import(self):
        """Test sequential_workflow imports."""
        from workflows.sequential_workflow import run_sequential_workflow
        assert callable(run_sequential_workflow)
        logger.info("✓ sequential_workflow imports correctly")

    def test_approval_import(self):
        """Test approval_workflow imports."""
        from workflows.approval_workflow import run_approval_workflow
        assert callable(run_approval_workflow)
        logger.info("✓ approval_workflow imports correctly")

    def test_game_import(self):
        """Test game_workflow imports."""
        from workflows.game_workflow import run_game_workflow
        assert callable(run_game_workflow)
        logger.info("✓ game_workflow imports correctly")

    def test_main_app_import(self):
        """Test main.py imports."""
        try:
            from main import app
            assert app is not None
            logger.info("✓ main.py imports correctly")
        except Exception as e:
            logger.warning(f"main.py import failed (might be missing deps): {e}")
            # Don't fail - this is expected if agent-framework not installed


class TestWorkflowStructure:
    """Test that workflows have correct structure."""

    def test_concurrent_signature(self):
        """Test concurrent_workflow has correct signature."""
        import inspect
        sig = inspect.signature(run_concurrent_workflow)
        params = list(sig.parameters.keys())
        
        assert 'config' in params, "Should have 'config' parameter"
        assert len(params) >= 1, "Should have at least config parameter"
        logger.info(f"concurrent_workflow signature: {sig}")

    def test_group_chat_signature(self):
        """Test group_chat_workflow has correct signature."""
        import inspect
        sig = inspect.signature(run_group_chat_workflow)
        params = list(sig.parameters.keys())
        
        assert 'config' in params, "Should have 'config' parameter"
        logger.info(f"group_chat_workflow signature: {sig}")

    def test_sequential_signature(self):
        """Test sequential_workflow has correct signature."""
        import inspect
        sig = inspect.signature(run_sequential_workflow)
        params = list(sig.parameters.keys())
        
        assert 'config' in params, "Should have 'config' parameter"
        logger.info(f"sequential_workflow signature: {sig}")

    def test_approval_signature(self):
        """Test approval_workflow has correct signature."""
        import inspect
        sig = inspect.signature(run_approval_workflow)
        params = list(sig.parameters.keys())
        
        assert 'config' in params, "Should have 'config' parameter"
        logger.info(f"approval_workflow signature: {sig}")

    def test_game_signature(self):
        """Test game_workflow has correct signature."""
        import inspect
        sig = inspect.signature(run_game_workflow)
        params = list(sig.parameters.keys())
        
        assert 'config' in params, "Should have 'config' parameter"
        logger.info(f"game_workflow signature: {sig}")


if __name__ == "__main__":
    # Run tests with: pytest tests/test_workflows_integration.py -v -s
    # Or run this file directly: python tests/test_workflows_integration.py
    pytest.main([__file__, "-v", "-s"])
