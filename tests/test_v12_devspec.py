"""
v1.2 DevSpec 实现测试
测试 Phase 1-4 所有新增功能
"""
import sys
import os
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# 确保 backend 在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

passed = 0
failed = 0
errors = []

def test(name, func):
    global passed, failed, errors
    try:
        func()
        passed += 1
        print(f"  [PASS] {name}")
    except Exception as e:
        failed += 1
        errors.append((name, str(e)))
        print(f"  [FAIL] {name}: {e}")

# ========== Phase 1: Backend Services ==========
print("\n=== Phase 1: Backend Services ===")

# --- MemoryStore ---
print("\n[MemoryStore]")
from app.services.memory_store import MemoryStore, MemoryData, LearnEntry, LEARN_DOMAINS

tmp_dir = tempfile.mkdtemp()

def test_memory_initialize():
    ms = MemoryStore(tmp_dir)
    ms.initialize()
    assert (Path(tmp_dir) / "MEMORY.md").exists(), "MEMORY.md not created"

def test_memory_load_empty():
    ms = MemoryStore(tmp_dir)
    data = ms.load()
    assert isinstance(data, MemoryData)
    assert len(data.key_facts) >= 1  # template has default facts

def test_memory_add_learn():
    ms = MemoryStore(tmp_dir)
    ms.add_learn_entry("numerical", "Test lesson", "human")
    data = ms.load()
    assert len(data.corrections) >= 1
    assert data.corrections[-1].domain == "numerical"
    assert data.corrections[-1].lesson == "Test lesson"

def test_memory_add_fact():
    ms = MemoryStore(tmp_dir)
    ms.add_key_fact("Test fact")
    data = ms.load()
    assert "Test fact" in data.key_facts

def test_memory_remove_learn():
    ms = MemoryStore(tmp_dir)
    before = len(ms.load().corrections)
    ms.remove_learn_entry(0)
    after = len(ms.load().corrections)
    assert after == before - 1

def test_memory_token_budget():
    ms = MemoryStore(tmp_dir)
    count = ms.get_token_count()
    assert isinstance(count, int) and count >= 0
    assert ms.is_within_budget()  # should be within 500 tokens

def test_memory_relevant_entries():
    ms = MemoryStore(tmp_dir)
    ms.add_learn_entry("workflow", "Workflow lesson", "system")
    entries = ms.get_relevant_entries(["workflow"])
    assert len(entries) >= 1

def test_memory_injection_content():
    ms = MemoryStore(tmp_dir)
    content = ms.get_injection_content()
    assert isinstance(content, str) and len(content) > 0

def test_memory_truncate_lesson():
    ms = MemoryStore(tmp_dir)
    long_lesson = "x" * 150
    ms.add_learn_entry("token", long_lesson, "system")
    data = ms.load()
    assert len(data.corrections[-1].lesson) <= 100

test("initialize", test_memory_initialize)
test("load empty", test_memory_load_empty)
test("add learn entry", test_memory_add_learn)
test("add key fact", test_memory_add_fact)
test("remove learn entry", test_memory_remove_learn)
test("token budget", test_memory_token_budget)
test("relevant entries", test_memory_relevant_entries)
test("injection content", test_memory_injection_content)
test("truncate long lesson", test_memory_truncate_lesson)

# --- SessionLogger ---
print("\n[SessionLogger]")
from app.services.session_logger import SessionLogger

sl_dir = tempfile.mkdtemp()

def test_session_create():
    sl = SessionLogger(sl_dir)
    sid = sl.create_session(goal="Test goal", approach="Test approach")
    assert sid.startswith("session_")
    assert (Path(sl_dir) / "execution" / "session_logs" / f"{sid}.md").exists()

def test_session_log_decision():
    sl = SessionLogger(sl_dir)
    sid = sl.create_session(goal="Decision test", approach="Test")
    sl.log_decision(sid, "Made decision A")
    content = sl.get_session_content(sid)
    assert "Made decision A" in content

def test_session_wrapup():
    sl = SessionLogger(sl_dir)
    sid = sl.create_session(goal="Wrapup test", approach="Test")
    sl.wrap_up(sid, completed="Done X", remaining="Y left", next_steps="Do Z")
    content = sl.get_session_content(sid)
    assert "Done X" in content
    assert "## 3. Wrap-up" in content

