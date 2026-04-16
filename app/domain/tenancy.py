GLOBAL_TENANT_SCOPE = "__global__"


def normalize_tenant_scope(tenant_id: str | None) -> str:
    return tenant_id or GLOBAL_TENANT_SCOPE
