from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CORPUS = ROOT / "corpus"


def load_plugin_like_hermes(module_name: str):
    """Load the root __init__.py the way Hermes' plugin loader does: as a package
    whose submodules resolve from the plugin dir via relative imports."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    module.__package__ = module_name
    module.__path__ = [str(ROOT)]  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