def test_session_list():
    sl = SessionLogger(sl_dir)
    sessions = sl.list_sessions()
    assert len(sessions) >= 1  # at least 1 (timestamps may collide in fast tests)

def test_session_latest_wrapup():
    sl = SessionLogger(sl_dir)
    # Create a fresh session with wrapup to ensure it exists
    sid = sl.create_session(goal="Wrapup check", approach="Test")
    sl.wrap_up(sid, completed="Check done", remaining="None", next_steps="Next")
    wrapup = sl.get_latest_wrapup()
    assert wrapup is not None
    assert "Check done" in wrapup

def test_session_get_content():
    sl = SessionLogger(sl_dir)
    sessions = sl.list_sessions()
    content = sl.get_session_content(sessions[0]["session_id"])
    assert content is not None and len(content) > 0

def test_session_nonexistent():
    sl = SessionLogger(sl_dir)
    content = sl.get_session_content("session_nonexistent")
    assert content is None

test("create session", test_session_create)
test("log decision", test_session_log_decision)
test("wrap up", test_session_wrapup)
test("list sessions", test_session_list)
test("latest wrapup", test_session_latest_wrapup)
test("get content", test_session_get_content)
test("nonexistent session", test_session_nonexistent)

# --- SnapshotGenerator ---
print("\n[SnapshotGenerator]")
from app.services.snapshot_generator import SnapshotGenerator

sg_dir = tempfile.mkdtemp()

def test_snapshot_initialize():
    sg = SnapshotGenerator(sg_dir)
    sg.initialize_agents_md("Test project overview")
    assert (Path(sg_dir) / "AGENTS.md").exists()

def test_snapshot_get_content():
    sg = SnapshotGenerator(sg_dir)
    content = sg.get_agents_md_content()
    assert content is not None
    assert "AUTO-GENERATED" in content

def test_snapshot_generate_dynamic():
    sg = SnapshotGenerator(sg_dir)
    dynamic = sg.generate_agents_md_dynamic_section(
        state={"phase": "E1_EXECUTING", "total_wps": 3},
        active_wp_results=[{"wp_id": "wp1", "status": "executing"}],
        next_task={"wp_id": "wp1", "subtask": "st1"},
    )
    assert "**Phase**" in dynamic
    assert "wp1" in dynamic

def test_snapshot_update():
    sg = SnapshotGenerator(sg_dir)
    dynamic = sg.generate_agents_md_dynamic_section(
        state={"phase": "E6_FROZEN"},
        active_wp_results=[],
    )
    sg.update_agents_md(dynamic)
    content = sg.get_agents_md_content()
    assert "**Phase**" in content

def test_snapshot_get_dynamic():
    sg = SnapshotGenerator(sg_dir)
    section = sg.get_dynamic_section()
    assert section is not None and len(section) > 0

test("initialize AGENTS.md", test_snapshot_initialize)
test("get content", test_snapshot_get_content)
test("generate dynamic section", test_snapshot_generate_dynamic)
test("update AGENTS.md", test_snapshot_update)
test("get dynamic section", test_snapshot_get_dynamic)

# --- ReadinessAssessor ---
print("\n[ReadinessAssessor]")
from app.services.readiness_assessor import ReadinessAssessor, RAResult, RAVerdict

ra_dir = tempfile.mkdtemp()

def test_ra_generate_prompt():
    ra = ReadinessAssessor(ra_dir)
    prompt = ra.generate_ra_prompt(
        wp_id="wp1",
        agents_md_content="Test agents",
        memory_md_content="Test memory",
        passed_criteria="All checks passed",
        artifacts_summary="3 artifacts",
    )
    assert "wp1" in prompt
    assert "ADVANCE" in prompt

def test_ra_parse_advance():
    ra = ReadinessAssessor(ra_dir)
    raw = '```json\n{"verdict": "ADVANCE", "reasoning": "Good", "north_star_alignment": "Aligned", "missing_pieces": [], "polish_suggestions": [], "next_wp_readiness": "Ready"}\n```'
    result = ra.parse_result(raw)
    assert result.verdict == RAVerdict.ADVANCE
    assert result.reasoning == "Good"

