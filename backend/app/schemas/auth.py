from pydantic import BaseModel


class RegisterIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    role: str


class MeOut(BaseModel):
    id: int
    username: str
    role: str
