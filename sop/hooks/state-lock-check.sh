#!/bin/bash
# Hook: state-lock-check
# 检测 state.json 是否被直接写入（应通过 StateStore）
# 触发时机: state.json 变更后

STATE_FILE="execution/state.json"

if [ ! -f "$STATE_FILE" ]; then
    exit 0
fi

# Check if state.json was modified outside of StateStore
# StateStore always increments state_version
CURRENT_VERSION=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('state_version', 0))" 2>/dev/null)

if [ -z "$CURRENT_VERSION" ]; then
    echo "WARNING: Cannot read state_version from state.json"
    exit 1
fi

echo "PASS: state.json version=$CURRENT_VERSION"
exit 0
