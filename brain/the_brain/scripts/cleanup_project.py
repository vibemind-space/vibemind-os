"""
Safe Project Cleanup Script for Tahlamus

This script:
1. Verifies duplicates exist in subdirectories before deleting root copies
2. Creates backups before any deletion
3. Moves files to proper directories
4. Checks for import statements that might break
5. Generates detailed log of all changes

Usage:
    python cleanup_project.py --dry-run   # Preview changes without making them
    python cleanup_project.py --execute   # Actually perform cleanup
    python cleanup_project.py --restore   # Restore from backup
"""

import os
import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import shutil
import datetime
from pathlib import Path
from typing import List, Dict, Tuple
import json


class ProjectCleanup:
    """Safe project cleanup with verification and backup"""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self.backup_dir = self.project_root / ".cleanup_backup"
        self.log_file = self.project_root / "cleanup_log.json"
        self.timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        self.changes = {
            'duplicates_removed': [],
            'temp_files_removed': [],
            'files_moved': [],
            'directories_created': [],
            'errors': [],
            'warnings': []
        }

    def print_header(self, title: str):
        """Print formatted header"""
        print("\n" + "=" * 80)
        print(f"  {title}")
        print("=" * 80)

    def verify_duplicate(self, root_file: str, subdir: str) -> bool:
        """
        Verify that a duplicate exists in subdirectory before deleting root copy

        Args:
            root_file: Filename in root directory
            subdir: Subdirectory name (core, demos, monitoring, integrations)

        Returns:
            True if subdirectory version exists and is valid
        """
        root_path = self.project_root / root_file
        subdir_path = self.project_root / subdir / root_file

        # Check both files exist
        if not root_path.exists():
            self.changes['warnings'].append(f"Root file doesn't exist: {root_file}")
            return False

        if not subdir_path.exists():
            self.changes['errors'].append(
                f"CANNOT DELETE {root_file}: Subdirectory version missing at {subdir}/{root_file}"
            )
            return False

        # Compare file sizes (should be similar)
        root_size = root_path.stat().st_size
        subdir_size = subdir_path.stat().st_size

        size_diff_ratio = abs(root_size - subdir_size) / max(root_size, subdir_size)

        if size_diff_ratio > 0.1:  # More than 10% difference
            self.changes['warnings'].append(
                f"Size mismatch for {root_file}: root={root_size} bytes, "
                f"subdir={subdir_size} bytes (diff={size_diff_ratio:.1%})"
            )

        return True

    def create_backup(self, file_path: Path) -> Path:
        """
        Create backup of file before deletion/move

        Args:
            file_path: Path to file to backup

        Returns:
            Path to backup file
        """
        # Create backup directory if needed
        self.backup_dir.mkdir(exist_ok=True)

        # Create timestamped backup
        backup_path = self.backup_dir / f"{self.timestamp}_{file_path.name}"
        shutil.copy2(file_path, backup_path)

        return backup_path

    def check_imports(self, file_to_remove: str) -> List[str]:
        """
        Check if any Python files import the file we're about to remove

        Args:
            file_to_remove: Filename being removed (without .py)

        Returns:
            List of files that import this module
        """
        module_name = file_to_remove.replace('.py', '')
        importing_files = []

        # Search in core production files
        search_dirs = ['core', 'production', 'web', 'memory_api']

        for search_dir in search_dirs:
            search_path = self.project_root / search_dir
            if not search_path.exists():
                continue

            for py_file in search_path.glob('*.py'):
                try:
                    content = py_file.read_text(encoding='utf-8', errors='ignore')

                    # Check for various import patterns
                    if (f"import {module_name}" in content or
                        f"from {module_name}" in content):
                        importing_files.append(str(py_file.relative_to(self.project_root)))

                except Exception as e:
                    pass

        return importing_files

    def get_duplicate_files(self) -> Dict[str, str]:
        """
        Get dictionary of duplicate files: {filename: subdirectory}

        Returns:
            Dict mapping root filenames to their proper subdirectory
        """
        return {
            # Core files
            'thalamo_pc_live.py': 'core',
            'thalamo_pc_adaptive.py': 'core',
            'config_loader.py': 'core',

            # Integration files
            'atmr_torch.py': 'integrations',
            'atmr_jax.py': 'integrations',
            'atmr_fast.py': 'integrations',
            'mamba_integration.py': 'integrations',
            'mamba_real_integration.py': 'integrations',

            # Monitoring files
            'monitor_web.py': 'monitoring',
            'monitor_web_ctm.py': 'monitoring',
            'monitor_dashboard.py': 'monitoring',
            'logger_viz.py': 'monitoring',

            # Demo files
            'calculator_with_routing.py': 'demos',
            'ctm_integration.py': 'demos',
            'ctm_use_cases.py': 'demos',
            'custom_agent_routing.py': 'demos',
            'experiment_context.py': 'demos',
            'experiment_learning.py': 'demos',
            'experiment_routing.py': 'demos',
            'math_reasoning_demo.py': 'demos',
            'ode_solver_routing.py': 'demos',
            'practical_math_routing.py': 'demos',
            'quick_demo.py': 'demos',
            'reasoning_modes.py': 'demos',
            'root_finding_routing.py': 'demos',
            'simple_routing_example.py': 'demos',
        }

    def get_temp_files(self) -> List[str]:
        """Get list of temporary/test files to remove"""
        return [
            'temp_demo_learning.py',
            'temp_hierarchical_demo.py',
            'quick_test.py',
            'test_working.py',
            'test_my_config.py',
            'test_layer3.py',
            'test_docker_prediction.py',
            'test_docker_task.py',
            'test_openrouter.py',
        ]

    def get_files_to_move(self) -> Dict[str, str]:
        """
        Get files to move to proper directories

        Returns:
            Dict mapping filename to target directory
        """
        return {
            # Move to demos/
            'chat_demo.py': 'demos',
            'chat_with_brain.py': 'demos',
            'demo_execute_forced.py': 'demos',
            'demo_execute_intervention.py': 'demos',

            # Move to scripts/
            'check_install_progress.py': 'scripts',
            'check_mamba_installation.py': 'scripts',
            'install_mamba_direct.py': 'scripts',
            'setup_cpp.py': 'scripts',
            'diagnose_threat.py': 'scripts',

            # Move to tests/
            'validate_atmr.py': 'tests',
            'test_autonomous_brain.py': 'tests',
        }

    def remove_duplicates(self, dry_run: bool = True) -> int:
        """
        Remove duplicate files from root directory

        Args:
            dry_run: If True, only preview changes

        Returns:
            Number of files removed
        """
        self.print_header("REMOVING DUPLICATE FILES")

        duplicates = self.get_duplicate_files()
        removed_count = 0

        for filename, subdir in duplicates.items():
            root_path = self.project_root / filename

            print(f"\nChecking: {filename}")
            print(f"  Root:   {root_path}")
            print(f"  Subdir: {subdir}/{filename}")

            # Verify duplicate exists
            if not self.verify_duplicate(filename, subdir):
                print(f"  ❌ SKIP: Verification failed")
                continue

            # Check for imports
            imports = self.check_imports(filename)
            if imports:
                warning = f"WARNING: {filename} is imported by: {', '.join(imports[:3])}"
                print(f"  ⚠️  {warning}")
                self.changes['warnings'].append(warning)

            if dry_run:
                print(f"  🔍 DRY RUN: Would delete {filename}")
            else:
                # Create backup
                backup_path = self.create_backup(root_path)
                print(f"  💾 Backed up to: {backup_path.name}")

                # Delete root copy
                root_path.unlink()
                print(f"  ✅ Deleted: {filename}")

                self.changes['duplicates_removed'].append({
                    'file': filename,
                    'subdirectory': subdir,
                    'backup': str(backup_path)
                })
                removed_count += 1

        print(f"\n{'[DRY RUN] Would remove' if dry_run else 'Removed'}: {removed_count} duplicate files")
        return removed_count

    def remove_temp_files(self, dry_run: bool = True) -> int:
        """
        Remove temporary/test files

        Args:
            dry_run: If True, only preview changes

        Returns:
            Number of files removed
        """
        self.print_header("REMOVING TEMPORARY/TEST FILES")

        temp_files = self.get_temp_files()
        removed_count = 0

        for filename in temp_files:
            file_path = self.project_root / filename

            if not file_path.exists():
                print(f"⏭️  Skip (doesn't exist): {filename}")
                continue

            print(f"\nProcessing: {filename}")

            # Check for imports
            imports = self.check_imports(filename)
            if imports:
                warning = f"WARNING: {filename} is imported by: {', '.join(imports[:3])}"
                print(f"  ⚠️  {warning}")
                self.changes['warnings'].append(warning)

            if dry_run:
                print(f"  🔍 DRY RUN: Would delete {filename}")
            else:
                # Create backup
                backup_path = self.create_backup(file_path)
                print(f"  💾 Backed up to: {backup_path.name}")

                # Delete file
                file_path.unlink()
                print(f"  ✅ Deleted: {filename}")

                self.changes['temp_files_removed'].append({
                    'file': filename,
                    'backup': str(backup_path)
                })
                removed_count += 1

        print(f"\n{'[DRY RUN] Would remove' if dry_run else 'Removed'}: {removed_count} temporary files")
        return removed_count

    def move_files(self, dry_run: bool = True) -> int:
        """
        Move files to proper directories

        Args:
            dry_run: If True, only preview changes

        Returns:
            Number of files moved
        """
        self.print_header("MOVING FILES TO PROPER DIRECTORIES")

        files_to_move = self.get_files_to_move()
        moved_count = 0

        for filename, target_dir in files_to_move.items():
            source_path = self.project_root / filename
            target_path = self.project_root / target_dir / filename

            if not source_path.exists():
                print(f"⏭️  Skip (doesn't exist): {filename}")
                continue

            print(f"\nMoving: {filename}")
            print(f"  From: {source_path}")
            print(f"  To:   {target_path}")

            # Check if target already exists
            if target_path.exists():
                print(f"  ⚠️  WARNING: Target already exists!")
                self.changes['warnings'].append(
                    f"Target exists for {filename} in {target_dir}/"
                )
                continue

            if dry_run:
                print(f"  🔍 DRY RUN: Would move to {target_dir}/")
            else:
                # Create target directory if needed
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if target_path.parent not in [x['directory'] for x in self.changes['directories_created']]:
                    self.changes['directories_created'].append({
                        'directory': str(target_path.parent)
                    })

                # Create backup
                backup_path = self.create_backup(source_path)
                print(f"  💾 Backed up to: {backup_path.name}")

                # Move file
                shutil.move(str(source_path), str(target_path))
                print(f"  ✅ Moved to: {target_dir}/{filename}")

                self.changes['files_moved'].append({
                    'file': filename,
                    'from': str(source_path),
                    'to': str(target_path),
                    'backup': str(backup_path)
                })
                moved_count += 1

        print(f"\n{'[DRY RUN] Would move' if dry_run else 'Moved'}: {moved_count} files")
        return moved_count

    def save_log(self):
        """Save changes log to JSON file"""
        self.changes['timestamp'] = self.timestamp

        with open(self.log_file, 'w') as f:
            json.dump(self.changes, f, indent=2)

        print(f"\n📋 Log saved to: {self.log_file}")

    def print_summary(self, dry_run: bool = True):
        """Print summary of changes"""
        self.print_header("CLEANUP SUMMARY")

        mode = "[DRY RUN - NO CHANGES MADE]" if dry_run else "[EXECUTED]"
        print(f"\n{mode}\n")

        print(f"Duplicates removed:    {len(self.changes['duplicates_removed'])}")
        print(f"Temp files removed:    {len(self.changes['temp_files_removed'])}")
        print(f"Files moved:           {len(self.changes['files_moved'])}")
        print(f"Directories created:   {len(self.changes['directories_created'])}")
        print(f"Warnings:              {len(self.changes['warnings'])}")
        print(f"Errors:                {len(self.changes['errors'])}")

        if self.changes['warnings']:
            print("\n⚠️  WARNINGS:")
            for warning in self.changes['warnings'][:10]:
                print(f"  - {warning}")
            if len(self.changes['warnings']) > 10:
                print(f"  ... and {len(self.changes['warnings']) - 10} more")

        if self.changes['errors']:
            print("\n❌ ERRORS:")
            for error in self.changes['errors']:
                print(f"  - {error}")

        if not dry_run:
            print(f"\n💾 Backups stored in: {self.backup_dir}")
            print(f"📋 Detailed log: {self.log_file}")

    def restore_from_backup(self):
        """Restore files from backup"""
        self.print_header("RESTORING FROM BACKUP")

        if not self.backup_dir.exists():
            print("❌ No backup directory found!")
            return

        # Load log
        if not self.log_file.exists():
            print("❌ No cleanup log found!")
            return

        with open(self.log_file, 'r') as f:
            log = json.load(f)

        print(f"Restoring from backup: {log.get('timestamp', 'unknown')}")

        restored = 0

        # Restore deleted duplicates
        for item in log.get('duplicates_removed', []):
            backup_file = Path(item['backup'])
            original_file = self.project_root / item['file']

            if backup_file.exists():
                shutil.copy2(backup_file, original_file)
                print(f"✅ Restored: {item['file']}")
                restored += 1

        # Restore deleted temp files
        for item in log.get('temp_files_removed', []):
            backup_file = Path(item['backup'])
            original_file = self.project_root / item['file']

            if backup_file.exists():
                shutil.copy2(backup_file, original_file)
                print(f"✅ Restored: {item['file']}")
                restored += 1

        # Restore moved files
        for item in log.get('files_moved', []):
            backup_file = Path(item['backup'])
            original_file = Path(item['from'])
            current_file = Path(item['to'])

            if backup_file.exists():
                # Remove from target location
                if current_file.exists():
                    current_file.unlink()

                # Restore to original location
                shutil.copy2(backup_file, original_file)
                print(f"✅ Restored: {item['file']}")
                restored += 1

        print(f"\n✅ Restored {restored} files from backup")


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nERROR: Please specify --dry-run, --execute, or --restore")
        sys.exit(1)

    mode = sys.argv[1]

    cleanup = ProjectCleanup()

    if mode == '--dry-run':
        print("=" * 80)
        print("  DRY RUN MODE - NO CHANGES WILL BE MADE")
        print("=" * 80)

        cleanup.remove_duplicates(dry_run=True)
        cleanup.remove_temp_files(dry_run=True)
        cleanup.move_files(dry_run=True)
        cleanup.print_summary(dry_run=True)

        print("\n" + "=" * 80)
        print("  To execute cleanup, run: python cleanup_project.py --execute")
        print("=" * 80)

    elif mode == '--execute':
        print("=" * 80)
        print("  EXECUTE MODE - CHANGES WILL BE MADE")
        print("=" * 80)

        response = input("\n⚠️  Are you sure you want to proceed? (yes/no): ")
        if response.lower() != 'yes':
            print("Aborted.")
            sys.exit(0)

        cleanup.remove_duplicates(dry_run=False)
        cleanup.remove_temp_files(dry_run=False)
        cleanup.move_files(dry_run=False)
        cleanup.save_log()
        cleanup.print_summary(dry_run=False)

        print("\n" + "=" * 80)
        print("  ✅ Cleanup complete!")
        print("  To restore: python cleanup_project.py --restore")
        print("=" * 80)

    elif mode == '--restore':
        cleanup.restore_from_backup()

    else:
        print(f"ERROR: Unknown mode '{mode}'")
        print("Use --dry-run, --execute, or --restore")
        sys.exit(1)


if __name__ == "__main__":
    main()
