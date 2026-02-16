
import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from src.workflows.hazard_workflow import run_hazard_assessment
from src.core.models import FullRiskProfile

@pytest.mark.asyncio
async def test_hazard_workflow_end_to_end():
    """
    Verify the full hazard workflow executes all steps and returns a FullRiskProfile.
    We mock the executors in the global hazard_pipeline directly.
    """
    from src.workflows.hazard_workflow import hazard_pipeline
    
    # Mock return values for each step
    mock_asset = {"building_cluster": None, "building_surfaces": {}}
    mock_chronic = {"chronic_results": {"subsidence": {}}, "adjusted_surface": {}}
    mock_cyclone = {"cyclone_result": {}, "cyclone_params": {}}
    mock_acute = {"hazard_results_by_rp": {100: {}}, "acute_results": {}}
    mock_structure = {"structure_results": [], "portfolio_summary": None}
    
    # Construct a minimal FullRiskProfile for verification
    from src.core.models import FullRiskProfile, CompositeRiskResult, SurfaceAdjustments, RiskTier, ConfidenceLevel, Location
    
    dummy_profile = FullRiskProfile(
        location=Location(lat=10.0, lon=106.0),
        city="hcmc",
        assessment_id="test",
        acute_risk=CompositeRiskResult(
            event_type="acute", composite_score=0, composite_tier=RiskTier.LOW,
            confidence=ConfidenceLevel.LOW, hazard_scores={}, weights_used={},
            composite_p5=0, composite_p95=0, city="hcmc", aggregation_valid=True
        ),
        chronic_risk=CompositeRiskResult(
            event_type="chronic", composite_score=0, composite_tier=RiskTier.LOW,
            confidence=ConfidenceLevel.LOW, hazard_scores={}, weights_used={},
            composite_p5=0, composite_p95=0, city="hcmc", aggregation_valid=True
        ),
        acute_hazard_details={},
        chronic_hazard_details={},
        surface_adjustments=SurfaceAdjustments(
            original_elevation_m=0, subsidence_applied_m=0, slr_applied_m=0, adjusted_elevation_m=0
        )
    )
    
    # Save original executors
    original_executors = {step.name: step.executor for step in hazard_pipeline.steps}
    
    try:
        # Create mocks
        m_asset = AsyncMock(side_effect=lambda d: {**d, **mock_asset})
        m_chronic = AsyncMock(side_effect=lambda d: {**d, **mock_chronic})
        m_cyclone = AsyncMock(side_effect=lambda d: {**d, **mock_cyclone})
        m_acute = AsyncMock(side_effect=lambda d: {**d, **mock_acute})
        m_structure = AsyncMock(side_effect=lambda d: {**d, **mock_structure})
        m_composite = AsyncMock(side_effect=lambda d: {**d, "output": dummy_profile})
        
        mocks = {
            "asset_fetch": m_asset,
            "chronic_hazards": m_chronic,
            "cyclone_assessment": m_cyclone,
            "acute_hazards": m_acute,
            "structure_risk": m_structure,
            "composite": m_composite
        }
        
        # Replace executors
        for step in hazard_pipeline.steps:
            if step.name in mocks:
                step.executor = mocks[step.name]
            
        # Execute workflow
        result = await run_hazard_assessment(
            lat=10.0, lon=106.0,
            city="hcmc",
            return_period=100,
            multi_rp=True
        )
        
        # Verify result
        assert result == dummy_profile
        
        # Verify all mocks were called
        for name, mock in mocks.items():
            mock.assert_called_once()
            
    finally:
        # Restore original executors
        for step in hazard_pipeline.steps:
            if step.name in original_executors:
                step.executor = original_executors[step.name]
