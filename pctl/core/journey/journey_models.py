"""
Journey models and types - Core layer
Based on legacy authflow types
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from ..exceptions import JourneyError


class Callback(BaseModel):
    """Journey callback model"""
    type: str
    output: Optional[List[Dict[str, str]]] = None
    input: List[Dict[str, str]]


StepConfig = Dict[str, str]  # Simple type alias


class JourneyConfig(BaseModel):
    """Journey configuration model"""
    platform_url: str = Field(alias='platformUrl')
    realm: str
    journey_name: str = Field(alias='journeyName')
    steps: Dict[str, StepConfig]
    
    class Config:
        validate_by_name = True


class JourneyStep(BaseModel):
    """Journey execution step"""
    auth_id: str
    callbacks: List[Callback]


class JourneyResult(BaseModel):
    """Journey execution result"""
    success: bool
    token_id: Optional[str] = None
    success_url: Optional[str] = None
    error: Optional[str] = None
    auth_id: Optional[str] = None
    callbacks: Optional[List[Callback]] = None