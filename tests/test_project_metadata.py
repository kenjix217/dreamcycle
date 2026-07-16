import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_apache_license_notice_and_package_metadata_are_consistent():
    license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    architecture = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")

    assert "Apache License" in license_text
    assert "Version 2.0, January 2004" in license_text
    assert "Copyright 2026 Kenny Jin" in notice
    assert 'version = "0.2.1"' in pyproject
    assert 'license = "Apache-2.0"' in pyproject
    assert 'license-files = ["LICENSE", "NOTICE"]' in pyproject
    assert '{name = "Kenny Jin", email = "kenjix217@gmail.com"}' in pyproject
    assert '"/ARCHITECTURE.md"' in pyproject
    assert architecture.count("```mermaid") >= 5


def test_source_has_no_jintellarcore_runtime_imports():
    forbidden = ("core.", "jintellarcore", "nervous")
    for path in (ROOT / "src" / "dreamcycle").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not any(name.startswith(forbidden) for name in imports), path
