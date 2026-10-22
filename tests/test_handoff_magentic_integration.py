#!/usr/bin/env python3
"""
Integration Tests for Handoff and Magentic Workflows

Validates both new Agent Framework orchestration patterns with real Azure OpenAI.

Run with: pytest tests/test_handoff_magentic_integration.py -v --timeout=180
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

import pytest
from dotenv import load_dotenv

# Setup path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from workflows import WorkflowConfig
from workflows.handoff_workflow import run_handoff_workflow
from workflows.magentic_workflow import run_magentic_workflow

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class WorkflowTestResult:
    """Result from running a workflow test."""
    workflow_id: str
    test_name: str
    success: bool
    event_count: int
    event_types: List[str]
    duration_seconds: float
    error: str = ""
    events: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.events is None:
            self.events = []


class TestHandoffWorkflow:
    """Integration tests for Handoff workflow."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test configuration."""
        self.config = WorkflowConfig.from_env()
        error = self.config.validate()
        if error:
            pytest.skip(f"Config validation failed: {error}")
        logger.info("✓ Config validated for Handoff tests")

    @pytest.mark.asyncio
    async def test_handoff_customer_service_only(self):
        """Test simple customer support request (no escalation)."""
        logger.info("\n--- Testing: Customer Service Only ---")
        
        topic = "I forgot my password and can't log in"
        events = []
        start_time = datetime.now()
        
        try:
            async for event in run_handoff_workflow(self.config, topic):
                events.append(event)
                logger.info(f"  Event: {event.type} - {event.description[:60]}")
                
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"✓ Test passed ({len(events)} events, {duration:.1f}s)")
            
            # Validation
            assert len(events) > 0, "No events received"
            assert events[-1].type == "workflow_complete", "Should end with workflow_complete"
            assert any(e.type == "agent_message" for e in events), "Should have agent messages"
            
        except Exception as e:
            logger.error(f"✗ Test failed: {str(e)}")
            raise

    @pytest.mark.asyncio
    async def test_handoff_technical_escalation(self):
        """Test request requiring technical expert."""
        logger.info("\n--- Testing: Technical Escalation ---")
        
        topic = "My API integration keeps crashing with error code 502. The endpoint returns malformed JSON."
        events = []
        start_time = datetime.now()
        
        try:
            async for event in run_handoff_workflow(self.config, topic):
                events.append(event)
                logger.info(f"  Event: {event.type} - {event.description[:60]}")
                
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"✓ Test passed ({len(events)} events, {duration:.1f}s)")
            
            # Validation
            assert len(events) > 0, "No events received"
            assert events[-1].type == "workflow_complete", "Should end with workflow_complete"
            # Should have multiple agent interactions (at least customer service + technical expert)
            agent_messages = [e for e in events if e.type == "agent_message"]
            assert len(agent_messages) >= 2, f"Should have ≥2 agent messages for escalation, got {len(agent_messages)}"
            
        except Exception as e:
            logger.error(f"✗ Test failed: {str(e)}")
            raise

    @pytest.mark.asyncio
    async def test_handoff_manager_escalation(self):
        """Test request requiring management escalation."""
        logger.info("\n--- Testing: Manager Escalation ---")
        
        topic = "We need to escalate this to senior management. This is a critical contract renewal issue that affects billing."
        events = []
        start_time = datetime.now()
        
        try:
            async for event in run_handoff_workflow(self.config, topic):
                events.append(event)
                logger.info(f"  Event: {event.type} - {event.description[:60]}")
                
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"✓ Test passed ({len(events)} events, {duration:.1f}s)")
            
            # Validation
            assert len(events) > 0, "No events received"
            assert events[-1].type == "workflow_complete", "Should end with workflow_complete"
            agent_messages = [e for e in events if e.type == "agent_message"]
            assert len(agent_messages) >= 2, f"Should have ≥2 agent messages for escalation, got {len(agent_messages)}"
            
        except Exception as e:
            logger.error(f"✗ Test failed: {str(e)}")
            raise

    @pytest.mark.asyncio
    async def test_handoff_all_phases(self):
        """Test complex scenario with technical + escalation keywords."""
        logger.info("\n--- Testing: All Phases ---")
        
        topic = "We have a critical technical bug in our payment API that's causing crashes. This is urgent and needs immediate escalation for billing impact review."
        events = []
        start_time = datetime.now()
        
        try:
            async for event in run_handoff_workflow(self.config, topic):
                events.append(event)
                logger.info(f"  Event: {event.type} - {event.description[:60]}")
                
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"✓ Test passed ({len(events)} events, {duration:.1f}s)")
            
            # Validation
            assert len(events) > 0, "No events received"
            assert events[-1].type == "workflow_complete", "Should end with workflow_complete"
            agent_messages = [e for e in events if e.type == "agent_message"]
            assert len(agent_messages) >= 2, f"Should have ≥2 agent messages, got {len(agent_messages)}"
            
        except Exception as e:
            logger.error(f"✗ Test failed: {str(e)}")
            raise


