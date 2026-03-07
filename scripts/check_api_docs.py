#!/usr/bin/env python3
"""Check API docs against actual FastAPI routes."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "websocket"}
DOC_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "WS"}
AUTO_START = "<!-- ROUTE_MATRIX_START -->"
AUTO_END = "<!-- ROUTE_MATRIX_END -->"


def normalize_path(path: str) -> str:
    """Normalize path for stable comparison."""
    path = path.strip()
    if not path:
        return "/"
    if not path.startswith("/"):
        path = f"/{path}"
    # collapse multiple slashes
    path = re.sub(r"/{2,}", "/", path)
    # trim trailing slash except root
    if len(path) > 1 and path.endswith("/"):
        path = path[:-1]
    return path


def join_path(prefix: str, route: str) -> str:
    prefix_n = normalize_path(prefix or "")
    route_n = normalize_path(route or "")
    if prefix_n == "/":
        return route_n
    if route_n == "/":
        return prefix_n
    return normalize_path(f"{prefix_n}/{route_n.lstrip('/')}")


def get_router_prefix(module_ast: ast.Module) -> str:
    for node in module_ast.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name) or target.id != "router":
            continue
        if not isinstance(node.value, ast.Call):
            continue
        fn = node.value.func
        if not isinstance(fn, ast.Name) or fn.id != "APIRouter":
            continue
        for kw in node.value.keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
    return ""


def extract_routes_from_file(path: Path, router_name: str = "router", prefix: str | None = None) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    content = path.read_text(encoding="utf-8")
    module_ast = ast.parse(content, filename=str(path))
    resolved_prefix = get_router_prefix(module_ast) if prefix is None else prefix

    for node in ast.walk(module_ast):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            if not isinstance(dec.func, ast.Attribute):
                continue
            if not isinstance(dec.func.value, ast.Name) or dec.func.value.id != router_name:
                continue
            method_raw = dec.func.attr.lower()
            if method_raw not in HTTP_METHODS:
                continue
            if not dec.args:
                continue
            arg0 = dec.args[0]
            if not isinstance(arg0, ast.Constant) or not isinstance(arg0.value, str):
                continue
            route_path = join_path(resolved_prefix, arg0.value)
            method = "WS" if method_raw == "websocket" else method_raw.upper()
            routes.add((method, route_path))
    return routes


def collect_code_routes(api_dir: Path, main_file: Path) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for py_file in sorted(api_dir.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        routes |= extract_routes_from_file(py_file)
    if main_file.exists():
        routes |= extract_routes_from_file(main_file, router_name="app", prefix="")
    return routes


def collect_doc_routes(doc_path: Path) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    pattern = re.compile(r"^\|\s*(GET|POST|PUT|DELETE|PATCH|WS)\s*\|\s*`([^`]+)`")
    lines = doc_path.read_text(encoding="utf-8").splitlines()
    if AUTO_START in lines and AUTO_END in lines:
        start = lines.index(AUTO_START) + 1
        end = lines.index(AUTO_END)
        lines = lines[start:end]
    for line in lines:
        m = pattern.match(line.strip())
        if not m:
            continue
        method = m.group(1).upper()
        path = normalize_path(m.group(2))
        if method in DOC_METHODS:
            routes.add((method, path))
    return routes


def render_route_matrix(routes: set[tuple[str, str]]) -> str:
    header = [
        "| 方法 | 路径 |",
        "|---|---|",
    ]
    body = [f"| {method} | `{path}` |" for method, path in sorted(routes)]
    return "\n".join(header + body)


def write_route_matrix(doc_path: Path, routes: set[tuple[str, str]]) -> None:
    content = doc_path.read_text(encoding="utf-8")
    matrix = render_route_matrix(routes)
    replacement = f"{AUTO_START}\n{matrix}\n{AUTO_END}"
    if AUTO_START in content and AUTO_END in content:
        content = re.sub(
            rf"{re.escape(AUTO_START)}[\s\S]*?{re.escape(AUTO_END)}",
            replacement,
            content,
            count=1,
        )
    else:
        if not content.endswith("\n"):
            content += "\n"
        content += f"\n## 路由矩阵（自动生成）\n\n{replacement}\n"
    doc_path.write_text(content, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate API docs against code routes.")
    parser.add_argument(
        "--doc",
        default="docs/API_DOCUMENTATION.md",
        help="Path to API documentation markdown file (relative to backend root).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write current code routes into the doc route matrix section.",
    )
    args = parser.parse_args()

    backend_root = Path(__file__).resolve().parents[1]
    api_dir = backend_root / "app" / "api"
    main_file = backend_root / "app" / "main.py"
    doc_path = backend_root / args.doc

    if not api_dir.exists():
        print(f"[ERROR] API directory not found: {api_dir}")
        return 2
    if not doc_path.exists():
        print(f"[ERROR] API doc file not found: {doc_path}")
        return 2

    code_routes = collect_code_routes(api_dir, main_file)
    if args.write:
        write_route_matrix(doc_path, code_routes)
        print(f"[OK] Wrote route matrix to: {doc_path}")
    doc_routes = collect_doc_routes(doc_path)

    missing_in_docs = sorted(code_routes - doc_routes)
    stale_in_docs = sorted(doc_routes - code_routes)

    print(f"Code routes: {len(code_routes)}")
    print(f"Doc routes : {len(doc_routes)}")

    if missing_in_docs:
        print("\n[FAIL] Routes found in code but missing in docs:")
        for method, path in missing_in_docs:
            print(f"  - {method:6} {path}")

    if stale_in_docs:
        print("\n[FAIL] Routes found in docs but missing in code:")
        for method, path in stale_in_docs:
            print(f"  - {method:6} {path}")

    if missing_in_docs or stale_in_docs:
        print("\nAPI documentation check failed.")
        return 1

    print("\n[OK] API documentation is in sync with code routes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
