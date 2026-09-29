"""Check local Markdown destinations; external URLs are intentionally excluded."""

import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
errors = []
for file in [
    *ROOT.glob("*.md"),
    *(ROOT / "docs").rglob("*.md"),
    *(ROOT / "examples").rglob("*.md"),
]:
    for target in re.findall(r"\]\(([^)]+)\)", file.read_text(encoding="utf-8")):
        target = target.split("#")[0]
        if not target or ":" in target or target.startswith("/"):
            continue
        if not (file.parent / unquote(target)).exists():
            errors.append(f"{file.relative_to(ROOT)}: {target}")
if errors:
    raise SystemExit("\n".join(errors))
print("Local documentation links pass")
