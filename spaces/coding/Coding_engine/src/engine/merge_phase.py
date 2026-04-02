"""
Merge Phase - Post-Generation Consolidation.

ARCH-42: Merge-Phase für parallele Code-Generierung.

Nach der parallelen Code-Generierung müssen die Ergebnisse konsolidiert werden:
1. Index-Dateien generieren (index.ts, __init__.py, etc.)
2. Imports konsolidieren (duplikate entfernen, sortieren)
3. Types zusammenführen (shared types in ein Modul)
4. Export-Listen aktualisieren
5. Zirkuläre Abhängigkeiten erkennen und auflösen

Diese Phase ist KRITISCH für die Funktionsfähigkeit des generierten Codes!
"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any
from collections import defaultdict
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ImportInfo:
    """Information über einen Import."""
    module: str
    imports: list[str] = field(default_factory=list)
    is_default: bool = False
    is_type_only: bool = False
    alias: Optional[str] = None
    
    def to_ts_import(self) -> str:
        """Generiert TypeScript Import-Statement."""
        if self.is_default:
            return f"import {self.alias or self.imports[0]} from '{self.module}';"
        elif self.is_type_only:
            items = ", ".join(sorted(self.imports))
            return f"import type {{ {items} }} from '{self.module}';"
        else:
            items = ", ".join(sorted(self.imports))
            return f"import {{ {items} }} from '{self.module}';"
    
    def to_py_import(self) -> str:
        """Generiert Python Import-Statement."""
        if self.imports:
            items = ", ".join(sorted(self.imports))
            return f"from {self.module} import {items}"
        return f"import {self.module}"


@dataclass
class ExportInfo:
    """Information über einen Export."""
    name: str
    source_file: str
    export_type: str = "named"  # "named", "default", "type"
    is_reexport: bool = False


@dataclass
class TypeInfo:
    """Information über einen Type/Interface."""
    name: str
    source_file: str
    definition: str
    dependencies: list[str] = field(default_factory=list)


@dataclass
class MergeResult:
    """Ergebnis der Merge-Phase."""
    success: bool
    index_files_created: list[str] = field(default_factory=list)
    imports_consolidated: int = 0
    types_merged: int = 0
    circular_deps_fixed: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "index_files_created": self.index_files_created,
            "imports_consolidated": self.imports_consolidated,
            "types_merged": self.types_merged,
            "circular_deps_fixed": self.circular_deps_fixed,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class ImportConsolidator:
    """
    Konsolidiert Imports in einzelnen Dateien und über Dateien hinweg.
    """
    
    # TypeScript Import Pattern
    TS_IMPORT_PATTERN = re.compile(
        r"import\s+(?:type\s+)?(?:"
        r"(?P<default>\w+)|"
        r"\{\s*(?P<named>[^}]+)\s*\}|"
        r"\*\s+as\s+(?P<namespace>\w+)"
        r")\s+from\s+['\"](?P<module>[^'\"]+)['\"];?"
    )
    
    # Python Import Patterns
    PY_FROM_IMPORT = re.compile(
        r"from\s+(?P<module>[\w.]+)\s+import\s+(?P<imports>.+)"
    )
    PY_IMPORT = re.compile(r"import\s+(?P<module>[\w.]+)")
    
    def consolidate_ts_file(self, content: str) -> str:
        """Konsolidiert Imports in einer TypeScript-Datei."""
        lines = content.split("\n")
        import_lines = []
        other_lines = []
        
        # Separiere Imports von anderem Code
        in_import_section = True
        for line in lines:
            stripped = line.strip()
            if in_import_section and (
                stripped.startswith("import") or 
                stripped == "" or
                stripped.startswith("//")
            ):
                import_lines.append(line)
            else:
                in_import_section = False
                other_lines.append(line)
        
        # Parse und konsolidiere Imports
        imports_by_module: defaultdict[str, ImportInfo] = defaultdict(
            lambda: ImportInfo(module="", imports=[])
        )
        
        for line in import_lines:
            match = self.TS_IMPORT_PATTERN.search(line)
            if match:
                module = match.group("module")
                is_type = "type" in line.split("import")[0] if "import" in line else False
                
                if match.group("default"):
                    imports_by_module[module].module = module
                    imports_by_module[module].is_default = True
                    imports_by_module[module].imports.append(match.group("default"))
                elif match.group("named"):
                    named = [n.strip() for n in match.group("named").split(",")]
                    imports_by_module[module].module = module
                    imports_by_module[module].imports.extend(named)
                    if is_type:
                        imports_by_module[module].is_type_only = True
        
        # Generiere konsolidierte Imports
        consolidated_imports = []
        
        # Sortiere: 1. Node modules, 2. Relative imports
        node_modules = []
        relative_imports = []
        
        for module, info in sorted(imports_by_module.items()):
            if info.module:
                if module.startswith("."):
                    relative_imports.append(info)
                else:
                    node_modules.append(info)
        
        for info in node_modules:
            consolidated_imports.append(info.to_ts_import())
        
        if node_modules and relative_imports:
            consolidated_imports.append("")  # Leerzeile
        
        for info in relative_imports:
            consolidated_imports.append(info.to_ts_import())
        
        # Füge zusammen
        result_lines = consolidated_imports + [""] + other_lines
        return "\n".join(result_lines)
    
    def consolidate_py_file(self, content: str) -> str:
        """Konsolidiert Imports in einer Python-Datei."""
        lines = content.split("\n")
        import_lines = []
        other_lines = []
        
        # Separiere Imports von anderem Code
        in_import_section = True
        for i, line in enumerate(lines):
            stripped = line.strip()
            if in_import_section and (
                stripped.startswith("import") or
                stripped.startswith("from") or
                stripped == "" or
                stripped.startswith("#")
            ):
                import_lines.append(line)
            elif stripped.startswith('"""') or stripped.startswith("'''"):
                # Docstring - gehört zum Rest
                in_import_section = False
                other_lines.append(line)
            else:
                in_import_section = False
                other_lines.append(line)
        
        # Parse und konsolidiere
        stdlib_imports: list[str] = []
        third_party_imports: list[str] = []
        local_imports: list[str] = []
        
        imports_by_module: defaultdict[str, set[str]] = defaultdict(set)
        plain_imports: set[str] = set()
        
        for line in import_lines:
            stripped = line.strip()
            
            from_match = self.PY_FROM_IMPORT.match(stripped)
            if from_match:
                module = from_match.group("module")
                imports = [i.strip() for i in from_match.group("imports").split(",")]
                imports_by_module[module].update(imports)
                continue
            
            import_match = self.PY_IMPORT.match(stripped)
            if import_match:
                plain_imports.add(import_match.group("module"))
        
        # Kategorisiere nach Typ
        stdlib = {
            "os", "sys", "re", "json", "typing", "pathlib", "dataclasses",
            "asyncio", "collections", "datetime", "time", "logging",
            "functools", "itertools", "enum", "abc", "contextlib",
        }
        
        for module in sorted(plain_imports):
            base = module.split(".")[0]
            if base in stdlib:
                stdlib_imports.append(f"import {module}")
            elif module.startswith("src."):
                local_imports.append(f"import {module}")
            else:
                third_party_imports.append(f"import {module}")
        
        for module, imports in sorted(imports_by_module.items()):
            base = module.split(".")[0]
            import_str = f"from {module} import {', '.join(sorted(imports))}"
            
            if base in stdlib:
                stdlib_imports.append(import_str)
            elif module.startswith("src.") or module.startswith("."):
                local_imports.append(import_str)
            else:
                third_party_imports.append(import_str)
        
        # Füge zusammen
        result_lines = []
        
        if stdlib_imports:
            result_lines.extend(sorted(stdlib_imports))
            result_lines.append("")
        
        if third_party_imports:
            result_lines.extend(sorted(third_party_imports))
            result_lines.append("")
        
        if local_imports:
            result_lines.extend(sorted(local_imports))
            result_lines.append("")
        
        result_lines.extend(other_lines)
        return "\n".join(result_lines)


