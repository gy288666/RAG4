import json
import httpx
import pytest
import threading
from concurrent.futures import ThreadPoolExecutor
from scripts.research_acceptance_guard import AcceptanceTransport


def test_failed_network_attempt_consumes_budget_and_has_no_secrets():
    def failed(request):
        raise httpx.ConnectTimeout('sensitive upstream detail', request=request)
    transport = AcceptanceTransport(inner=httpx.MockTransport(failed), completion_limit=1)
    with httpx.Client(transport=transport) as client:
        with pytest.raises(httpx.ConnectTimeout):
            client.post('https://api.siliconflow.cn/v1/chat/completions', headers={'Authorization': 'Bearer secret'}, json={'input': 'private text'})
        with pytest.raises(RuntimeError):
            client.post('https://api.siliconflow.cn/v1/chat/completions')
    assert len(transport.calls) == 1
    assert transport.calls[0]['status'] == 'failed'
    assert 'secret' not in json.dumps(transport.calls) and 'private text' not in json.dumps(transport.calls)
    assert 'sensitive' not in json.dumps(transport.calls)


@pytest.mark.parametrize('url', ['http://api.siliconflow.cn/v1/embeddings', 'https://evil.invalid/v1/embeddings',
    'https://api.siliconflow.cn/v1/embeddings?key=x', 'https://api.siliconflow.cn/v1/models',
    'https://api.siliconflow.cn:444/v1/embeddings', 'https://user:pass@api.siliconflow.cn/v1/embeddings'])
def test_unapproved_endpoint_never_reaches_transport(url):
    def forbidden(request): pytest.fail('Unapproved endpoint escaped guard')
    guard = AcceptanceTransport(inner=httpx.MockTransport(forbidden))
    with httpx.Client(transport=guard) as client:
        with pytest.raises(ValueError): client.post(url)
    assert guard.calls == []


def test_independent_caps_and_bounded_usage_fields():
    guard = AcceptanceTransport(inner=httpx.MockTransport(lambda r: httpx.Response(200, json={'usage': {'total_tokens': 12, 'secret': 'x'}})),
        completion_limit=1, embedding_limit=1)
    with httpx.Client(transport=guard) as client:
        for path in ('embeddings', 'chat/completions'): client.post('https://api.siliconflow.cn/v1/' + path)
        with pytest.raises(RuntimeError): client.post('https://api.siliconflow.cn/v1/embeddings')
    assert len(guard.calls) == 2 and all(c['usage'] == {'total_tokens': 12} for c in guard.calls)


@pytest.mark.parametrize('limits', [{'completion_limit': 9}, {'completion_limit': True}, {'embedding_limit': 4}, {'embedding_limit': 0}])
def test_unsafe_caps_rejected(limits):
    with pytest.raises(ValueError): AcceptanceTransport(**limits)


def test_concurrent_reservations_cannot_escape_global_cap():
    entered, release = threading.Event(), threading.Event()
    def slow(request):
        entered.set()
        assert release.wait(10)
        return httpx.Response(200, json={})
    guard = AcceptanceTransport(inner=httpx.MockTransport(slow), completion_limit=1)
    with httpx.Client(transport=guard) as client, ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(client.post, 'https://api.siliconflow.cn/v1/chat/completions')
        try:
            assert entered.wait(10)
            with pytest.raises(RuntimeError): client.post('https://api.siliconflow.cn/v1/chat/completions')
        finally:
            release.set()
        assert first.result().status_code == 200
    assert len(guard.calls) == 1
