#!/usr/bin/env python3
"""
Hook: log-reminder
session log 更新提醒
触发时机: 每 5 步
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

def check_session_log(project_path: str) -> int:
    logs_dir = Path(project_path) / "execution" / "session_logs"
    if not logs_dir.exists():
        print("WARNING: No session logs directory found")
        return 1
    
    logs = sorted(logs_dir.glob("session_*.md"), reverse=True)
    if not logs:
        print("WARNING: No session logs found. Create one with 'create_session'")
        return 1
    
    latest = logs[0]
    content = latest.read_text(encoding="utf-8")
    
    # Check if decisions section has recent entries
    if "## 2. Decisions" in content:
        decisions_start = content.index("## 2. Decisions")
        decisions_section = content[decisions_start:]
        decision_count = decisions_section.count("\n- ")
        
        if decision_count == 0:
            print(f"REMINDER: Session log {latest.name} has no decision entries. Log your decisions!")
            return 1
    
    print(f"PASS: Session log {latest.name} is active")
    return 0

if __name__ == "__main__":
    project_path = sys.argv[1] if len(sys.argv) > 1 else "."
    sys.exit(check_session_log(project_path))