def test_ra_parse_block():
    ra = ReadinessAssessor(ra_dir)
    raw = '{"verdict": "BLOCK", "reasoning": "Missing data", "missing_pieces": ["data X"]}'
    result = ra.parse_result(raw)
    assert result.verdict == RAVerdict.BLOCK
    assert len(result.missing_pieces) == 1

def test_ra_save_load():
    ra = ReadinessAssessor(ra_dir)
    result = RAResult(verdict=RAVerdict.POLISH, reasoning="Needs polish")
    ra.save_result("wp1", result)
    loaded = ra.load_latest_result("wp1")
    assert loaded is not None
    assert loaded.verdict == RAVerdict.POLISH

def test_ra_override():
    ra = ReadinessAssessor(ra_dir)
    result = ra.create_override("wp2", RAVerdict.BLOCK, "Human decided to proceed")
    assert result.verdict == RAVerdict.ADVANCE
    assert "override" in result.assessed_by.lower()

def test_ra_status():
    ra = ReadinessAssessor(ra_dir)
    # Create execution dir structure
    (Path(ra_dir) / "execution" / "wp1" / "gate_results").mkdir(parents=True, exist_ok=True)
    result = RAResult(verdict=RAVerdict.ADVANCE, reasoning="OK")
    ra.save_result("wp1", result)
    status = ra.get_ra_status()
    assert "wp1" in status

test("generate RA prompt", test_ra_generate_prompt)
test("parse ADVANCE result", test_ra_parse_advance)
test("parse BLOCK result", test_ra_parse_block)
test("save and load result", test_ra_save_load)
test("override BLOCK", test_ra_override)
test("get RA status", test_ra_status)

# ========== Phase 2: SOP Config Layer ==========
print("\n=== Phase 2: SOP Config Layer ===")

sop_base = Path(__file__).parent.parent.parent / "backend" / "sop"

def test_sop_commands():
    cmd_dir = sop_base / "commands"
    expected = ["init-wp.md", "execute-subtask.md", "self-test.md", "submit-review.md",
                "fix-issues.md", "freeze-wp.md", "assemble-delivery.md"]
    for f in expected:
        assert (cmd_dir / f).exists(), f"Missing command: {f}"

def test_sop_agents():
    agent_dir = sop_base / "agents"
    expected = ["executor.md", "reviewer.md", "boundary-checker.md",
                "snapshot-writer.md", "assembly-builder.md", "diagnostician.md"]
    for f in expected:
        assert (agent_dir / f).exists(), f"Missing agent: {f}"

def test_sop_rules():
    rules_dir = sop_base / "rules"
    expected = ["verification-protocol.md", "freeze-hygiene.md",
                "no-cheat-fix.md", "beware-gemini-citations.md"]
    for f in expected:
        assert (rules_dir / f).exists(), f"Missing rule: {f}"

def test_sop_hooks():
    hooks_dir = sop_base / "hooks"
    expected = ["frozen-guard.sh", "state-lock-check.sh",
                "log-reminder.py", "boundary-check.sh"]
    for f in expected:
        assert (hooks_dir / f).exists(), f"Missing hook: {f}"

def test_sop_yaml_frontmatter():
    """Check that command files have YAML front-matter"""
    cmd_file = sop_base / "commands" / "init-wp.md"
    content = cmd_file.read_text(encoding="utf-8")
    assert content.startswith("---"), "Missing YAML front-matter"
    assert "name:" in content

test("commands/ (7 files)", test_sop_commands)
test("agents/ (6 files)", test_sop_agents)
test("rules/ (4 files)", test_sop_rules)
test("hooks/ (4 files)", test_sop_hooks)
test("YAML front-matter", test_sop_yaml_frontmatter)

# ========== Phase 3: API + Integration ==========
print("\n=== Phase 3: API + Integration ===")

def test_api_imports():
    from app.api.readiness import router as ra_router
    from app.api.memory import router as mem_router
    from app.api.session_logs import router as sl_router
    assert ra_router is not None
    assert mem_router is not None
    assert sl_router is not None

