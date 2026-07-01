"""Dependency graph extraction for Python codebases."""
import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileDependencies:
    file_path: str
    imports: list[str] = field(default_factory=list)
    imported_by: list[str] = field(default_factory=list)


class DependencyGraphBuilder:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self._module_to_file: dict[str, str] = {}
        self._graph: dict[str, FileDependencies] = {}

    def build(self) -> dict[str, FileDependencies]:
        py_files = list(self.repo_path.rglob("*.py"))
        py_files = [f for f in py_files if not self._is_ignored(f)]

        # pass 1: map every file to its importable module name
        for f in py_files:
            rel_path = str(f.relative_to(self.repo_path))
            module_name = self._path_to_module(f)
            self._module_to_file[module_name] = rel_path
            self._graph[rel_path] = FileDependencies(file_path=rel_path)

        # pass 2: parse imports and resolve to files we know about
        for f in py_files:
            rel_path = str(f.relative_to(self.repo_path))
            try:
                imported_modules = self._extract_imports(f)
            except (SyntaxError, UnicodeDecodeError):
                continue

            for mod in imported_modules:
                resolved = self._resolve_module(mod)
                if resolved and resolved != rel_path:
                    self._graph[rel_path].imports.append(resolved)
                    self._graph[resolved].imported_by.append(rel_path)

        return self._graph

    def _is_ignored(self, path: Path) -> bool:
        ignored_dirs = {"venv", ".venv", "__pycache__", ".git", "node_modules", "build", "dist"}
        return any(part in ignored_dirs for part in path.parts)

    def _path_to_module(self, file_path: Path) -> str:
        rel = file_path.relative_to(self.repo_path)
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1].removesuffix(".py")
        return ".".join(parts)

    def _extract_imports(self, file_path: Path) -> list[str]:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
        modules = []

        # get this file's package prefix for resolving relative imports
        rel = file_path.relative_to(self.repo_path)
        package_parts = list(rel.parts[:-1])  # e.g. ["src", "flask"]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    # relative import — resolve against current package
                    base = package_parts[:len(package_parts) - (node.level - 1)]
                    if node.module:
                        resolved = ".".join(base) + "." + node.module
                    else:
                        resolved = ".".join(base)
                    modules.append(resolved)
                elif node.module:
                    modules.append(node.module)

        return modules

    def _resolve_module(self, module_name: str) -> str | None:
        if module_name in self._module_to_file:
            return self._module_to_file[module_name]
        parts = module_name.split(".")
        while parts:
            parts.pop()
            candidate = ".".join(parts)
            if candidate in self._module_to_file:
                return self._module_to_file[candidate]
        return None

    def get_blast_radius(self, file_path: str) -> list[str]:
        node = self._graph.get(file_path)
        if not node:
            return []
        return node.imported_by

    def get_orphans(self) -> list[str]:
        return [
            path for path, deps in self._graph.items()
            if not deps.imported_by and not path.endswith("__init__.py")
        ]