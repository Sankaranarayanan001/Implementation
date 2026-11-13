from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=72)
    full_name: str = ""


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MappingConfirmIn(BaseModel):
    mappings: Dict[str, Optional[str]]  # source column -> canonical banking field (or null)


class DecisionItem(BaseModel):
    rec_id: str
    decision: str  # approve | reject | modify
    action: Optional[str] = None
    params: Optional[dict] = None


class ReviewIn(BaseModel):
    decisions: List[DecisionItem] = []
    approve_all_pending: bool = False
