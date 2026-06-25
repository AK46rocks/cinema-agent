#create Interface like state
from typing import TypedDict, Optional, Dict, Any
from pydantic import BaseModel
from enum import Enum

class Intent(str, Enum):
    TRENDING = "TRENDING",
    MOVIE_INFO = "MOVIE_INFO",
    ACTOR_INFO = "ACTOR_INFO"
    ANALYSIS = "ANALYSIS"
    SIMILAR = "SIMILAR"

class RouterOutput(BaseModel):
    intent : Intent
    extracted_argument: str 
    media_type: str = "movie"
    discover_params: str = "{}"  

class AgentState(TypedDict):
    user_query: str
    intent: Intent
    extracted_argument: Optional[str]
    media_type: Optional[str]           
    discover_params: Optional[dict]
    local_data: Optional[str]
    live_data: Optional[str]
    final_response: Optional[str]