class IndexGenerator:
    """
    Generiert Index-Dateien (index.ts, __init__.py) für Verzeichnisse.
    """
    
    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.logger = logger.bind(component="index_generator")
    
    def generate_ts_index(self, directory: str) -> str:
        """Generiert index.ts für ein TypeScript-Verzeichnis."""
        dir_path = self.project_dir / directory
        if not dir_path.exists():
            return ""
        
        exports = []
        
        for file in sorted(dir_path.glob("*.ts")):
            if file.name in ("index.ts", "index.d.ts"):
                continue
            
            # Extrahiere Exports aus der Datei
            content = file.read_text(encoding="utf-8", errors="ignore")
            file_exports = self._extract_ts_exports(content, file.stem)
            exports.extend(file_exports)
        
        # Generiere Index
        lines = [
            f"// Auto-generated index file for {directory}",
            "// Do not edit manually - regenerate using merge phase",
            "",
        ]
        
        # Gruppiere nach Datei
        by_file: defaultdict[str, list[str]] = defaultdict(list)
        for exp in exports:
            by_file[exp.source_file].append(exp.name)
        
        for source_file, names in sorted(by_file.items()):
            names_str = ", ".join(sorted(names))
            lines.append(f"export {{ {names_str} }} from './{source_file}';")
        
        return "\n".join(lines)
    
    def generate_py_init(self, directory: str) -> str:
        """Generiert __init__.py für ein Python-Verzeichnis."""
        dir_path = self.project_dir / directory
        if not dir_path.exists():
            return ""
        
        exports = []
        
        for file in sorted(dir_path.glob("*.py")):
            if file.name in ("__init__.py", "conftest.py"):
                continue
            
            # Extrahiere Exports
            content = file.read_text(encoding="utf-8", errors="ignore")
            file_exports = self._extract_py_exports(content, file.stem)
            exports.extend(file_exports)
        
        # Generiere __init__.py
        lines = [
            '"""',
            f"Auto-generated __init__.py for {directory}",
            "Do not edit manually - regenerate using merge phase",
            '"""',
            "",
        ]
        
        # Gruppiere nach Modul
        by_module: defaultdict[str, list[str]] = defaultdict(list)
        for exp in exports:
            by_module[exp.source_file].append(exp.name)
        
        for module, names in sorted(by_module.items()):
            names_str = ", ".join(sorted(names))
            lines.append(f"from .{module} import {names_str}")
        
        # __all__
        all_names = [exp.name for exp in exports]
        if all_names:
            lines.append("")
            lines.append(f"__all__ = {sorted(all_names)!r}")
        
        return "\n".join(lines)
    
    def _extract_ts_exports(self, content: str, filename: str) -> list[ExportInfo]:
        """Extrahiert Exports aus TypeScript-Datei."""
        exports = []
        
        # export const/function/class/type/interface
        patterns = [
            r"export\s+(?:const|let|var)\s+(\w+)",
            r"export\s+function\s+(\w+)",
            r"export\s+class\s+(\w+)",
            r"export\s+type\s+(\w+)",
            r"export\s+interface\s+(\w+)",
            r"export\s+enum\s+(\w+)",
        ]
        
        for pattern in patterns:
            for match in re.finditer(pattern, content):
                exports.append(ExportInfo(
                    name=match.group(1),
                    source_file=filename,
                    export_type="named",
                ))
        
        # export default
        default_match = re.search(
            r"export\s+default\s+(?:class|function)?\s*(\w+)",
            content
        )
        if default_match:
            exports.append(ExportInfo(
                name=default_match.group(1),
                source_file=filename,
                export_type="default",
            ))
        
        return exports
    
    def _extract_py_exports(self, content: str, filename: str) -> list[ExportInfo]:
        """Extrahiert Exports aus Python-Datei."""
        exports = []
        
        # class definitions
        for match in re.finditer(r"^class\s+(\w+)", content, re.MULTILINE):
            exports.append(ExportInfo(
                name=match.group(1),
                source_file=filename,
                export_type="named",
            ))
        
        # function definitions (top-level only)
        for match in re.finditer(r"^def\s+(\w+)", content, re.MULTILINE):
            name = match.group(1)
            if not name.startswith("_"):  # Skip private
                exports.append(ExportInfo(
                    name=name,
                    source_file=filename,
                    export_type="named",
                ))
        
        # UPPER_CASE constants (top-level)
        for match in re.finditer(r"^([A-Z][A-Z0-9_]+)\s*=", content, re.MULTILINE):
            exports.append(ExportInfo(
                name=match.group(1),
                source_file=filename,
                export_type="named",
            ))
        
        return exports


