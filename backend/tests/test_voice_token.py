import io
import json
from fastapi.testclient import TestClient
from app import main

client = TestClient(main.app)


def test_voice_token_requires_server_key(monkeypatch):
    monkeypatch.delenv('ELEVENLABS_API_KEY', raising=False)
    assert client.post('/api/voice/token').json()['detail']['code'] == 'VOICE_UNAVAILABLE'


def test_voice_token_returns_only_single_use_token_and_limits_requests(monkeypatch):
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'test-secret')
    main._voice_tokens.clear()

    def fake_open(request, timeout):
        assert request.full_url.endswith('/single-use-token/realtime_scribe')
        assert request.get_header('Xi-api-key') == 'test-secret'
        assert timeout == 5
        return io.BytesIO(json.dumps({'token': 'sutkn_test'}).encode())

    monkeypatch.setattr(main, 'urlopen', fake_open)
    for _ in range(5):
        result = client.post('/api/voice/token')
        assert result.json() == {'token': 'sutkn_test'}
        assert result.headers['cache-control'] == 'no-store'
    assert client.post('/api/voice/token').status_code == 429
