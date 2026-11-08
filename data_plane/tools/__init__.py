"""Layer 3 — Data & Execution Plane."""
from __future__ import annotations

__all__ = ["ToolRegistry", "ToolInjector", "Settings"]


def __getattr__(name: str):  # lazy imports keep `import tools` cheap
    if name == "ToolRegistry":
        from .registry import ToolRegistry
        return ToolRegistry
    if name == "ToolInjector":
        from .injector import ToolInjector
        return ToolInjector
    if name == "Settings":
        from .config import Settings
        return Settings
    raise AttributeError(name)
