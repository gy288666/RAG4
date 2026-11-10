"""The standalone live fixture must reject unsafe roots before any app imports."""
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize('case', ['wrong_name', 'nonempty', 'missing'])
def test_fixture_rejects_existing_data_or_nonfixture_root_before_database_access(tmp_path, case):
    root = tmp_path / ('rag4-live-e2e-existing' if case != 'wrong_name' else 'business-data')
    if case != 'missing':
        root.mkdir()
    if case == 'nonempty':
        (root / 'fixture.db').write_bytes(b'existing data must not be touched')
    before = {p.name: p.read_bytes() for p in root.iterdir()} if root.exists() else None
    script = Path(__file__).parent / 'support' / 'research_live_server.py'
    result = subprocess.run([sys.executable, str(script), '--root', str(root)], capture_output=True, text=True, timeout=15)
    assert result.returncode != 0
    assert 'Fixture root must be a new empty' in result.stderr
    after = {p.name: p.read_bytes() for p in root.iterdir()} if root.exists() else None
    assert after == before
