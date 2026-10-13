"""VERSION is the single release source for FastAPI and frontend."""
import json

from app.main import get_version, read_app_version


def test_version_uses_root_version_file(monkeypatch, tmp_path):
    source = tmp_path / 'VERSION'
    source.write_text('1.0.44\n', encoding='utf-8')
    monkeypatch.setenv('MULTIPLEKSER_VERSION_FILE', str(source))
    assert read_app_version() == '1.0.44'
    result = get_version()
    assert result.status_code == 200
    assert json.loads(result.body) == {'version': '1.0.44'}
    assert result.headers['cache-control'] == 'no-store'


def test_missing_version_does_not_claim_old_release(monkeypatch, tmp_path):
    monkeypatch.setenv('MULTIPLEKSER_VERSION_FILE', str(tmp_path / 'missing'))
    assert read_app_version() == 'unknown'
    assert json.loads(get_version().body) == {'version': 'unknown'}
