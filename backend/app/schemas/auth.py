from pydantic import BaseModel


class RegisterIn(BaseModel):
    email: str
    password: str


class VerifyIn(BaseModel):
    email: str
    code: str


class ResendIn(BaseModel):
    email: str


class LoginIn(BaseModel):
    email: str
    password: str


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str


class TokenOut(BaseModel):
    access_token: str
    role: str


class MeOut(BaseModel):
    id: int
    email: str
    role: str
