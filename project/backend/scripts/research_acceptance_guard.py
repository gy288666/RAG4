"""Development-only provider allowlist and finite request ledger; no secrets logged."""
import json
import threading
from time import perf_counter
import httpx


class AcceptanceTransport(httpx.BaseTransport):
    def __init__(self, *, inner=None, completion_limit=8, embedding_limit=3):
        if type(completion_limit) is not int or not 1 <= completion_limit <= 8:
            raise ValueError('Completion cap must be 1..8')
        if type(embedding_limit) is not int or not 1 <= embedding_limit <= 3:
            raise ValueError('Embedding cap must be 1..3')
        self.inner = inner if inner is not None else httpx.HTTPTransport(retries=0)
        self.limits = {'/v1/chat/completions': completion_limit, '/v1/embeddings': embedding_limit}
        self.calls, self.lock = [], threading.Lock()

    def handle_request(self, request):
        url = request.url
        if (request.method != 'POST' or url.scheme != 'https' or url.host != 'api.siliconflow.cn'
                or url.port not in (None, 443) or url.path not in self.limits or url.query or url.userinfo):
            raise ValueError('Provider request outside acceptance scope')
        with self.lock:
            if sum(c['path'] == url.path for c in self.calls) >= self.limits[url.path]:
                raise RuntimeError('Acceptance request budget exhausted')
            entry = {'path': url.path, 'status': 'started', 'usage': {}}
            self.calls.append(entry)  # Failures consume their reservation too.
        started = perf_counter()
        try:
            response = self.inner.handle_request(request)
            response.read()
            entry.update(http_status=response.status_code, status='succeeded' if response.is_success else 'failed')
            try:
                usage = response.json().get('usage', {})
                if isinstance(usage, dict):
                    entry['usage'] = {k: v for k, v in usage.items() if k in {'prompt_tokens', 'completion_tokens', 'total_tokens'} and type(v) is int and v >= 0}
            except (ValueError, AttributeError):
                pass
            return response
        except Exception as error:
            entry.update(status='failed', error_type=type(error).__name__)
            raise
        finally:
            entry['elapsed_ms'] = round((perf_counter() - started) * 1000)

    def close(self):
        self.inner.close()
