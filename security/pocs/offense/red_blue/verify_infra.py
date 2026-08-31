"""Verify all Red vs Blue infrastructure targets."""
from infra import check_all_targets, get_available_target_summary

status = check_all_targets()
print("Target Status:")
for k, v in status.items():
    icon = "OK" if v else "FAIL"
    print(f"  {k}: {icon}")
print()
print("Available targets:")
print(get_available_target_summary())
