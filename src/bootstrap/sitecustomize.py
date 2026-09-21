import sys
import types

# Add a fake pyodide module to sys.modules seems to break `panel convert`
# print("Adding fake pyodide module to sys.modules", file=sys.stderr)
# sys.modules.setdefault("pyodide", types.ModuleType("pyodide"))