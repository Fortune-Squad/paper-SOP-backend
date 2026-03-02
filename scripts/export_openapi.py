#!/usr/bin/env python3
"""导出 OpenAPI 3.0 JSON 到 docs/openapi.json，便于文档与代码生成。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app

if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(app.openapi(), f, ensure_ascii=False, indent=2)
    print(f"Written: {out}")
