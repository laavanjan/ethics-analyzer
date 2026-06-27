#!/usr/bin/env python3
"""
Schema Validation Script (PRIV-02)

Ensures database schema fields (Pydantic models, dataclasses) are actually
used in the codebase. Prevents schema drift by validating that:
1. All defined fields in models are referenced in application code
2. No orphaned fields exist without usage

Run as: python validate_schema.py
Or use as a pre-commit hook.
"""

import re
import sys
from pathlib import Path
from typing import Dict, Set, Tuple


def find_field_definitions() -> Dict[str, Set[str]]:
    """Extract field definitions from Pydantic models and dataclasses."""
    fields_by_model = {}

    # Check api.py for AnalyzeRequest Pydantic model
    api_file = Path("api.py")
    if api_file.exists():
        content = api_file.read_text()

        # Extract AnalyzeRequest class
        match = re.search(
            r"class AnalyzeRequest\(.*?\):(.*?)(?=^class |\Z)",
            content,
            re.MULTILINE | re.DOTALL
        )
        if match:
            class_body = match.group(1)
            fields = set()
            for line in class_body.split('\n'):
                line = line.strip()
                # Must contain ':' for type annotation and not be a control flow statement
                if ':' in line and not any(keyword in line for keyword in ['if ', 'elif ', 'else', 'for ', 'while ']):
                    field_name = line.split(':')[0].strip()
                    # Must be a valid identifier and not start with underscore
                    if field_name and field_name.replace('_', '').replace('-', '').isalnum() and not field_name.startswith('_'):
                        fields.add(field_name)
            if fields:
                fields_by_model["AnalyzeRequest"] = fields

    # Check ethics_analyzer.py for EthicsIssue dataclass
    analyzer_file = Path("ethics_analyzer.py")
    if analyzer_file.exists():
        content = analyzer_file.read_text()

        match = re.search(
            r"@dataclass\s+class EthicsIssue:(.*?)(?=^class |^@|\Z)",
            content,
            re.MULTILINE | re.DOTALL
        )
        if match:
            class_body = match.group(1)
            fields = set()
            for line in class_body.split('\n'):
                line = line.strip()
                # Must contain ':' for type annotation
                if ':' in line and not line.startswith('#'):
                    field_name = line.split(':')[0].strip()
                    # Must be a valid identifier and not start with underscore
                    if field_name and field_name.replace('_', '').isalnum() and not field_name.startswith('_'):
                        fields.add(field_name)
            if fields:
                fields_by_model["EthicsIssue"] = fields

    return fields_by_model


def find_field_usage(field_name: str) -> bool:
    """Check if a field is referenced anywhere in the codebase."""
    py_files = Path(".").glob("*.py")
    escaped_field = re.escape(field_name)

    for file in py_files:
        if file.name == "validate_schema.py":
            continue
        try:
            content = file.read_text()
            # Look for field references: model.field, .field, or field= patterns
            patterns = [
                rf"\b{escaped_field}\b",  # Direct reference
                rf"\.{escaped_field}\b",  # Attribute access
                rf'"{escaped_field}"',    # String reference
                rf"'{escaped_field}'",    # String reference
            ]
            for pattern in patterns:
                if re.search(pattern, content):
                    return True
        except (UnicodeDecodeError, PermissionError):
            continue

    return False


def validate_schema() -> Tuple[bool, str]:
    """Validate that all schema fields are actually used."""
    fields_by_model = find_field_definitions()

    if not fields_by_model:
        return True, "No dataclass or Pydantic models found"

    issues = []
    for model_name, fields in fields_by_model.items():
        for field_name in fields:
            if not find_field_usage(field_name):
                issues.append(f"  [{model_name}] Unused field: {field_name}")

    if issues:
        msg = "[FAIL] Schema validation failed:\n" + "\n".join(issues)
        return False, msg
    else:
        used_count = sum(len(f) for f in fields_by_model.values())
        msg = f"[PASS] Schema validation passed: {used_count} fields in {len(fields_by_model)} models all used"
        return True, msg


if __name__ == "__main__":
    success, message = validate_schema()
    print(message)
    sys.exit(0 if success else 1)