class TypeMerger:
    """
    Merged TypeScript Types/Interfaces in ein gemeinsames Modul.
    """
    
    # Patterns für Type-Definitionen
    TYPE_PATTERNS = {
        "type": re.compile(r"export\s+type\s+(\w+)\s*=\s*([^;]+);"),
        "interface": re.compile(r"export\s+interface\s+(\w+)\s*(?:extends\s+[^{]+)?\{([^}]+)\}"),
    }
    
    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.logger = logger.bind(component="type_merger")
    
    def extract_types(self, directory: str) -> list[TypeInfo]:
        """Extrahiert alle Types aus einem Verzeichnis."""
        dir_path = self.project_dir / directory
        if not dir_path.exists():
            return []
        
        types = []
        
        for file in dir_path.rglob("*.ts"):
            if file.name.endswith(".d.ts"):
                continue
            
            content = file.read_text(encoding="utf-8", errors="ignore")
            
            # Type Aliases
            for match in self.TYPE_PATTERNS["type"].finditer(content):
                types.append(TypeInfo(
                    name=match.group(1),
                    source_file=str(file.relative_to(self.project_dir)),
                    definition=f"export type {match.group(1)} = {match.group(2)};",
                ))
            
            # Interfaces
            for match in self.TYPE_PATTERNS["interface"].finditer(content):
                types.append(TypeInfo(
                    name=match.group(1),
                    source_file=str(file.relative_to(self.project_dir)),
                    definition=f"export interface {match.group(1)} {{\n{match.group(2)}\n}}",
                ))
        
        return types
    
    def merge_to_file(self, types: list[TypeInfo], output_file: str) -> str:
        """Merged alle types in eine Datei."""
        lines = [
            "/**",
            " * Auto-generated types file",
            " * Contains all shared types merged from the codebase",
            " * Do not edit manually - regenerate using merge phase",
            " */",
            "",
        ]
        
        # Dedupliziere nach Name
        seen = set()
        unique_types = []
        for t in types:
            if t.name not in seen:
                seen.add(t.name)
                unique_types.append(t)
        
        # Sortiere alphabetisch
        for t in sorted(unique_types, key=lambda x: x.name):
            lines.append(f"// From: {t.source_file}")
            lines.append(t.definition)
            lines.append("")
        
        return "\n".join(lines)


