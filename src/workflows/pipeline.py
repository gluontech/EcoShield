"""
Lightweight deterministic pipeline runner — replaces Agno Workflow.
Provides step-by-step async execution with error handling and result collection.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """Result of a single pipeline step execution."""
    name: str
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class PipelineStep:
    """Definition of a pipeline step."""
    name: str
    executor: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]
    description: str = ""


class Pipeline:
    """
    Deterministic step-by-step async pipeline.
    
    Executes steps in order. Each step receives the dictionary returned by the
    previous step (or the initial input for the first step).
    """

    def __init__(self, name: str, steps: List[PipelineStep]):
        self.name = name
        self.steps = steps

    async def run(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the pipeline steps sequentially.
        
        Args:
            input_data: Initial context dictionary.
            
        Returns:
            Final context dictionary after all steps have executed.
            
        Raises:
            Exception: If any step fails, the exception is propagated.
        """
        data = input_data.copy()
        
        logger.info(f"[{self.name}] Starting pipeline execution with {len(self.steps)} steps")
        
        for i, step in enumerate(self.steps):
            logger.info(f"[{self.name}] Step {i+1}/{len(self.steps)}: {step.name}")
            try:
                # Execute step
                step_result = await step.executor(data)
                
                # Update context with result
                # Note: We expect steps to return the updated context dict
                if isinstance(step_result, dict):
                    data = step_result
                else:
                    logger.warning(
                        f"[{self.name}] Step '{step.name}' did not return a dict. "
                        f"Type: {type(step_result)}"
                    )
                    
            except Exception as e:
                logger.error(f"[{self.name}] Step '{step.name}' failed: {str(e)}")
                raise e
                
        logger.info(f"[{self.name}] Pipeline execution completed successfully")
        return data
