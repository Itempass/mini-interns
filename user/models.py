from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional

class User(BaseModel):
    uuid: UUID
    auth0_sub: Optional[str] = None
    email: Optional[str] = None
    is_anonymous: bool = False
    created_at: datetime
    balance: float = 5.0
    is_admin: Optional[bool] = None

    class Config:
        from_attributes = True 