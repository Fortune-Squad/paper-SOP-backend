#!/bin/bash
# Hook: frozen-guard
# 检测 frozen 文件是否被修改
# 触发时机: 每次文件变更后

FROZEN_DIR="artifacts/04_frozen"
MANIFESTS=$(find execution -name "FROZEN_MANIFEST.json" 2>/dev/null)

# Check frozen directory
CHANGED=$(git diff --name-only HEAD -- "$FROZEN_DIR" 2>/dev/null)
if [ -n "$CHANGED" ]; then
    echo "VIOLATION: Frozen files modified:"
    echo "$CHANGED"
    exit 1
fi

# Check files listed in FROZEN_MANIFEST.json
for manifest in $MANIFESTS; do
    files=$(python3 -c "import json; m=json.load(open('$manifest')); print('\n'.join(f['path'] for f in m.get('files',[])))" 2>/dev/null)
    for f in $files; do
        if git diff --name-only HEAD -- "$f" 2>/dev/null | grep -q .; then
            echo "VIOLATION: Frozen manifest file modified: $f"
            exit 1
        fi
    done
done

echo "PASS: No frozen files modified"
exit 0
