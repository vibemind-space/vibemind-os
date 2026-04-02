# Backend Scripts Directory

This directory contains validation and maintenance scripts for the TRAE Backend.

## Scripts

### `validate_new_architecture.py`

**Purpose**: Validates that the refactored backend architecture is working correctly.

**Usage**:

```bash
cd backend
python scripts/validate_new_architecture.py
```

**What it checks**:

- App creation and configuration loading
- API endpoint availability
- Service manager functionality
- Health monitoring
- File structure integrity

### `validate_node_execution.py`

**Purpose**: Validates that all node templates have proper execution functions.

**Usage**:

```bash
cd backend
python scripts/validate_node_execution.py
```

**What it checks**:

- Node template execution code validation
- Service dependency availability
- Syntax validation of execution functions
- Overall system readiness for node execution

## When to Use

- **After backend changes**: Run both scripts to ensure integrity
- **Before deployment**: Validate the complete system
- **Troubleshooting**: Identify issues with architecture or node execution
- **Development**: Regular validation during feature development

## Output

Both scripts provide detailed validation reports with:

- ✅ Success indicators for passing tests
- ❌ Error indicators for failing tests
- Detailed error messages and recommendations
- Overall system health summary

## Exit Codes

- `0`: All validations passed
- `1`: One or more validations failed
