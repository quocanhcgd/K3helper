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

    # Upstream Moonraker keeps FileManager in a package, while K3 firmware
    # has shipped both the package and a flattened module over time.
    file_manager_class = None
    for module_name in (
        "moonraker.components.file_manager.file_manager",
        "moonraker.components.file_manager",
    ):
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        candidate = getattr(module, "FileManager", None)
        if candidate is not None:
            file_manager_class = candidate
            break
    if file_manager_class is None:
        raise ImportError("Moonraker FileManager class was not found")
    original_init = file_manager_class.__init__
    original_check_reserved_path = file_manager_class.check_reserved_path

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

    if not getattr(original_check_reserved_path, "_k3helper_registered_root_fix", False):
        def patched_check_reserved_path(self, req_path, need_write, raise_error=True):
            path = pathlib.Path(req_path).expanduser().resolve()
            # A registered data root is an explicit public Moonraker API root.
            # Creality's build sometimes reports a broad source directory as
            # the reserved "moonraker" path, which incorrectly catches
            # config/docs below it. Check registered roots first; normal
            # write-access checks still enforce read-only roots separately.
            registered = [
                pathlib.Path(item).expanduser().resolve()
                for item in getattr(self, "file_paths", {}).values()
            ]
            if ".git" not in path.parts and any(
                root == path or root in path.parents for root in registered
            ):
                return False
            return original_check_reserved_path(self, req_path, need_write, raise_error)

        patched_check_reserved_path._k3helper_registered_root_fix = True
        file_manager_class.check_reserved_path = patched_check_reserved_path
except Exception:
    logging.exception("K3 Helper could not apply Moonraker file-manager compatibility")
