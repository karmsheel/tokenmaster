"""Token Master — token spend analytics for Hermes.

The package is imported by the Hermes plugin loader in every process that can load
plugins, so importing it must never import Hermes core. This plugin has no agent-side
surface at all (no tools, no hooks): its whole product is the Dashboard backend
(``dashboard/plugin_api.py``) and the Desktop page (``../desktop-plugins/token-master``),
so ``register()`` is deliberately empty.

``plugin.yaml`` still matters: the backend router at ``/api/plugins/token-master/`` is
only mounted for a plugin the user has enabled, and enabling is a package-level
operation (``hermes plugins enable token-master``).
"""

from __future__ import annotations

__version__ = "0.1.0"
PLUGIN_NAME = "token-master"
__all__ = ["PLUGIN_NAME", "__version__", "register"]


def register(ctx) -> None:  # noqa: ANN001, ARG001 - the loader's fixed signature
    """Register nothing: Token Master is UI + a read-only backend."""
    return None
