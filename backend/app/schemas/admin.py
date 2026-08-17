from pydantic import BaseModel


class ProviderIn(BaseModel):
    id: int | None = None
    name: str
    base_url: str
    api_key: str = ""
    model: str
    temperature: float = 0.2
    max_output: int = 4096
    is_active: bool = False


class ProviderOut(BaseModel):
    id: int
    name: str
    base_url: str
    model: str
    temperature: float
    max_output: int
    is_active: bool