class TestMagenticWorkflow:
    """Integration tests for Magentic workflow."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test configuration."""
        self.config = WorkflowConfig.from_env()
        error = self.config.validate()
        if error:
            pytest.skip(f"Config validation failed: {error}")
        logger.info("✓ Config validated for Magentic tests")

    @pytest.mark.asyncio
    async def test_magentic_research_task(self):
        """Test research-focused task."""
        logger.info("\n--- Testing: Research Task ---")
        
        topic = "Research the top 3 emerging trends in cloud AI infrastructure for 2025"
        events = []
        start_time = datetime.now()
        
        try:
            async for event in run_magentic_workflow(self.config, topic):
                events.append(event)
                logger.info(f"  Event: {event.type} - {event.description[:60]}")
                
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"✓ Test passed ({len(events)} events, {duration:.1f}s)")
            
            # Validation
            assert len(events) > 0, "No events received"
            assert events[-1].type == "workflow_complete", "Should end with workflow_complete"
            assert any(e.type == "agent_message" for e in events), "Should have agent messages"
            
        except Exception as e:
            logger.error(f"✗ Test failed: {str(e)}")
            raise

    @pytest.mark.asyncio
    async def test_magentic_analysis_task(self):
        """Test analysis task with evaluation."""
        logger.info("\n--- Testing: Analysis Task ---")
        
        topic = "Analyze the pros and cons of Agent Framework vs LangChain for enterprise AI applications"
        events = []
        start_time = datetime.now()
        
        try:
            async for event in run_magentic_workflow(self.config, topic):
                events.append(event)
                logger.info(f"  Event: {event.type} - {event.description[:60]}")
                
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"✓ Test passed ({len(events)} events, {duration:.1f}s)")
            
            # Validation
            assert len(events) > 0, "No events received"
            assert events[-1].type == "workflow_complete", "Should end with workflow_complete"
            
        except Exception as e:
            logger.error(f"✗ Test failed: {str(e)}")
            raise

    @pytest.mark.asyncio
    async def test_magentic_complex_task(self):
        """Test complex task requiring multiple analysis phases."""
        logger.info("\n--- Testing: Complex Task ---")
        
        topic = "Create a comprehensive migration strategy for moving a legacy monolithic ERP system from on-premises to Azure cloud with zero downtime"
        events = []
        start_time = datetime.now()
        
        try:
            async for event in run_magentic_workflow(self.config, topic):
                events.append(event)
                logger.info(f"  Event: {event.type} - {event.description[:60]}")
                
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"✓ Test passed ({len(events)} events, {duration:.1f}s)")
            
            # Validation
            assert len(events) > 0, "No events received"
            assert events[-1].type == "workflow_complete", "Should end with workflow_complete"
            
        except Exception as e:
            logger.error(f"✗ Test failed: {str(e)}")
            raise

    @pytest.mark.asyncio
    async def test_magentic_iteration_control(self):
        """Test that iteration control respects MAX_ITERATIONS."""
        logger.info("\n--- Testing: Iteration Control ---")
        
        topic = "Provide a detailed security assessment of multi-tenant SaaS architecture"
        events = []
        start_time = datetime.now()
        
        try:
            async for event in run_magentic_workflow(self.config, topic):
                events.append(event)
                logger.info(f"  Event: {event.type} - {event.description[:60]}")
                
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"✓ Test passed ({len(events)} events, {duration:.1f}s)")
            
            # Validation
            assert len(events) > 0, "No events received"
            assert events[-1].type == "workflow_complete", "Should end with workflow_complete"
            # Should not hang (implies iteration control works)
            assert duration < 300, f"Test took too long ({duration}s), may indicate infinite loop"
            
        except Exception as e:
            logger.error(f"✗ Test failed: {str(e)}")
            raise


class TestWorkflowEventStructure:
    """Tests that validate event structure and WebSocket compatibility."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test configuration."""
        self.config = WorkflowConfig.from_env()
        error = self.config.validate()
        if error:
            pytest.skip(f"Config validation failed: {error}")

    @pytest.mark.asyncio
    async def test_handoff_event_format(self):
        """Validate Handoff workflow produces correctly formatted events."""
        logger.info("\n--- Testing: Handoff Event Format ---")
        
        topic = "I need help with my account"
        event_types = []
        
        try:
            async for event in run_handoff_workflow(self.config, topic):
                # Validate event structure
                assert hasattr(event, 'type'), "Event missing 'type' attribute"
                assert hasattr(event, 'description'), "Event missing 'description' attribute"
                event_types.append(event.type)
                
            logger.info(f"✓ Event types received: {event_types}")
            assert len(event_types) > 0, "No events produced"
            assert event_types[-1] == "workflow_complete", "Last event should be workflow_complete"
            
        except Exception as e:
            logger.error(f"✗ Test failed: {str(e)}")
            raise

    @pytest.mark.asyncio
    async def test_magentic_event_format(self):
        """Validate Magentic workflow produces correctly formatted events."""
        logger.info("\n--- Testing: Magentic Event Format ---")
        
        topic = "Analyze this topic"
        event_types = []
        
        try:
            async for event in run_magentic_workflow(self.config, topic):
                # Validate event structure
                assert hasattr(event, 'type'), "Event missing 'type' attribute"
                assert hasattr(event, 'description'), "Event missing 'description' attribute"
                event_types.append(event.type)
                
            logger.info(f"✓ Event types received: {event_types}")
            assert len(event_types) > 0, "No events produced"
            assert event_types[-1] == "workflow_complete", "Last event should be workflow_complete"
            
        except Exception as e:
            logger.error(f"✗ Test failed: {str(e)}")
            raise


if __name__ == "__main__":
    # Run with: python -m pytest tests/test_handoff_magentic_integration.py -v --timeout=180
    pytest.main([__file__, "-v", "--timeout=180"])
