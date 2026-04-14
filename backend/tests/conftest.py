import pathlib
import sys
import types

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


if "oasis.environment" not in sys.modules:
    oasis_pkg = types.ModuleType("oasis")
    env_module = types.ModuleType("oasis.environment")

    class Environment:
        async def step(self):
            return None

    env_module.Environment = Environment
    oasis_pkg.environment = env_module
    sys.modules["oasis"] = oasis_pkg
    sys.modules["oasis.environment"] = env_module
