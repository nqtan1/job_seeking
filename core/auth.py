from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Optional, Set

from fastapi import Header, HTTPException


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    tenant_name: str = "Default Tenant"
    api_key: Optional[str] = None
    is_authenticated: bool = False


class TenantRegistry:
    def __init__(self, tenant_keys: Dict[str, Set[str]]):
        self.tenant_keys = tenant_keys

    @classmethod
    def from_env(cls) -> "TenantRegistry":
        raw_config = os.getenv("TENANT_API_KEYS_JSON")
        if not raw_config:
            return cls({})

        try:
            parsed = json.loads(raw_config)
        except json.JSONDecodeError as exc:
            raise ValueError("TENANT_API_KEYS_JSON must be valid JSON") from exc

        tenant_keys: Dict[str, Set[str]] = {}
        if isinstance(parsed, dict):
            for tenant_id, value in parsed.items():
                if isinstance(value, str):
                    tenant_keys[str(tenant_id)] = {value}
                elif isinstance(value, list):
                    tenant_keys[str(tenant_id)] = {str(item) for item in value}
                else:
                    raise ValueError("TENANT_API_KEYS_JSON values must be strings or lists of strings")

        return cls(tenant_keys)

    def is_configured(self) -> bool:
        return bool(self.tenant_keys)

    def validate(self, tenant_id: str, api_key: str) -> TenantContext:
        allowed_keys = self.tenant_keys.get(tenant_id)
        if not allowed_keys:
            raise HTTPException(status_code=403, detail="Unknown tenant")
        if api_key not in allowed_keys:
            raise HTTPException(status_code=403, detail="Invalid tenant API key")

        return TenantContext(
            tenant_id=tenant_id,
            tenant_name=tenant_id,
            api_key=api_key,
            is_authenticated=True,
        )


@lru_cache(maxsize=1)
def get_tenant_registry() -> TenantRegistry:
    return TenantRegistry.from_env()


def resolve_tenant_context(
    tenant_id: Optional[str] = None,
    api_key: Optional[str] = None,
) -> TenantContext:
    registry = get_tenant_registry()

    if not registry.is_configured():
        return TenantContext(
            tenant_id=tenant_id or "default",
            api_key=api_key,
            is_authenticated=False,
        )

    if not tenant_id or not api_key:
        raise HTTPException(status_code=401, detail="Tenant authentication required")

    return registry.validate(tenant_id, api_key)


def get_tenant_context(
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-Id"),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> TenantContext:
    return resolve_tenant_context(x_tenant_id, x_api_key)