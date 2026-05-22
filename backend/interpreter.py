"""
.module interpreter.

A `.module` file is YAML:
    name: hello
    description: ...
    category: utility
    params:
      - {name: who, type: string, default: world}
    entry: hello.py
    function: run

Pair it with hello.py in the same folder, exposing `run(**kwargs)`.
"""
import importlib.util, os, yaml
from pathlib import Path
from typing import Dict, List

MODULES_DIR = Path(__file__).resolve().parent.parent / "modules"

class ModuleSpec:
    def __init__(self, path: Path, data: dict):
        self.path = path
        self.name = data["name"]
        self.description = data.get("description","")
        self.category = data.get("category","misc")
        self.params = data.get("params", [])
        self.entry = data.get("entry","")
        self.function = data.get("function","run")
        self.raw = data

    def call(self, **kwargs):
        py = self.path.parent / self.entry
        spec = importlib.util.spec_from_file_location(self.name, py)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        fn = getattr(mod, self.function)
        # apply defaults / coerce types
        final = {}
        for p in self.params:
            v = kwargs.get(p["name"], p.get("default"))
            t = p.get("type","string")
            try:
                if t == "int":   v = int(v)
                if t == "float": v = float(v)
                if t == "bool":  v = str(v).lower() in ("1","true","yes","on")
            except Exception: pass
            final[p["name"]] = v
        return fn(**final)

def discover() -> List[ModuleSpec]:
    out = []
    for f in MODULES_DIR.glob("*.module"):
        try:
            data = yaml.safe_load(f.read_text())
            out.append(ModuleSpec(f, data))
        except Exception: pass
    return out

def find(name: str) -> ModuleSpec | None:
    for m in discover():
        if m.name == name: return m
    return None
