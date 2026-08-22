from pydantic import BaseModel, EmailStr
from typing import Optional

class EmailRequest(BaseModel):
    email: EmailStr

class EmailVerifyRequest(BaseModel):
    email: EmailStr
    code: str

class UserSignupRequest(BaseModel):
    user_id: str
    user_pw: str
    user_name: str
    user_role: Optional[str] = "VIEWER"
    user_email: EmailStr
    user_phone: Optional[str] = None
    user_gender: Optional[str] = None
    user_address: Optional[str] = None