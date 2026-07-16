def test_core_import_does_not_load_transformers():
    import sys

    import dreamcycle

    assert dreamcycle.__version__ == "0.2.0"
    assert "transformers" not in sys.modules
    assert "torch" not in sys.modules


def test_core_import_does_not_load_http_or_ml_extras_in_fresh_process():
    import subprocess
    import sys

    script = (
        "import dreamcycle,sys; "
        "assert 'fastapi' not in sys.modules; "
        "assert 'httpx' not in sys.modules; "
        "import dreamcycle.server; "
        "assert 'fastapi' not in sys.modules; "
        "assert 'httpx' not in sys.modules; "
        "assert 'transformers' not in sys.modules; "
        "assert 'torch' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", script], check=True)
