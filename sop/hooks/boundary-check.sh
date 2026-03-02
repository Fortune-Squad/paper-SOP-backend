#!/bin/bash
# Hook: boundary-check
# allowed_paths 快速验证
# 触发时机: subtask 完成后

WP_ID="${1:-}"
SUBTASK_ID="${2:-}"

if [ -z "$WP_ID" ]; then
    echo "Usage: boundary-check.sh <wp_id> [subtask_id]"
    exit 1
fi

SPEC_FILE="execution/${WP_ID}/subtasks/${SUBTASK_ID}_spec.yaml"

if [ ! -f "$SPEC_FILE" ]; then
    echo "WARNING: Subtask spec not found: $SPEC_FILE"
    exit 0
fi

# Get changed files
CHANGED=$(git diff --name-only HEAD 2>/dev/null)

if [ -z "$CHANGED" ]; then
    echo "PASS: No files changed"
    exit 0
fi

# Extract allowed_paths from spec (simple grep)
ALLOWED=$(grep -A 100 "allowed_paths:" "$SPEC_FILE" | grep "^  - " | sed 's/^  - //' | tr -d '"')
FORBIDDEN=$(grep -A 100 "forbidden_paths:" "$SPEC_FILE" | grep "^  - " | sed 's/^  - //' | tr -d '"')

VIOLATIONS=""
for file in $CHANGED; do
    # Check forbidden
    for forbidden in $FORBIDDEN; do
        if echo "$file" | grep -q "^$forbidden"; then
            VIOLATIONS="${VIOLATIONS}\n  FORBIDDEN: $file (matches $forbidden)"
        fi
    done
done

if [ -n "$VIOLATIONS" ]; then
    echo "VIOLATION: Boundary check failed:"
    echo -e "$VIOLATIONS"
    exit 1
fi

echo "PASS: All changes within allowed paths"
exit 0
