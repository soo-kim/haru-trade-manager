from pydantic import BaseModel


class ConfigSetRequest(BaseModel):
    key: str
    value: str
    changed_by: str = "api"
