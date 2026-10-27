"""Expose K3 Helper's external Moonraker components to the stock package."""

import importlib
import logging
import os
import pathlib
import sys
import types

try:
    components = importlib.import_module("moonraker.components")
    component_path = os.path.join(os.path.dirname(__file__), "moonraker", "components")
    if component_path not in components.__path__:
        components.__path__.append(component_path)

    # Creality's trimmed loader imports optional modules as components.X
    # rather than moonraker.components.X.
    try:
        top_components = importlib.import_module("components")
    except ModuleNotFoundError:
        top_components = types.ModuleType("components")
        top_components.__path__ = []
        sys.modules["components"] = top_components
    top_component_path = os.path.join(os.path.dirname(__file__), "components")
    if top_component_path not in top_components.__path__:
        top_components.__path__.append(top_component_path)

    # Distro-installed Moonraker may report /usr/share as its source root,
    # which also contains Klipper's registered docs root. That makes the
    # file manager reject its own docs directory as a reserved Moonraker path.
    moonraker = importlib.import_module("moonraker")
    module = importlib.import_module("moonraker.components.file_manager.file_manager")
    file_manager_class = module.FileManager
    original_init = file_manager_class.__init__

    if not getattr(original_init, "_k3helper_reserved_path_fix", False):
        package_root = pathlib.Path("/usr/share/moonraker").resolve()

        def patched_init(self, config):
            original_init(self, config)
            reserved = self.reserved_paths.get("moonraker")
            if reserved is None:
                return
            reserved_root, can_read = reserved
            reserved_root = pathlib.Path(reserved_root).resolve()
            if package_root != reserved_root and reserved_root in package_root.parents:
                self.reserved_paths["moonraker"] = (package_root, can_read)
                logging.info(
                    "K3 Helper narrowed Moonraker's reserved path from %s to %s",
                    reserved_root,
                    package_root,
                )

        patched_init._k3helper_reserved_path_fix = True
        file_manager_class.__init__ = patched_init
except Exception:
    logging.exception("K3 Helper could not apply Moonraker file-manager compatibility")
