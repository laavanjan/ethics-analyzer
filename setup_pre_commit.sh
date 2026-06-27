#!/bin/bash
# Setup Pre-Commit Hook for Schema Validation
# Usage: bash setup_pre_commit.sh

HOOK_DIR=".git/hooks"
HOOK_FILE="$HOOK_DIR/pre-commit"

# Create hooks directory if it doesn't exist
mkdir -p "$HOOK_DIR"

# Create the pre-commit hook
cat > "$HOOK_FILE" << 'HOOK_CONTENT'
#!/bin/bash
# Pre-commit hook: Validate database schema fields before commit

echo "Running schema validation..."
python validate_schema.py

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Schema validation failed!"
    echo "Commit has been rejected to prevent schema drift."
    echo ""
    echo "To fix:"
    echo "1. Review the unused fields listed above"
    echo "2. Either remove unused fields from the schema definition"
    echo "3. Or add code that uses them"
    echo "4. Then run: python validate_schema.py (to verify)"
    echo "5. Then commit again"
    echo ""
    exit 1
fi

exit 0
HOOK_CONTENT

# Make the hook executable
chmod +x "$HOOK_FILE"

echo "✓ Pre-commit hook installed at: $HOOK_FILE"
echo "✓ Schema validation will run on every commit"
echo ""
echo "To test the hook:"
echo "  python validate_schema.py"
echo ""
echo "To skip validation (if needed):"
echo "  git commit --no-verify"
