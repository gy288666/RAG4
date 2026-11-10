"""Isolated browser fixture server. Never import this from the production app.

Requires a NEW empty rag4-live-e2e-* temporary directory. Environment overrides
precede all app imports; the runner keeps the SQLite/files for failure inspection.
Only loopback HTTP is served; no production database or provider credentials load.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time

parser = argparse.ArgumentParser()
parser.add_argument('--root', required=True)
args = parser.parse_args()
root = Path(args.root).resolve()
if not root.is_dir() or not root.name.startswith('rag4-live-e2e-') or any(root.iterdir()):
    raise SystemExit('Fixture root must be a new empty rag4-live-e2e-* directory')
os.environ.update(ENV_FILE=str(root / 'absent.env'), DATABASE_URL='sqlite:///' + (root / 'fixture.db').as_posix(),
    UPLOAD_DIR=str(root / 'uploads'), CHROMA_DIR=str(root / 'vectors'), DEV_MOCK_AI='true',
    DOCUMENT_CHUNKING_ENGINE='rag3', SECRET_KEY='isolated-browser-test-secret-not-for-production')
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
import uvicorn
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import init_db, SessionLocal
from app.models.document import Document
from app.models.research_task import ResearchTaskRecord
from app.research import runtime
from app.research.model import JsonResearchModel
from app.services import document_service, vector_store, index_job_service as jobs, index_build_service as builds, index_version_service as versions
from types import SimpleNamespace

init_db()
store = vector_store.LocalVectorStore(str(root / 'vectors'))
vector_store._store = store
document_service.SYNCHRONOUS_PROCESSING = True
metrics = {'completion_attempts': 0, 'completion_failures': 0, 'embedding_batches': 0, 'external_provider_calls': 0}


class Embedding:
    def __init__(self, **kwargs): pass
    def embed_documents(self, texts):
        metrics['embedding_batches'] += 1
        return [[1., 2., 3.] for _ in texts]
    def embed_query(self, text): return [1., 2., 3.]


builds.RemoteEmbeddingAdapter = Embedding
runtime.RemoteEmbeddingAdapter = Embedding
client = TestClient(app)  # Seed HTTP handlers; lifespan will run in real Uvicorn.
accounts = ('student@outlook.com', 'other@outlook.com')
password = 'fixture-password-123'
for email in accounts:
    assert client.post('/api/v1/auth/register', json={'email': email, 'password': password}).status_code == 200
login = client.post('/api/v1/auth/login', json={'email': accounts[0], 'password': password}).json()['data']
headers = {'Authorization': 'Bearer ' + login['access_token']}
spec = builds.EmbeddingSpec(endpoint='https://offline.invalid/v1/embeddings', model_id='offline-embedding', version='offline-v1', dimension=3)
documents, build_ids, paths = [], [], []
for i, name in enumerate(('dpr', 'fid', 'realm')):
    text = f'Synthetic {name.upper()} fixture uses a dedicated encoder to retrieve relevant passages. This is deterministic test data.'
    response = client.post('/api/v1/docs/upload', headers=headers,
        files=[('files', (f'fixture_{name}.txt', text.encode(), 'text/plain'))])
    assert response.status_code == 200, response.text
    document_id = response.json()['data'][0]['id']
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        assert doc.status == 'ready'
        owner = doc.user_id
        paths.append(doc.local_path)
    prepared = jobs.run_job(owner, jobs.create_job(owner, document_id, idempotency_key=f'prepare-{i}').id)
    build = builds.create_build(owner, prepared.chunk_set_id, spec, idempotency_key=f'build-{i}')
    assert builds.run_build(owner, build.id, api_key='offline-placeholder', store=store).status == 'validated'
    documents.append(document_id)
    build_ids.append(build.id)
version = versions.create_version(owner, build_ids, store=store)
with SessionLocal() as db:
    baseline_namespace = runtime.config_service.load_runtime_config(db).embedding_version
config = SimpleNamespace(embedding_base_url='https://offline.invalid/v1', embedding_api_key='offline-placeholder',
    llm_base_url='https://offline.invalid/v1', llm_model='offline-contract-model', llm_api_key='offline-placeholder')
runtime.config_service.load_runtime_config = lambda db: config


def transport(request):
    """Exercise real wire parsing and source-handle checks with deterministic JSON."""
    assert request.url.host == 'offline.invalid'
    metrics['completion_attempts'] += 1
    data = json.loads(json.loads(request.content)['messages'][1]['content'])
    if 'citations' in data:
        citation = data['citations'][0]
        output = {'claims': [{'facet': 'method', 'statement': citation['text'], 'citation_id': citation['citation_id']}], 'relations': []}
    else:
        assert 'claims' in data
        if (root / 'fail-realm').exists() and any(c['document_id'] == documents[2] for c in data['claims']):
            metrics['completion_failures'] += 1
            raise httpx.ReadTimeout('deterministic offline fixture timeout', request=request)
        output = {'assessments': [{'claim_id': c['claim_id'], **{key: {'status': 'supported',
            'reason': 'Synthetic fixture source matches statement', 'support_ids': [c['sources'][0]['source_id']]}
            for key in ('attribution', 'conditions', 'entailment')}} for c in data['claims']]}
    return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(output)}}],
        'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}})


runtime.JsonResearchModel = lambda spec, **kw: JsonResearchModel(spec, **kw, transport=httpx.MockTransport(transport))
# Fail closed if a future path accidentally attempts a real provider connection.
original_connect = socket.socket.connect
def local_only(sock, address):
    if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1'):
        metrics['external_provider_calls'] += 1
        raise RuntimeError('External network disabled in isolated fixture server')
    return original_connect(sock, address)
socket.socket.connect = local_only
from app.services.index_build_service import records_digest
manifest = versions.load_version_snapshot(owner, version.id, store=store)
version_digests = {m['namespace']: records_digest(store.read_records(owner, index_version=m['namespace'])) for m in manifest['members']}
baseline_records = store.read_records(owner, index_version=baseline_namespace)
assert len(baseline_records) >= 3
baseline_digest = records_digest(baseline_records)
with SessionLocal() as db:
    checkpoint_count = db.query(ResearchTaskRecord).count()
assert checkpoint_count == 0
client.close()
listener = socket.socket()
listener.bind(('127.0.0.1', 0))
port = listener.getsockname()[1]
server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, access_log=False, log_level='warning'))


def lifecycle():
    while not server.started and not server.should_exit:
        time.sleep(.05)
    if server.started:
        (root / 'ready.json').write_text(json.dumps({'port': port, 'version_id': version.id,
            'document_ids': documents, 'source_paths': paths}), encoding='utf-8')
    while not server.should_exit:
        if (root / 'stop').exists(): server.should_exit = True
        time.sleep(.05)


threading.Thread(target=lifecycle, daemon=True).start()
try:
    server.run(sockets=[listener])
finally:
    from app.research.store import SQLResearchTaskStore
    tasks, _ = SQLResearchTaskStore().listing(owner)
    summaries = []
    for item in tasks:
        task = SQLResearchTaskStore().load(owner, item['id'])
        summaries.append({'id': task.id, 'goal': task.goal, 'status': task.status, 'revision': task.revision,
            'tool_calls_used': task.tool_calls_used, 'model_calls_used': task.model_calls_used,
            'verification_batches': len(task.verification_batches), 'artifact_attached': task.artifact is not None,
            'retry_events': len(task.retry_events),'claim_reviews':len(task.claim_reviews)})
    (root / 'audit.json').write_text(json.dumps({'metrics': metrics, 'tasks': summaries,
        'active_state': versions.active_state(owner),
        'retained_vectors_unchanged': all(value == records_digest(store.read_records(owner, index_version=namespace)) for namespace, value in version_digests.items()),
        'baseline_record_count': len(baseline_records),
        'baseline_unchanged': baseline_digest == records_digest(store.read_records(owner, index_version=baseline_namespace))}), encoding='utf-8')
    listener.close()
