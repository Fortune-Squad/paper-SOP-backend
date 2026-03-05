from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import json

from .contracts import SCHEMA_VERSION


class Decision(str, Enum):
    KEEP = "keep"
    DROP = "drop"
    ESCALATE = "escalate"
    SEAL = "seal"
    RETRY = "retry"


@dataclass
class RetryPolicy:
    max_attempts: int = 3
    backoff_seconds: float = 30.0
    backoff_multiplier: float = 2.0
    retryable_errors: tuple[str, ...] = ("timeout", "solver_crash", "token_limit", "network_error")

    def delay_for_attempt(self, attempt: int) -> float:
        return self.backoff_seconds * (self.backoff_multiplier ** (attempt - 1))

    def is_retryable(self, error_msg: str) -> bool:
        lower = error_msg.lower()
        return any(pattern in lower for pattern in self.retryable_errors)


@dataclass
class ExecutorConfig:
    kernel: str = "fake"
    cmd: str | list[str] | None = None
    cmd_file: str | None = None
    timeout_seconds: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutorConfig":
        kernel = str(data.get("kernel", "fake")).strip().lower()
        if kernel not in {"fake", "subprocess"}:
            raise ValueError("executor_map.*.kernel must be 'fake' or 'subprocess'")

        raw_cmd = data.get("cmd")
        cmd: str | list[str] | None
        if raw_cmd is None:
            cmd = None
        elif isinstance(raw_cmd, str):
            cmd = raw_cmd
        elif isinstance(raw_cmd, list):
            cmd_items: list[str] = []
            for index, item in enumerate(raw_cmd):
                if not isinstance(item, str):
                    raise ValueError(f"executor_map.*.cmd[{index}] must be a string")
                if not item:
                    raise ValueError(f"executor_map.*.cmd[{index}] must not be empty")
                cmd_items.append(item)
            cmd = cmd_items
        else:
            raise ValueError("executor_map.*.cmd must be a string or list[str]")

        raw_cmd_file = data.get("cmd_file")
        if raw_cmd_file is None:
            cmd_file = None
        else:
            cmd_file = str(raw_cmd_file).strip()
            if not cmd_file:
                raise ValueError("executor_map.*.cmd_file must not be empty")

        raw_timeout = data.get("timeout_seconds")
        timeout_seconds: int | None
        if raw_timeout is None:
            timeout_seconds = None
        else:
            try:
                timeout_seconds = int(raw_timeout)
            except (TypeError, ValueError) as exc:
                raise ValueError("executor_map.*.timeout_seconds must be an integer") from exc
            if timeout_seconds < 1:
                raise ValueError("executor_map.*.timeout_seconds must be >= 1")

        return cls(
            kernel=kernel,
            cmd=cmd,
            cmd_file=cmd_file,
            timeout_seconds=timeout_seconds,
        )


@dataclass
class InverseConfig:
    enabled: bool = False
    cmd: str | list[str] | None = None
    cmd_file: str | None = None
    timeout_seconds: int = 120

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InverseConfig":
        raw_enabled = data.get("enabled", False)
        enabled = bool(raw_enabled)

        raw_cmd = data.get("cmd")
        cmd: str | list[str] | None
        if raw_cmd is None:
            cmd = None
        elif isinstance(raw_cmd, str):
            cmd = raw_cmd
        elif isinstance(raw_cmd, list):
            cmd_items: list[str] = []
            for index, item in enumerate(raw_cmd):
                if not isinstance(item, str):
                    raise ValueError(f"inverse.cmd[{index}] must be a string")
                if not item:
                    raise ValueError(f"inverse.cmd[{index}] must not be empty")
                cmd_items.append(item)
            cmd = cmd_items
        else:
            raise ValueError("inverse.cmd must be a string or list[str]")

        raw_cmd_file = data.get("cmd_file")
        if raw_cmd_file is None:
            cmd_file = None
        else:
            cmd_file = str(raw_cmd_file).strip()
            if not cmd_file:
                raise ValueError("inverse.cmd_file must not be empty")

        raw_timeout = data.get("timeout_seconds", 120)
        if raw_timeout is None:
            timeout_seconds = 120
        else:
            try:
                timeout_seconds = int(raw_timeout)
            except (TypeError, ValueError) as exc:
                raise ValueError("inverse.timeout_seconds must be an integer") from exc
        if timeout_seconds < 1:
            raise ValueError("inverse.timeout_seconds must be >= 1")

        return cls(
            enabled=enabled,
            cmd=cmd,
            cmd_file=cmd_file,
            timeout_seconds=timeout_seconds,
        )


@dataclass
class PathsConfig:
    repo_root: str | None = None
    slot_a_backend_root: str | None = None
    slot_a_prompts_root: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PathsConfig":
        def _get_path_value(key: str) -> str | None:
            raw = data.get(key)
            if raw is None:
                return None
            value = str(raw).strip()
            return value or None

        return cls(
            repo_root=_get_path_value("repo_root"),
            slot_a_backend_root=_get_path_value("slot_a_backend_root"),
            slot_a_prompts_root=_get_path_value("slot_a_prompts_root"),
        )


