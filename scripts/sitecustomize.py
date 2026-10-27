"""Expose K3 Helper's external Moonraker components to the stock package."""

import importlib
import os

try:
    components = importlib.import_module("moonraker.components")
    component_path = os.path.join(os.path.dirname(__file__), "moonraker", "components")
    if component_path not in components.__path__:
        components.__path__.append(component_path)
except Exception:
    pass
