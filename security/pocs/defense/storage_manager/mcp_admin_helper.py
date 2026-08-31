"""
Shared Admin Elevation Helper for all MCP Servers.

Provides:
  - is_admin(): Check if current process has admin rights
  - run_elevated(script, description): Run PowerShell as admin via UAC
  - ps_admin(cmd): Like ps() but with elevation
  - ps_admin_json(cmd): Like ps_json() but with elevation

The elevation flow:
  1. Tool detects admin is needed
  2. Returns { "needs_admin": true, "action": "...", "description": "..." }
  3. LLM asks user for confirmation
  4. User confirms → LLM calls the tool with elevated=true
  5. UAC popup appears → user clicks Yes
  6. Action runs with admin rights, output saved to temp file
  7. Tool reads output and returns results
"""

import json
import os
import subprocess
import tempfile
import time
import uuid


ADMIN_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), ".pc_storage_manager", "admin_output")


def is_admin():
    """Check if current process has admin privileges."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False


def run_elevated(ps_script, timeout=60):
    """
    Run a PowerShell script with admin elevation (triggers UAC).
    Returns the script's output as string, or None on failure.

    The script output is captured via a temp file since elevated
    processes can't pipe stdout back to the non-elevated parent.
    """
    os.makedirs(ADMIN_OUTPUT_DIR, exist_ok=True)

    # Unique output file
    run_id = uuid.uuid4().hex[:8]
    output_file = os.path.join(ADMIN_OUTPUT_DIR, f"admin_{run_id}.txt")
    error_file = os.path.join(ADMIN_OUTPUT_DIR, f"admin_{run_id}_err.txt")
    script_file = os.path.join(ADMIN_OUTPUT_DIR, f"admin_{run_id}.ps1")

    # Write the script with output capture
    full_script = f"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
try {{
{ps_script}
}} catch {{
    $_.Exception.Message | Out-File -FilePath '{error_file}' -Encoding UTF8
}}
"""

    # Wrap to capture output
    wrapper = f"""
[Console]::OutputEncoding = [Text.Encoding]::UTF8
& {{
{ps_script}
}} *>&1 | Out-File -FilePath '{output_file}' -Encoding UTF8
if ($Error.Count -gt 0) {{
    $Error | Out-File -FilePath '{error_file}' -Encoding UTF8
}}
"""

    with open(script_file, "w", encoding="utf-8") as f:
        f.write(wrapper)

    try:
        # Launch elevated PowerShell (triggers UAC)
        subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                f"Start-Process powershell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"{script_file}\"' -Verb RunAs -Wait"
            ],
            capture_output=True, timeout=timeout,
            encoding="utf-8", errors="replace"
        )

        # Wait briefly for output file
        for _ in range(10):
            if os.path.exists(output_file):
                break
            time.sleep(0.5)

        # Read output
        output = None
        if os.path.exists(output_file):
            with open(output_file, "r", encoding="utf-8", errors="replace") as f:
                output = f.read().strip()

        error = None
        if os.path.exists(error_file):
            with open(error_file, "r", encoding="utf-8", errors="replace") as f:
                error = f.read().strip()

        return output, error

    except subprocess.TimeoutExpired:
        return None, "Timeout — UAC may not have been confirmed"
    except Exception as e:
        return None, str(e)
    finally:
        # Cleanup
        for f in [script_file, output_file, error_file]:
            try:
                os.unlink(f)
            except:
                pass


def run_elevated_json(ps_script, timeout=60):
    """Run elevated PowerShell and parse JSON output."""
    wrapped = f"""
& {{
{ps_script}
}} | ConvertTo-Json -Depth 5 -Compress
"""
    output, error = run_elevated(wrapped, timeout)
    if output:
        try:
            return json.loads(output), None
        except json.JSONDecodeError:
            return None, f"JSON parse error: {output[:200]}"
    return None, error


def admin_required_response(action, description, tool_name, params=None):
    """
    Standard response when admin is needed.
    The LLM should show this to the user and ask for confirmation.
    """
    return json.dumps({
        "needs_admin": True,
        "action": action,
        "description": description,
        "tool_to_call": tool_name,
        "params": params or {},
        "message": f"⚠️ ADMIN NÖTIG: {description}\n"
                   f"→ Ein UAC-Popup wird erscheinen\n"
                   f"→ Klicke 'Ja' um fortzufahren\n"
                   f"→ Oder sage 'nein' um abzubrechen",
    }, indent=2)
