"""Assembly — model catalog (GET /api/catalog from models.yaml)."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from src.providers.config import load_models_config

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    family: str
    roles: list[str]
    scope: str


class CatalogProvider(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    enabled: bool
    key_url: str = ""
    models: list[CatalogModel]


class CatalogResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: list[CatalogProvider]
    families: list[str]


@router.get("", response_model=CatalogResponse)
def get_catalog() -> CatalogResponse:
    """Providers, models and families from models.yaml (no keys)."""
    catalog = load_models_config()
    providers: list[CatalogProvider] = []
    families: set[str] = set()
    for pid, spec in catalog.providers.items():
        models = [
            CatalogModel(id=m.id, family=m.family, roles=list(m.roles), scope=m.scope)
            for m in spec.models
        ]
        providers.append(
            CatalogProvider(
                id=pid, enabled=spec.enabled, key_url=spec.key_url, models=models
            )
        )
        if spec.enabled:
            families.update(m.family for m in spec.models)
    return CatalogResponse(providers=providers, families=sorted(families))