class CircularDependencyResolver:
    """
    Erkennt und löst zirkuläre Abhängigkeiten.
    """
    
    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.logger = logger.bind(component="circular_resolver")
    
    def find_circular_deps(self, directory: str) -> list[tuple[str, str]]:
        """Findet zirkuläre Abhängigkeiten in einem Verzeichnis."""
        # Build dependency graph
        deps: dict[str, set[str]] = defaultdict(set)
        dir_path = self.project_dir / directory
        
        if not dir_path.exists():
            return []
        
        for file in dir_path.rglob("*.ts"):
            content = file.read_text(encoding="utf-8", errors="ignore")
            relative_path = str(file.relative_to(dir_path))
            
            # Finde relative imports
            for match in re.finditer(r"from\s+['\"](\.[^'\"]+)['\"]", content):
                imported = match.group(1)
                # Normalisiere Pfad
                imported_path = (file.parent / imported).resolve()
                try:
                    imported_relative = str(imported_path.relative_to(dir_path)) + ".ts"
                    deps[relative_path].add(imported_relative)
                except ValueError:
                    pass
        
        # Find cycles using DFS
        cycles = []
        visited = set()
        rec_stack = set()
        
        def dfs(node: str, path: list[str]) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in deps.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor, path + [neighbor]):
                        return True
                elif neighbor in rec_stack:
                    # Cycle found
                    cycles.append((node, neighbor))
                    return True
            
            rec_stack.remove(node)
            return False
        
        for node in deps:
            if node not in visited:
                dfs(node, [node])
        
        return cycles