def test_api_routes_count():
    from app.api.readiness import router as ra_router
    from app.api.memory import router as mem_router
    from app.api.session_logs import router as sl_router
    ra_routes = [r for r in ra_router.routes]
    mem_routes = [r for r in mem_router.routes]
    sl_routes = [r for r in sl_router.routes]
    assert len(ra_routes) == 4, f"RA routes: expected 4, got {len(ra_routes)}"
    assert len(mem_routes) == 4, f"Memory routes: expected 4, got {len(mem_routes)}"
    assert len(sl_routes) == 5, f"Session routes: expected 5, got {len(sl_routes)}"

def test_main_app_loads():
    from app.main import app
    route_paths = [r.path for r in app.routes if hasattr(r, 'path')]
    # Check new endpoints are registered
    assert any("/ra/" in p for p in route_paths), "RA routes not registered"
    assert any("/memory" in p for p in route_paths), "Memory routes not registered"
    assert any("/sessions" in p for p in route_paths), "Session routes not registered"

def test_wp_engine_imports():
    from app.services.wp_engine import WPExecutionEngine
    # Check new methods exist
    assert hasattr(WPExecutionEngine, 'process_ra_verdict')
    assert hasattr(WPExecutionEngine, '_current_session_id')

def test_wp_engine_has_services():
    """Check WPExecutionEngine initializes v1.2 services"""
    from app.services.wp_engine import WPExecutionEngine
    import inspect
    source = inspect.getsource(WPExecutionEngine.__init__)
    assert "memory_store" in source
    assert "session_logger" in source
    assert "snapshot_generator" in source
    assert "readiness_assessor" in source

test("API router imports", test_api_imports)
test("API route counts (4+4+5=13)", test_api_routes_count)
test("main app loads with new routes", test_main_app_loads)
test("WP Engine new methods", test_wp_engine_imports)
test("WP Engine has v1.2 services", test_wp_engine_has_services)

# ========== Phase 4: Frontend (file existence) ==========
print("\n=== Phase 4: Frontend Files ===")

fe_base = Path(__file__).parent.parent.parent / "frontend" / "src"

def test_fe_types():
    content = (fe_base / "types" / "index.ts").read_text(encoding="utf-8")
    assert "RAVerdictType" in content
    assert "LearnEntry" in content
    assert "MemoryData" in content
    assert "SessionLogSummary" in content

def test_fe_api_config():
    content = (fe_base / "api" / "config.ts").read_text(encoding="utf-8")
    assert "raRequest" in content
    assert "memory" in content
    assert "sessions" in content

def test_fe_api_client():
    assert (fe_base / "api" / "devspec.ts").exists()
    content = (fe_base / "api" / "devspec.ts").read_text(encoding="utf-8")
    assert "raApi" in content
    assert "memoryApi" in content
    assert "sessionApi" in content

def test_fe_components():
    assert (fe_base / "components" / "RA" / "RADashboard.tsx").exists()
    assert (fe_base / "components" / "Memory" / "MemoryBrowser.tsx").exists()
    assert (fe_base / "components" / "SessionLog" / "SessionLogViewer.tsx").exists()

def test_fe_project_detail_tabs():
    content = (fe_base / "pages" / "ProjectDetail.tsx").read_text(encoding="utf-8")
    assert "RADashboard" in content
    assert "MemoryBrowser" in content
    assert "SessionLogViewer" in content
    assert "key: 'ra'" in content
    assert "key: 'memory'" in content
    assert "key: 'sessions'" in content

test("types (RAVerdictType, LearnEntry, etc.)", test_fe_types)
test("API config (endpoints)", test_fe_api_config)
test("API client (devspec.ts)", test_fe_api_client)
test("components (3 dirs)", test_fe_components)
test("ProjectDetail tabs (3 new)", test_fe_project_detail_tabs)

# ========== Cleanup ==========
for d in [tmp_dir, sl_dir, sg_dir, ra_dir]:
    try:
        shutil.rmtree(d)
    except:
        pass

# ========== Summary ==========
print(f"\n{'='*50}")
print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
if errors:
    print(f"\nFailed tests:")
    for name, err in errors:
        print(f"  [FAIL] {name}: {err}")
print(f"{'='*50}")

sys.exit(0 if failed == 0 else 1)

