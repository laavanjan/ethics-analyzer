# Schema Validation Guide
**Preventing Database Schema Drift in Ethics Analyzer**

---

## Overview

The "Database schemas only collect fields the app actually uses" requirement ensures that data models don't accumulate unused fields. This guide explains:

1. What was audited
2. What was found
3. How to prevent schema drift going forward

---

## Quick Start

### Run Schema Validation
```bash
python validate_schema.py
```

Expected output on success:
```
[PASS] Schema validation passed: 14 fields in 2 models all used
```

### Install Pre-Commit Hook (Optional but Recommended)
```bash
bash setup_pre_commit.sh
```

This ensures validation runs automatically before every commit.

---

## What Gets Validated

### 1. Pydantic Models (FastAPI Request/Response schemas)
- **File**: `api.py`
- **Model**: `AnalyzeRequest` (lines 106-118)
- **Fields validated**: 11
- **Status**: All used ✓

### 2. Python Dataclasses
- **File**: `ethics_analyzer.py`
- **Class**: `EthicsIssue` (lines 42-50)
- **Fields validated**: 7
- **Status**: All used ✓

---

## How the Validation Works

The `validate_schema.py` script:

1. **Parses schema definitions** from source code using regex:
   - Extracts Pydantic model fields (type annotations with `:`):
     ```python
     class AnalyzeRequest(BaseModel):
         mode: str = "github"  # <- mode is extracted
     ```
   - Extracts dataclass fields similarly

2. **Searches for field usage** across all `.py` files:
   - Direct references: `body.mode`, `request.mode`
   - Attribute access: `.mode`
   - String references: `"mode"`
   - Prints detailed report if unused fields found

3. **Reports findings**:
   - Exit code 0 (success) if all fields used
   - Exit code 1 (failure) if unused fields found

---

## Field-by-Field Audit Results

### AnalyzeRequest Fields

| Field | Purpose | Where Used | Critical |
|-------|---------|-----------|----------|
| `mode` | Analysis mode (github/local/git) | api.py analyze() | Yes |
| `github_token` | GitHub API authentication | github_connector.py | Conditional |
| `repo_full_name` | Repository identifier | api.py, github_connector.py | Conditional |
| `snippets` | Code snippets for local analysis | api.py (local mode) | Conditional |
| `repo_url` | Git repository URL | git_connector.py | Conditional |
| `branch` | Git branch to analyze | git_connector.py | Conditional |
| `file_paths` | Specific files to analyze | api.py (git mode) | Conditional |
| `focus_profile` | Ethics pillar focus selection | ethics_analyzer.py | Yes |
| `languages` | Programming language filter | github_connector.py | No |
| `create_github_issue` | GitHub issue creation flag | api.py (line 246) | No |
| `save_json_report` | JSON report save flag | api.py (line 259) | No |

### EthicsIssue Fields

| Field | Purpose | Where Used |
|-------|---------|-----------|
| `file_path` | Source file of the issue | Issue reporting, JSON export |
| `line_number` | Code line number | Issue reporting, JSON export |
| `issue_type` | Category (privacy, security, etc.) | Filtering, reporting |
| `severity` | Issue severity level | Sorting, filtering |
| `message` | Issue description | Display, JSON export |
| `suggestion` | Remediation recommendation | Display, guidance |
| `code_snippet` | Code example (optional) | Display, evidence |

---

## Integration with CI/CD

### GitHub Actions Example

Add to `.github/workflows/ci.yml`:

```yaml
name: CI

on: [push, pull_request]

jobs:
  validate-schema:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Validate database schemas
        run: python validate_schema.py
```

### Local Pre-Commit Hook

Run once:
```bash
bash setup_pre_commit.sh
```

Then validation runs automatically before every commit:
```bash
$ git commit -m "My changes"
Running schema validation...
[PASS] Schema validation passed: 14 fields in 2 models all used
[main 1a2b3c4] My changes
 2 files changed...
```

To skip validation (only if absolutely necessary):
```bash
git commit --no-verify
```

---

## Troubleshooting

### Validation Fails: "Unused field: xxx"

**Problem**: A field is defined in a model but not used in code.

**Solution**:
1. Check if the field should be used:
   - If yes → Add code that references it
   - If no → Remove the field from the model definition

2. Example: Adding usage
   ```python
   # models.py
   class MyRequest(BaseModel):
       optional_field: str  # Currently unused
   
   # solution: use it somewhere
   if body.optional_field:  # Now it's used!
       handle_field(body.optional_field)
   ```

3. Example: Removing unused field
   ```python
   # Before
   class MyRequest(BaseModel):
       unused: str
       
   # After
   class MyRequest(BaseModel):
       # unused field removed
   ```

### Script Doesn't Find Fields

**Problem**: Schema validation passes but you know a field is unused.

**Likely cause**: The field isn't detected by the regex parser.

**Solution**: Check field name format:
- Must be on a single line with a type annotation
- Pattern: `field_name: FieldType [= default]`
- Invalid patterns won't be detected (multiline, unusual syntax)

---

## Best Practices

### ✓ When Adding New Fields

1. Add field to model with clear type hint:
   ```python
   class Request(BaseModel):
       user_id: str  # Identifies the requesting user
   ```

2. Use it immediately in the same PR:
   ```python
   def process(body: Request):
       if body.user_id:  # <- Usage
           log_user(body.user_id)
   ```

3. Document purpose in code comments

4. Run validation before committing:
   ```bash
   python validate_schema.py
   ```

### ✓ Before Removing Fields

1. Search codebase for all references:
   ```bash
   grep -r "field_name" --include="*.py"
   ```

2. Update dependent code to not use field

3. Remove field definition

4. Run validation:
   ```bash
   python validate_schema.py
   ```

### ✗ Don't

- Add "just in case" fields
- Rename fields without updating all references
- Leave fields unused "for future expansion"
- Skip schema validation on commits

---

## Maintenance Schedule

| Frequency | Task |
|-----------|------|
| **Per commit** | Automatic validation via pre-commit hook |
| **Per PR** | Reviewers check for unused field patterns |
| **Monthly** | Run manual audit and review field necessity |
| **Quarterly** | Full schema effectiveness review |

---

## Related Security Controls

This validation supports multiple ethics/compliance requirements:

- **PRIV-02**: Data minimization at schema level
- **PRIV-04**: No unnecessary data collection
- **Governance**: Clear data governance practices
- **Documentation**: Schema-to-code traceability

---

## Questions?

See also:
- [SCHEMA_AUDIT_REPORT.md](./SCHEMA_AUDIT_REPORT.md) - Detailed audit findings
- [field_usage_mapping.csv](./field_usage_mapping.csv) - Complete field inventory
- [validate_schema.py](./validate_schema.py) - Validation implementation

---