class MergePhase:
    """
    ARCH-42: Haupt-Klasse für die Merge-Phase.
    
    Führt alle Konsolidierungsschritte durch:
    1. Index-Dateien generieren
    2. Imports konsolidieren
    3. Types zusammenführen
    4. Zirkuläre Abhängigkeiten prüfen
    """
    
    def __init__(self, project_dir: str):
        self.project_dir = Path(project_dir)
        self.consolidator = ImportConsolidator()
        self.index_generator = IndexGenerator(project_dir)
        self.type_merger = TypeMerger(project_dir)
        self.circular_resolver = CircularDependencyResolver(project_dir)
        self.logger = logger.bind(component="merge_phase")
    
    def execute(
        self,
        directories: Optional[list[str]] = None,
        generate_indexes: bool = True,
        consolidate_imports: bool = True,
        merge_types: bool = True,
        check_circular: bool = True,
    ) -> MergeResult:
        """
        Führt die komplette Merge-Phase durch.
        
        Args:
            directories: Verzeichnisse zu verarbeiten (default: src/*)
            generate_indexes: Index-Dateien generieren
            consolidate_imports: Imports konsolidieren
            merge_types: Types zusammenführen
            check_circular: Zirkuläre Abhängigkeiten prüfen
            
        Returns:
            MergeResult mit Zusammenfassung
        """
        result = MergeResult(success=True)
        
        # Default directories
        if directories is None:
            directories = self._find_source_directories()
        
        self.logger.info(
            "merge_phase_start",
            directories=directories,
        )
        
        try:
            # 1. Index-Dateien generieren
            if generate_indexes:
                for directory in directories:
                    index_files = self._generate_indexes(directory)
                    result.index_files_created.extend(index_files)
            
            # 2. Imports konsolidieren
            if consolidate_imports:
                for directory in directories:
                    count = self._consolidate_directory_imports(directory)
                    result.imports_consolidated += count
            
            # 3. Types zusammenführen
            if merge_types:
                for directory in directories:
                    count = self._merge_types(directory)
                    result.types_merged += count
            
            # 4. Zirkuläre Abhängigkeiten prüfen
            if check_circular:
                for directory in directories:
                    cycles = self.circular_resolver.find_circular_deps(directory)
                    if cycles:
                        for a, b in cycles:
                            result.warnings.append(
                                f"Circular dependency: {a} <-> {b}"
                            )
                        result.circular_deps_fixed += len(cycles)
            
            self.logger.info(
                "merge_phase_complete",
                index_files=len(result.index_files_created),
                imports_consolidated=result.imports_consolidated,
                types_merged=result.types_merged,
                warnings=len(result.warnings),
            )
            
        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            self.logger.error("merge_phase_error", error=str(e))
        
        return result
    
    def _find_source_directories(self) -> list[str]:
        """Findet alle Source-Verzeichnisse."""
        directories = []
        
        # Frontend
        for name in ("src/components", "src/pages", "src/hooks", "src/services"):
            if (self.project_dir / name).exists():
                directories.append(name)
        
        # Backend
        for name in ("src/routes", "src/models", "backend", "api"):
            if (self.project_dir / name).exists():
                directories.append(name)
        
        # Root src
        if (self.project_dir / "src").exists():
            directories.append("src")
        
        return directories
    
    def _generate_indexes(self, directory: str) -> list[str]:
        """Generiert Index-Dateien für ein Verzeichnis."""
        created = []
        dir_path = self.project_dir / directory
        
        if not dir_path.exists():
            return created
        
        # TypeScript index.ts
        ts_files = list(dir_path.glob("*.ts"))
        if ts_files and not (dir_path / "index.ts").exists():
            content = self.index_generator.generate_ts_index(directory)
            if content:
                index_path = dir_path / "index.ts"
                index_path.write_text(content, encoding="utf-8")
                created.append(str(index_path.relative_to(self.project_dir)))
        
        # Python __init__.py
        py_files = list(dir_path.glob("*.py"))
        if py_files and not (dir_path / "__init__.py").exists():
            content = self.index_generator.generate_py_init(directory)
            if content:
                init_path = dir_path / "__init__.py"
                init_path.write_text(content, encoding="utf-8")
                created.append(str(init_path.relative_to(self.project_dir)))
        
        return created
    
    def _consolidate_directory_imports(self, directory: str) -> int:
        """Konsolidiert Imports in allen Dateien eines Verzeichnisses."""
        count = 0
        dir_path = self.project_dir / directory
        
        if not dir_path.exists():
            return count
        
        # TypeScript
        for file in dir_path.rglob("*.ts"):
            try:
                content = file.read_text(encoding="utf-8")
                new_content = self.consolidator.consolidate_ts_file(content)
                if new_content != content:
                    file.write_text(new_content, encoding="utf-8")
                    count += 1
            except Exception as e:
                self.logger.warning(
                    "consolidate_error",
                    file=str(file),
                    error=str(e),
                )
        
        # Python
        for file in dir_path.rglob("*.py"):
            try:
                content = file.read_text(encoding="utf-8")
                new_content = self.consolidator.consolidate_py_file(content)
                if new_content != content:
                    file.write_text(new_content, encoding="utf-8")
                    count += 1
            except Exception as e:
                self.logger.warning(
                    "consolidate_error",
                    file=str(file),
                    error=str(e),
                )
        
        return count
    
    def _merge_types(self, directory: str) -> int:
        """Merged Types in ein gemeinsames Modul."""
        types = self.type_merger.extract_types(directory)
        
        if not types:
            return 0
        
        # Schreibe merged types
        output_file = self.project_dir / directory / "types.ts"
        content = self.type_merger.merge_to_file(types, str(output_file))
        output_file.write_text(content, encoding="utf-8")
        
        return len(types)


# Convenience function
def run_merge_phase(project_dir: str) -> MergeResult:
    """
    Convenience function für die Merge-Phase.
    
    ```python
    from src.engine.merge_phase import run_merge_phase
    
    result = run_merge_phase("./output_project")
    if result.success:
        print(f"Created {len(result.index_files_created)} index files")
    ```
    """
    phase = MergePhase(project_dir)
    return phase.execute()