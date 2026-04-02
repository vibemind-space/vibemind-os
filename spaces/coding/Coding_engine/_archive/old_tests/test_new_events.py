"""Test that all new emergent EventTypes exist via direct AST parse."""
import ast
import sys

# Parse event_bus.py and extract all EventType members
with open("src/mind/event_bus.py", "r") as f:
    source = f.read()

tree = ast.parse(source)

# Find EventType class and get all assignments
event_types = set()
for node in ast.walk(tree):
    if isinstance(node, ast.ClassDef) and node.name == "EventType":
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        event_types.add(target.id)

new_types = [
    "PACKAGE_READY", "PACKAGE_INGESTION_FAILED",
    "TREEQUEST_VERIFICATION_STARTED", "TREEQUEST_VERIFICATION_COMPLETE",
    "TREEQUEST_FINDING_CRITICAL", "TREEQUEST_FINDING_WARNING", "TREEQUEST_FINDING_INFO",
    "TREEQUEST_NO_ISSUES",
    "EVOLUTION_REQUESTED", "EVOLUTION_STARTED", "EVOLUTION_GENERATION_COMPLETE",
    "EVOLUTION_IMPROVED", "EVOLUTION_CONVERGED", "EVOLUTION_FAILED", "EVOLUTION_APPLIED",
    "MINIBOOK_CONNECTED", "MINIBOOK_DISCONNECTED", "MINIBOOK_POST_CREATED",
    "MINIBOOK_COMMENT_ADDED", "MINIBOOK_AGENT_MENTIONED", "MINIBOOK_DISCUSSION_RESOLVED",
    "DAVELOVABLE_PROJECT_CREATED", "DAVELOVABLE_FILES_PUSHED", "DAVELOVABLE_PREVIEW_READY",
    "OPENCLAW_COMMAND_RECEIVED", "OPENCLAW_STATUS_REQUESTED", "OPENCLAW_NOTIFICATION_SENT",
    "SECURITY_VULNERABILITY",
    "PIPELINE_STARTED", "PIPELINE_PHASE_CHANGED", "PIPELINE_COMPLETED", "PIPELINE_FAILED",
]

missing = [t for t in new_types if t not in event_types]
if missing:
    print(f"MISSING: {missing}")
    sys.exit(1)
else:
    print(f"All {len(new_types)} new EventTypes found in EventType class")
    print(f"Total EventTypes in class: {len(event_types)}")

print("\n=== NEW EVENTS TEST PASSED ===")
