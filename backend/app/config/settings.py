# Compatibility shim: Wrangler finance code expects app.config.settings
# This module re-exports from Huabang's app.core.config
from app.core.config import settings  # noqa: F401, E402
