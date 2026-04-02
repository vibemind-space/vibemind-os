"""
Merger - Resolves conflicts between parallel code generation.

This module handles:
1. File conflict detection
2. Import resolution
3. Content merging
4. Deduplication
"""
import re
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import structlog

from src.autogen.cli_wrapper import GeneratedFile

logger = structlog.get_logger()


@dataclass
class MergeConflict:
    """Represents a conflict between generated files."""
    path: str
    sources: list[str]  # Slice IDs that generated this file
    conflict_type: str  # "duplicate", "different_content", "import_mismatch"
    resolution: Optional[str] = None  # How it was resolved

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "sources": self.sources,
            "conflict_type": self.conflict_type,
            "resolution": self.resolution,
        }


@dataclass
class MergeResult:
    """Result from merging generated files."""
    success: bool
    merged_files: list[GeneratedFile] = field(default_factory=list)
    conflicts: list[MergeConflict] = field(default_factory=list)
    conflicts_resolved: int = 0
    conflicts_unresolved: int = 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "merged_files": len(self.merged_files),
            "conflicts": [c.to_dict() for c in self.conflicts],
            "conflicts_resolved": self.conflicts_resolved,
            "conflicts_unresolved": self.conflicts_unresolved,
        }


class CodeMerger:
    """
    Merges code from multiple parallel agents.

    Handles:
    - Duplicate file detection
    - Content merging for same files
    - Import deduplication
    - Conflict resolution
    """

    def __init__(self):
        self.logger = logger.bind(component="merger")

    def merge(
        self,
        file_groups: dict[str, list[GeneratedFile]],
    ) -> MergeResult:
        """
        Merge files from multiple sources.

        Args:
            file_groups: Dict mapping slice_id to list of generated files

        Returns:
            MergeResult with merged files and conflict info
        """
        self.logger.info(
            "starting_merge",
            sources=len(file_groups),
            total_files=sum(len(files) for files in file_groups.values()),
        )

        # Group files by path
        by_path: dict[str, list[tuple[str, GeneratedFile]]] = {}
        for slice_id, files in file_groups.items():
            for file in files:
                if file.path not in by_path:
                    by_path[file.path] = []
                by_path[file.path].append((slice_id, file))

        merged_files = []
        conflicts = []
        resolved = 0
        unresolved = 0

        # Process each path
        for path, sources in by_path.items():
            if len(sources) == 1:
                # No conflict
                merged_files.append(sources[0][1])
            else:
                # Conflict detected
                conflict, merged = self._resolve_conflict(path, sources)
                conflicts.append(conflict)

                if merged:
                    merged_files.append(merged)
                    resolved += 1
                else:
                    # Use the first one as fallback
                    merged_files.append(sources[0][1])
                    unresolved += 1

        # Post-processing: fix imports
        merged_files = self._fix_imports(merged_files)

        self.logger.info(
            "merge_complete",
            files=len(merged_files),
            conflicts=len(conflicts),
            resolved=resolved,
            unresolved=unresolved,
        )

        return MergeResult(
            success=unresolved == 0,
            merged_files=merged_files,
            conflicts=conflicts,
            conflicts_resolved=resolved,
            conflicts_unresolved=unresolved,
        )

    def _resolve_conflict(
        self,
        path: str,
        sources: list[tuple[str, GeneratedFile]],
    ) -> tuple[MergeConflict, Optional[GeneratedFile]]:
        """
        Attempt to resolve a file conflict.

        Returns:
            Tuple of (conflict info, merged file or None)
        """
        slice_ids = [s[0] for s in sources]
        files = [s[1] for s in sources]

        # Check if contents are identical
        contents = [f.content for f in files]
        if len(set(contents)) == 1:
            # Same content, just deduplicate
            return (
                MergeConflict(
                    path=path,
                    sources=slice_ids,
                    conflict_type="duplicate",
                    resolution="deduplicated",
                ),
                files[0],
            )

        # Check if one is a subset of another (e.g., partial implementation)
        for i, content_a in enumerate(contents):
            for j, content_b in enumerate(contents):
                if i != j and content_a in content_b:
                    return (
                        MergeConflict(
                            path=path,
                            sources=slice_ids,
                            conflict_type="partial",
                            resolution=f"used_larger_from_{slice_ids[j]}",
                        ),
                        files[j],
                    )

        # Try to merge Python files
        if path.endswith(".py"):
            merged = self._merge_python_files(files)
            if merged:
                return (
                    MergeConflict(
                        path=path,
                        sources=slice_ids,
                        conflict_type="different_content",
                        resolution="merged_python",
                    ),
                    merged,
                )

        # Try to merge TypeScript files
        if path.endswith((".ts", ".tsx")):
            merged = self._merge_typescript_files(files)
            if merged:
                return (
                    MergeConflict(
                        path=path,
                        sources=slice_ids,
                        conflict_type="different_content",
                        resolution="merged_typescript",
                    ),
                    merged,
                )

        # Could not resolve
        return (
            MergeConflict(
                path=path,
                sources=slice_ids,
                conflict_type="different_content",
                resolution=None,
            ),
            None,
        )

    def _merge_python_files(
        self,
        files: list[GeneratedFile],
    ) -> Optional[GeneratedFile]:
        """Attempt to merge Python files."""
        # Extract imports and content from each file
        all_imports = set()
        all_content = []

        for file in files:
            imports, content = self._extract_python_imports(file.content)
            all_imports.update(imports)
            all_content.append(content)

        # Check if content sections are mergeable
        # (e.g., different functions, different classes)
        merged_content = self._merge_python_content(all_content)
        if merged_content is None:
            return None

        # Rebuild file
        import_lines = sorted(all_imports)
        final_content = "\n".join(import_lines) + "\n\n" + merged_content

        return GeneratedFile(
            path=files[0].path,
            content=final_content,
            language="python",
        )

    def _extract_python_imports(self, content: str) -> tuple[set[str], str]:
        """Extract imports from Python content."""
        lines = content.split("\n")
        imports = set()
        other_lines = []
        in_import = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith(("import ", "from ")):
                imports.add(line)
                in_import = True
            elif in_import and not stripped:
                continue  # Skip empty lines after imports
            else:
                in_import = False
                other_lines.append(line)

        return imports, "\n".join(other_lines).strip()

    def _merge_python_content(self, contents: list[str]) -> Optional[str]:
        """Try to merge Python content sections."""
        # Extract top-level definitions from each
        all_definitions = {}

        for content in contents:
            definitions = self._extract_python_definitions(content)
            for name, code in definitions.items():
                if name not in all_definitions:
                    all_definitions[name] = code
                elif all_definitions[name] != code:
                    # Conflicting definitions - can't merge
                    return None

        # Rebuild merged content
        return "\n\n".join(all_definitions.values())

    def _extract_python_definitions(self, content: str) -> dict[str, str]:
        """Extract function and class definitions."""
        definitions = {}

        # Match class definitions
        class_pattern = r"(class\s+(\w+).*?(?=\nclass\s|\ndef\s|\Z))"
        for match in re.finditer(class_pattern, content, re.DOTALL):
            definitions[f"class_{match.group(2)}"] = match.group(1).strip()

        # Match function definitions
        func_pattern = r"((?:async\s+)?def\s+(\w+).*?(?=\n(?:async\s+)?def\s|\nclass\s|\Z))"
        for match in re.finditer(func_pattern, content, re.DOTALL):
            definitions[f"func_{match.group(2)}"] = match.group(1).strip()

        return definitions

    def _merge_typescript_files(
        self,
        files: list[GeneratedFile],
    ) -> Optional[GeneratedFile]:
        """Attempt to merge TypeScript files."""
        # Extract imports
        all_imports = set()
        all_content = []

        for file in files:
            imports, content = self._extract_ts_imports(file.content)
            all_imports.update(imports)
            all_content.append(content)

        # Simple concatenation for TypeScript
        # (more sophisticated merging would need AST parsing)
        merged_content = "\n\n".join(filter(None, all_content))

        import_lines = sorted(all_imports)
        final_content = "\n".join(import_lines) + "\n\n" + merged_content

        return GeneratedFile(
            path=files[0].path,
            content=final_content,
            language="typescript",
        )

    def _extract_ts_imports(self, content: str) -> tuple[set[str], str]:
        """Extract imports from TypeScript content."""
        lines = content.split("\n")
        imports = set()
        other_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import "):
                imports.add(line)
            else:
                other_lines.append(line)

        return imports, "\n".join(other_lines).strip()

    def _fix_imports(
        self,
        files: list[GeneratedFile],
    ) -> list[GeneratedFile]:
        """Fix import statements across all files."""
        # Build a map of what's defined where
        definitions: dict[str, str] = {}  # name -> file path

        for file in files:
            if file.language == "python":
                for match in re.finditer(r"(?:class|def)\s+(\w+)", file.content):
                    definitions[match.group(1)] = file.path
            elif file.language in ("typescript", "javascript"):
                for match in re.finditer(r"export\s+(?:const|function|class)\s+(\w+)", file.content):
                    definitions[match.group(1)] = file.path

        # No import fixing needed for now - would require more context
        return files


def merge_generated_files(
    file_groups: dict[str, list[GeneratedFile]],
) -> MergeResult:
    """
    Convenience function to merge files.

    Args:
        file_groups: Dict of slice_id -> files

    Returns:
        MergeResult
    """
    merger = CodeMerger()
    return merger.merge(file_groups)