@dataclass
class ProgramSpec:
    program_id: str
    goal: str
    constraints: list[str] = field(default_factory=list)
    max_candidates: int = 2
    execution_types: list[str] = field(default_factory=lambda: ["slot_a"])
    executor_map: dict[str, ExecutorConfig] = field(default_factory=dict)
    inverse: InverseConfig = field(default_factory=InverseConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    retry_policy: RetryPolicy | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProgramSpec":
        program_id = str(data.get("program_id", "")).strip()
        goal = str(data.get("goal", "")).strip()
        if not program_id:
            raise ValueError("program_id is required")
        if not goal:
            raise ValueError("goal is required")

        constraints = data.get("constraints", [])
        if constraints is None:
            constraints = []
        if not isinstance(constraints, list):
            raise ValueError("constraints must be a list")
        constraints = [str(item) for item in constraints]

        raw_max = data.get("max_candidates", 2)
        try:
            max_candidates = int(raw_max)
        except (TypeError, ValueError) as exc:
            raise ValueError("max_candidates must be an integer") from exc
        if max_candidates < 1:
            max_candidates = 1

        execution_types_raw = data.get("execution_types", ["slot_a"])
        if execution_types_raw is None:
            execution_types_raw = ["slot_a"]
        if not isinstance(execution_types_raw, list):
            raise ValueError("execution_types must be a list")
        execution_types = [str(item).strip() for item in execution_types_raw if str(item).strip()]
        if not execution_types:
            execution_types = ["slot_a"]
        execution_types = execution_types[:max_candidates]

        raw_executor_map = data.get("executor_map", {})
        if raw_executor_map is None:
            raw_executor_map = {}
        if not isinstance(raw_executor_map, dict):
            raise ValueError("executor_map must be an object")
        executor_map: dict[str, ExecutorConfig] = {}
        for execution_type, raw_cfg in raw_executor_map.items():
            normalized_execution_type = str(execution_type).strip()
            if not normalized_execution_type:
                raise ValueError("executor_map keys must not be empty")
            if not isinstance(raw_cfg, dict):
                raise ValueError(f"executor_map.{normalized_execution_type} must be an object")
            executor_map[normalized_execution_type] = ExecutorConfig.from_dict(raw_cfg)

        raw_inverse = data.get("inverse")
        if raw_inverse is None:
            inverse = InverseConfig()
        else:
            if not isinstance(raw_inverse, dict):
                raise ValueError("inverse must be an object")
            inverse = InverseConfig.from_dict(raw_inverse)

        raw_paths = data.get("paths")
        if raw_paths is None:
            paths = PathsConfig()
        else:
            if not isinstance(raw_paths, dict):
                raise ValueError("paths must be an object")
            paths = PathsConfig.from_dict(raw_paths)

        raw_retry = data.get("retry_policy")
        retry_policy: RetryPolicy | None = None
        if raw_retry is not None:
            if not isinstance(raw_retry, dict):
                raise ValueError("retry_policy must be an object")
            rp_kwargs: dict[str, Any] = {}
            if "max_attempts" in raw_retry:
                rp_kwargs["max_attempts"] = int(raw_retry["max_attempts"])
            if "backoff_seconds" in raw_retry:
                rp_kwargs["backoff_seconds"] = float(raw_retry["backoff_seconds"])
            if "backoff_multiplier" in raw_retry:
                rp_kwargs["backoff_multiplier"] = float(raw_retry["backoff_multiplier"])
            if "retryable_errors" in raw_retry:
                rp_kwargs["retryable_errors"] = tuple(str(e) for e in raw_retry["retryable_errors"])
            retry_policy = RetryPolicy(**rp_kwargs)

        return cls(
            program_id=program_id,
            goal=goal,
            constraints=constraints,
            max_candidates=max_candidates,
            execution_types=execution_types,
            executor_map=executor_map,
            inverse=inverse,
            paths=paths,
            retry_policy=retry_policy,
        )

    @classmethod
    def from_json_file(cls, spec_path: str | Path) -> "ProgramSpec":
        path = Path(spec_path)
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("ProgramSpec JSON must be an object")
        return cls.from_dict(payload)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateCard:
    id: str
    hypothesis: str
    plan: str
    required_artifacts: list[str] = field(default_factory=list)
    eval_checks: list[str] = field(default_factory=list)
    priority: int = 0
    execution_type: str = "slot_a"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunRecord:
    run_id: str
    program_id: str
    candidate_id: str
    bundle_path: str
    gate_result: str
    score: float
    execution_type: str = "slot_a"
    next_action: str | None = None
    bundle_history: list[str] = field(default_factory=list)
    previous_bundle_dir: str | None = None
    audit_dir: str | None = None
    audit_status: str | None = None
    audit_report_path: str | None = None
    audit_diff_path: str | None = None
    audit_exec_path: str | None = None
    retry_count: int = 0
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        if result.get("retry_count", 0) == 0:
            result.pop("retry_count", None)
        return result
