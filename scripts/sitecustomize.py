"""Expose K3 Helper's external Moonraker components to the stock package."""

import importlib
import logging
import os
import pathlib
import pkgutil
import sys
import types

try:
    # K3 launches moonraker.py as a script from /usr/share/moonraker, so its
    # components are top-level imports (components.*), not moonraker.components.
    moonraker_root = "/usr/share/moonraker"
    if moonraker_root not in sys.path:
        sys.path.insert(0, moonraker_root)

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

    # Support namespace-package imports too, for Helper Script extensions.
    try:
        moonraker_components = importlib.import_module("moonraker.components")
        namespace_component_path = os.path.join(moonraker_root, "components")
        if namespace_component_path not in moonraker_components.__path__:
            moonraker_components.__path__.append(namespace_component_path)
        helper_namespace_path = os.path.join(
            os.path.dirname(__file__), "moonraker", "components"
        )
        if helper_namespace_path not in moonraker_components.__path__:
            moonraker_components.__path__.append(helper_namespace_path)
    except (ImportError, ModuleNotFoundError):
        moonraker_components = None

    # Moonraker's active FileManager module on K3 is
    # components.file_manager.file_manager.
    file_manager_class = None
    module_names = [
        "components.file_manager.file_manager",
        "components.file_manager",
        "moonraker.components.file_manager.file_manager",
        "moonraker.components.file_manager",
        "moonraker.file_manager",
    ]
    packages = [top_components]
    if moonraker_components is not None:
        packages.append(moonraker_components)
    for package in packages:
        candidate = getattr(package, "FileManager", None)
        if candidate is not None and hasattr(candidate, "check_reserved_path"):
            file_manager_class = candidate
            logging.info("K3 Helper found Moonraker FileManager in %s", package.__name__)
            break
    if file_manager_class is not None:
        packages = []
    for package in packages:
        package_path = getattr(package, "__path__", ())
        try:
            package_modules = list(pkgutil.walk_packages(package_path, package.__name__ + "."))
        except Exception:
            package_modules = []
        for item in package_modules:
            if item.name not in module_names and "file" not in item.name.lower():
                continue
            module_names.append(item.name)
        for package_dir in package_path:
            try:
                package_root = pathlib.Path(package_dir).resolve()
                for source_path in package_root.rglob("*.py"):
                    try:
                        source = source_path.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    if "class FileManager" not in source:
                        continue
                    relative = source_path.relative_to(package_root.parent)
                    parts = list(relative.parts)
                    if parts[-1] == "__init__.py":
                        parts.pop()
                    else:
                        parts[-1] = pathlib.Path(parts[-1]).stem
                    discovered = ".".join(parts)
                    if discovered and discovered not in module_names:
                        module_names.append(discovered)
            except (OSError, ValueError):
                continue
    for module_name in module_names:
        try:
            module = importlib.import_module(module_name)
        except (ImportError, ModuleNotFoundError, AttributeError):
            continue
        candidate = getattr(module, "FileManager", None)
        if candidate is not None and hasattr(candidate, "check_reserved_path"):
            file_manager_class = candidate
            logging.info("K3 Helper found Moonraker FileManager in %s", module_name)
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
