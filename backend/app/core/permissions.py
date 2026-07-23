"""
Compatibility shim - maps Wrangler-style permission checks to Huabang deps
"""
from app.api.v1.deps import require_permission

# Wrangler uses check_permission(permission) directly
# Huabang uses require_permission(permission) which returns a Depends callable
def check_permission(permission: str):
    """Wrangler-compatible permission checker"""
    return require_permission(permission)
