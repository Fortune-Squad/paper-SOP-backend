from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .adapters import FakeKernelAdapter, KernelAdapter, SubprocessKernelAdapter
from .command_utils import substitute_command_tokens
from .lock import OutDirLock
from .loop import AutopilotLoop
from .schemas import ProgramSpec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Autopilot v1.0 CLI")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run autopilot from ProgramSpec JSON")
    run_parser.add_argument("--spec", required=True, help="Path to ProgramSpec JSON file")
    run_parser.add_argument("--out", required=True, help="Output directory")
    run_parser.add_argument(
        "--kernel",
        choices=["fake", "subprocess"],
        default="fake",
        help="Kernel adapter type",
    )
    run_parser.add_argument(
        "--cmd",
        help="Command string for subprocess kernel adapter. Supports JSON list syntax.",
    )
    run_parser.add_argument(
        "--cmd-file",
        help="Path to JSON file containing command as list[str] for subprocess kernel adapter",
    )
    run_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=300,
        help="Timeout for subprocess kernel adapter in seconds (default: 300)",
    )
    run_parser.add_argument(
        "--no-lock",
        action="store_true",
        help="Bypass out_dir lock acquisition (use with caution).",
    )

    tick_parser = subparsers.add_parser("tick", help="Non-blocking tick/resume on existing output dir")
    tick_parser.add_argument("--out", required=True, help="Existing output directory")
    tick_parser.add_argument(
        "--no-lock",
        action="store_true",
        help="Bypass out_dir lock acquisition (use with caution).",
    )

    daemon_parser = subparsers.add_parser("daemon", help="Run autopilot as a continuous tick loop")
    daemon_parser.add_argument("--out-dir", required=True, help="Autopilot output directory")
    daemon_parser.add_argument("--interval", type=float, default=30.0,
                               help="Seconds between ticks (default: 30)")
    daemon_parser.add_argument("--max-failures", type=int, default=10,
                               help="Max consecutive failures before cooldown (default: 10)")
    daemon_parser.add_argument("--hil-inbox", default=None,
                               help="HIL ticket inbox directory (optional)")

    return parser


def _parse_list_command(raw: str, source: str, parser: argparse.ArgumentParser) -> list[str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        parser.error(f"Invalid JSON command list in {source}: {exc}")
        return []

    if not isinstance(payload, list):
        parser.error(f"Command in {source} must be a JSON list")
        return []
    if not payload:
        parser.error(f"Command in {source} must not be empty")
        return []

    command: list[str] = []
    for index, item in enumerate(payload):
        if not isinstance(item, str):
            parser.error(f"Command item at index {index} in {source} must be a string")
            return []
        if not item:
            parser.error(f"Command item at index {index} in {source} must not be empty")
            return []
        command.append(item)
    return substitute_command_tokens(command)


def _resolve_subprocess_command(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> str | list[str]:
    if args.cmd and args.cmd_file:
        parser.error("--cmd and --cmd-file are mutually exclusive")

    if args.cmd_file:
        cmd_file_path = Path(args.cmd_file)
        try:
            # utf-8-sig keeps Windows-authored JSON files (with BOM) compatible.
            content = cmd_file_path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            parser.error(f"Failed to read --cmd-file '{cmd_file_path}': {exc}")
            return []
        return _parse_list_command(content, f"--cmd-file {cmd_file_path}", parser)

    if not args.cmd:
        parser.error("--cmd or --cmd-file is required when --kernel subprocess is used")

    cmd_text = str(args.cmd)
    if cmd_text.lstrip().startswith("["):
        return _parse_list_command(cmd_text, "--cmd", parser)
    return cmd_text


def _build_adapter(args: argparse.Namespace, parser: argparse.ArgumentParser) -> KernelAdapter:
    if args.kernel == "fake":
        return FakeKernelAdapter()

    if args.kernel == "subprocess":
        if args.timeout_seconds < 1:
            parser.error("--timeout-seconds must be >= 1")
        command = _resolve_subprocess_command(args, parser)
        cmd_file = str(args.cmd_file).strip() if args.cmd_file else None
        return SubprocessKernelAdapter(
            command=command,
            timeout_seconds=args.timeout_seconds,
            cmd_file=cmd_file,
        )

    parser.error(f"Unsupported kernel adapter: {args.kernel}")
    return FakeKernelAdapter()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command not in {"run", "tick", "daemon"}:
        parser.print_help()
        return 1

    if args.command == "daemon":
        from .scheduler import AutopilotScheduler
        scheduler = AutopilotScheduler(
            out_dir=args.out_dir,
            tick_interval_seconds=args.interval,
            max_consecutive_failures=args.max_failures,
            hil_inbox_dir=args.hil_inbox,
        )
        scheduler.run_forever()
        return 0

    if args.command == "tick":
        out_dir = Path(args.out)
        try:
            with OutDirLock(out_dir=out_dir, command="tick", enabled=not bool(args.no_lock)):
                result = AutopilotLoop.tick(out_dir=out_dir)
        except RuntimeError as exc:
            print(f"Autopilot lock error: {exc}")
            return 1
        print(
            f"Autopilot tick complete. out={out_dir}, records={result['records']}, "
            f"promoted={result['promoted']}, pending={result['pending']}"
        )
        return 0

    spec = ProgramSpec.from_json_file(args.spec)
    out_dir = Path(args.out)
    try:
        with OutDirLock(out_dir=out_dir, command="run", enabled=not bool(args.no_lock)):
            adapter = _build_adapter(args, parser)
            loop = AutopilotLoop(
                spec=spec,
                out_dir=out_dir,
                kernel_adapter=adapter,
                default_subprocess_timeout_seconds=args.timeout_seconds,
            )
            records = loop.run()
    except RuntimeError as exc:
        print(f"Autopilot lock error: {exc}")
        return 1

    print(
        f"Autopilot run complete. program_id={spec.program_id}, "
        f"candidates={len(records)}, out={out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
