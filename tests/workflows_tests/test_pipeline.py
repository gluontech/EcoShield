
import pytest
import asyncio
from typing import Dict, Any
from src.workflows.pipeline import Pipeline, PipelineStep

# Mock steps
async def step_one(data: Dict[str, Any]) -> Dict[str, Any]:
    data["step_one"] = "done"
    return data

async def step_two(data: Dict[str, Any]) -> Dict[str, Any]:
    data["step_two"] = "done"
    data["count"] = data.get("count", 0) + 1
    return data

async def step_fail(data: Dict[str, Any]) -> Dict[str, Any]:
    raise ValueError("Step failed intentionally")

@pytest.mark.asyncio
async def test_pipeline_execution_order():
    """Verify strictly sequential execution."""
    pipeline = Pipeline(
        name="TestPipeline",
        steps=[
            PipelineStep(name="one", executor=step_one, description="First"),
            PipelineStep(name="two", executor=step_two, description="Second"),
        ]
    )
    
    initial_data = {"start": True}
    result = await pipeline.run(initial_data)
    
    assert result["start"] is True
    assert result["step_one"] == "done"
    assert result["step_two"] == "done"
    assert result["count"] == 1

@pytest.mark.asyncio
async def test_pipeline_error_propagation():
    """Verify pipeline stops on error and raises exception."""
    pipeline = Pipeline(
        name="FailPipeline",
        steps=[
            PipelineStep(name="one", executor=step_one),
            PipelineStep(name="fail", executor=step_fail),
            PipelineStep(name="two", executor=step_two), # Should not run
        ]
    )
    
    with pytest.raises(ValueError, match="Step failed intentionally"):
        await pipeline.run({})

@pytest.mark.asyncio
async def test_pipeline_data_flow():
    """Verify data is passed between steps and modified."""
    
    async def adder(data):
        data["sum"] = data.get("sum", 0) + 10
        return data
        
    pipeline = Pipeline(
        name="DataFlow",
        steps=[
            PipelineStep(name="add1", executor=adder),
            PipelineStep(name="add2", executor=adder),
        ]
    )
    
    result = await pipeline.run({"sum": 5})
    assert result["sum"] == 25  # 5 + 10 + 10
