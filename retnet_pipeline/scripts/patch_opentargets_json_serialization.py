#!/usr/bin/env python3
from pathlib import Path

p = Path("scripts/build_opentargets_drug_target_layer.py")

if not p.exists():
    raise SystemExit(f"File not found: {p}")

s = p.read_text(encoding="utf-8")

old = "def json_text(value):\n    return json.dumps(value, ensure_ascii=False, sort_keys=True)\n"

new = """def _json_safe(value):
    # Recursively convert pandas/NumPy/Arrow-derived objects to JSON-safe Python objects.
    if value is None:
        return None

    if hasattr(value, "tolist"):
        try:
            return _json_safe(value.tolist())
        except Exception:
            pass

    if hasattr(value, "item"):
        try:
            return _json_safe(value.item())
        except Exception:
            pass

    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if isinstance(value, (str, int, float, bool)):
        return value

    return str(value)


def json_text(value):
    return json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        sort_keys=True
    )
"""

if old not in s:
    raise SystemExit("Could not find the original json_text() function. The script may already be patched.")

backup = p.with_suffix(".py.before_json_fix.bak")
backup.write_text(s, encoding="utf-8")

s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")

print("JSON SERIALIZATION PATCH APPLIED")
print("Updated:", p)
print("Backup :", backup)
print("json_safe present:", "def _json_safe(" in s)
print("tolist handling present:", 'hasattr(value, "tolist")' in s)
