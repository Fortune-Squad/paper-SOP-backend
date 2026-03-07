# Autopilot

## Quickstart

Run:

```powershell
py -m sop.autopilot.cli run --spec sop/autopilot/examples/program_spec_slot_ab.json --out sop/autopilot/.demo_out --kernel fake
```

Tick:

```powershell
py -m sop.autopilot.cli tick --out sop/autopilot/.demo_out
```

Locking:

- `run` and `tick` create `OUT/.autopilot.lock` by default.
- Use `--no-lock` to bypass locking.
- Stale locks (>1 hour) are overridden and a `LOCK_STALE_OVERRIDE` ledger event is appended.

## ProgramSpec Fields

- `program_id` / `goal` / `constraints` / `max_candidates`
- `execution_types`: ordered candidate routing labels.
- `executor_map`: per-execution-type kernel config.
  - `kernel`: `fake` or `subprocess`
  - `cmd`: string or JSON-list command
  - `cmd_file`: path to JSON list command
  - `timeout_seconds`
- `inverse` (default disabled):
  - `enabled`: bool
  - `cmd`: optional string or list command
  - `cmd_file`: optional JSON-list file
  - `timeout_seconds`: default `120`
- `paths` (optional):
  - `repo_root`
  - `slot_a_backend_root`
  - `slot_a_prompts_root`

## Slot-A Submit-Only Bridge

Command file (portable token):

```json
[
  "@PYTHON@",
  "-m",
  "sop.autopilot.bridges.slot_a_submit"
]
```

Bridge path resolution order:

1. `ProgramSpec.paths.*`
2. env overrides: `AUTOPILOT_REPO_ROOT`, `AUTOPILOT_SLOT_A_BACKEND_ROOT`, `AUTOPILOT_SLOT_A_PROMPTS_ROOT`
3. auto-detect by walking up for `paper-sop-automation/backend`

Metadata includes:

- `template_source`
- `template_paths_used`
- `backend_root_used`

## Slot-B Manual Bundle

Bridge command file:

```json
[
  "@PYTHON@",
  "-m",
  "sop.autopilot.bridges.slot_b_manual_bundle"
]
```

Manual outputs marker:

- `outputs/outputs_manifest.json`

Manifest forms:

Simple list:

```json
{
  "files": ["result.txt", "plots/summary.png"],
  "note": "optional"
}
```

Verified entries (size/hash):

```json
{
  "files": [
    {
      "path": "result.txt",
      "size": 3,
      "sha256": "dc51b8c96c2d745df3bd5590d990230a482fd247123599548e0632fdbf97fc22"
    }
  ],
  "note": "optional"
}
```

`tick` promotes PENDING -> PASS only when listed files exist and optional checks pass.

## Append-Only Bundles And History

- Bundle dirs are versioned and append-only:
  - `bundles/<program_id>-<candidate_id>-<run_id>`
- `run_records/cand-*.json` tracks:
  - `run_id`
  - `previous_bundle_dir`
  - `bundle_history`

## Ledger Events

Common events include:

- `DISPATCH_SUBMIT`
- `INVERSE_DIFF_OK`
- `INVERSE_DIFF_FAIL`
- `TICK_PROMOTE_PASS`
- `TICK_MANIFEST_INVALID`
- `TICK_MANIFEST_MALFORMED`
- `TICK_MANIFEST_INCOMPLETE`
- `TICK_OUTPUT_SIZE_MISMATCH`
- `TICK_OUTPUT_HASH_MISMATCH`
- `LOCK_STALE_OVERRIDE`

Each ledger line is JSON with `schema_version`.

## Known Limitations

- Slot-A bridge integration with backend runner depends on local backend source layout.
- Windows plugin/toolchain integration is still experimental.
- Subprocess-mode behavior depends on externally provided bridge/command contracts.
