"""Merge Phase 1 EN/AR message pairs (scripts/i18n/p1-*.py) into messages/en.json and ar.json.

Each module defines P = nested dict whose leaves are [en, ar]. Existing keys are overwritten.
Usage: python3 scripts/i18n/merge.py
"""
import glob
import json
import os
import runpy

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def split(node, idx):
    if isinstance(node, list):
        return node[idx]
    return {k: split(v, idx) for k, v in node.items()}


def deep_merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v


for idx, loc in ((0, "en"), (1, "ar")):
    path = os.path.join(ROOT, "messages", f"{loc}.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for mod in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "p1-*.py"))):
        deep_merge(data, split(runpy.run_path(mod)["P"], idx))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
print("merged")
