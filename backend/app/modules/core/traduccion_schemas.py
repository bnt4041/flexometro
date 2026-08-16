from pydantic import BaseModel, ConfigDict, Field


class TraduccionOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    clave: str
    texto: str


class TraduccionOverrideUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texto: str = Field(min_length=1, max_length=2000)
