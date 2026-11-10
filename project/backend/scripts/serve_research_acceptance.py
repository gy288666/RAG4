"""Explicit bounded live-provider acceptance server on a NEW experiment copy.

Never mutates retained input tasks. Optional retry runs only in a NEW copy.
No business .env, task, PDF, vector or DB is edited.
The key is loaded only in this process from env or the user-authorized notes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.research_acceptance_guard import AcceptanceTransport


def acceptance_options(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-run', type=Path, required=True)
    p.add_argument('--vectors', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--allow-live', action='store_true', required=True)
    p.add_argument('--retry-copy', action='store_true')
    p.add_argument('--task-name', default='task.json')
    p.add_argument('--database-name', default='research.sqlite')
    p.add_argument('--completion-limit', type=int, choices=range(1, 9), default=8)
    p.add_argument('--embedding-limit', type=int, choices=range(1, 4), default=3)
    args = p.parse_args(argv)
    for name in (args.task_name, args.database_name):
        if Path(name).name != name or name in {'.', '..'} or '/' in name or '\\' in name:
            raise ValueError('Snapshot names must be simple file names')
    return args


def acceptance_paths(args):
    source = args.source_run.resolve()
    vectors = args.vectors.resolve()
    output = args.output.resolve()
    # Reject aliasing/nesting that could accidentally mix new and retained data.
    for original in (source, vectors):
        if output == original or output in original.parents or original in output.parents:
            raise ValueError('Acceptance output must be separate from retained input')
    return source, vectors, output


def main():
    args = acceptance_options()
    source, vectors, output = acceptance_paths(args)
    task_path, database_path = source / args.task_name, source / args.database_name
    task_raw = task_path.read_bytes()
    frozen = json.loads(task_raw)
    if frozen['completion']['endpoint'] != 'https://api.siliconflow.cn/v1/chat/completions':
        raise ValueError('Source completion endpoint is not authorized')
    key = os.environ.get('RAG4_EVAL_API_KEY')
    if not key:
        notes = Path('E:/RAG3/提示.txt').read_text(encoding='utf-8-sig')
        keys = set(re.findall(r'sk-[A-Za-z0-9_-]{20,}', notes))
        if len(keys) != 1: raise ValueError('Set one RAG4_EVAL_API_KEY in memory; notes key selection is ambiguous')
        key = keys.pop()
    output.mkdir(parents=True, exist_ok=False)
    def digests(path): return {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in path.glob('*.json')}
    original_vectors = digests(vectors)
    original_db_sha = hashlib.sha256(database_path.read_bytes()).hexdigest()
    with sqlite3.connect(database_path.as_uri() + '?mode=ro', uri=True) as old, sqlite3.connect(output / 'snapshot.sqlite') as copied:
        old.backup(copied)
    shutil.copytree(vectors, output / 'vectors')
    os.environ.update(ENV_FILE=str(output / 'absent.env'), DATABASE_URL='sqlite:///' + (output / 'snapshot.sqlite').as_posix(),
        UPLOAD_DIR=str(output / 'uploads'), CHROMA_DIR=str(output / 'vectors'), DEV_MOCK_AI='false',
        SECRET_KEY='isolated-live-acceptance-login-only')
    import httpx
    import uvicorn
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.models.user import User
    from app.research import runtime
    from app.research.model import JsonResearchModel
    from app.research.store import SQLResearchTaskStore
    from app.services.vector_store import LocalVectorStore
    from app.services import vector_store, index_version_service as versions
    from app.modeling.adapters import RemoteEmbeddingAdapter
    from types import SimpleNamespace
    tasks = SQLResearchTaskStore()
    parent = tasks.load(frozen['user_id'], frozen['id'])
    store = LocalVectorStore(str(output / 'vectors'))
    vector_store._store = store
    corpus, bindings, manifest = runtime._load_scope(parent.user_id, parent.index_version_id, tuple(s.document_id for s in parent.sources), store)
    if corpus.corpus_id != parent.corpus_id or bindings != parent.sources: raise ValueError('Retained sources changed')
    if manifest['embedding']['endpoint'] != 'https://api.siliconflow.cn/v1/embeddings': raise ValueError('Frozen embedding endpoint differs')
    if args.retry_copy:
        decision = runtime.read_retry(parent.user_id, parent.id, expected_revision=parent.revision, vector_store=store)
        if not decision.eligible or not decision.sources_validated: raise ValueError('Source checkpoint cannot be safely retried')
    initial_tasks = {item['id'] for item in tasks.listing(parent.user_id, limit=100)[0]}
    before_active = versions.active_state(parent.user_id)
    with SessionLocal() as db:
        user = db.get(User, parent.user_id)
        user.email, user.password_hash, user.status = 'paper-acceptance@outlook.com', hash_password('paper-acceptance-password'), 1
        user.token_version = (user.token_version or 0) + 1
        db.commit()
    guard = AcceptanceTransport(completion_limit=args.completion_limit, embedding_limit=args.embedding_limit)
    client = httpx.Client(transport=guard, timeout=httpx.Timeout(60, connect=5), limits=httpx.Limits(keepalive_expiry=60))
    config = SimpleNamespace(llm_base_url='https://api.siliconflow.cn/v1', llm_api_key=key,
        llm_model=parent.completion.model_id, embedding_base_url='https://api.siliconflow.cn/v1', embedding_api_key=key)
    runtime.config_service.load_runtime_config = lambda db: config
    models = []
    def model_factory(*args, **kwargs):
        model = JsonResearchModel(*args, **kwargs, client=client)
        models.append(model)
        return model
    class BoundedEmbedding(RemoteEmbeddingAdapter):
        def _post(self, unused_client, batch):
            response = client.post(self._endpoint, headers={'Authorization': 'Bearer ' + self._api_key},
                json={'model': self._model_id, 'input': batch})
            response.raise_for_status()
            return response.json()
    runtime.JsonResearchModel, runtime.RemoteEmbeddingAdapter = model_factory, BoundedEmbedding
    from app.main import app
    listener = socket.socket(); listener.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=listener.getsockname()[1], access_log=False, log_level='warning'))
    def lifecycle():
        while not server.started and not server.should_exit: time.sleep(.05)
        if server.started:
            (output / 'ready.json').write_text(json.dumps({'port': listener.getsockname()[1], 'source_task_id': parent.id,
                'version_id': parent.index_version_id, 'goal': parent.goal, 'model_id': parent.completion.model_id,
                'retry_copy': args.retry_copy}), encoding='utf-8')
        while not server.should_exit:
            if (output / 'stop').exists(): server.should_exit = True
            time.sleep(.05)
    threading.Thread(target=lifecycle, daemon=True).start()
    try:
        server.run(sockets=[listener])
    finally:
        new_tasks = [tasks.load(parent.user_id, item['id']) for item in tasks.listing(parent.user_id, limit=100)[0] if item['id'] not in initial_tasks]
        current = tasks.load(parent.user_id, parent.id)
        observed_tasks = [current] if args.retry_copy else new_tasks
        record = {'completion_limit': args.completion_limit, 'embedding_request_limit': args.embedding_limit, 'automatic_network_retries': 0,
            'calls': guard.calls, 'completion_calls': [c for m in models for c in m.calls], 'cost': 'unknown',
            'parent_task_unchanged': current == parent,
            'original_task_file_unchanged': task_path.read_bytes() == task_raw,
            'original_database_unchanged': hashlib.sha256(database_path.read_bytes()).hexdigest() == original_db_sha,
            'original_vectors_unchanged': digests(vectors) == original_vectors,
            'copied_vectors_unchanged': digests(output / 'vectors') == original_vectors,
            'active_unchanged': versions.active_state(parent.user_id) == before_active,
            'task_count': len(new_tasks), 'retry_copy': args.retry_copy, 'quality_gate_passed': False,
            'successful_source_steps_unchanged': all(current.steps[i] == s for i, s in enumerate(parent.steps) if s.status == 'succeeded'),
            'original_budget_unchanged': current.budget == parent.budget,
            'code_sha256': {str(f.relative_to(Path(__file__).resolve().parents[1])).replace('\\', '/'): hashlib.sha256(f.read_bytes()).hexdigest()
                for f in [Path(__file__).resolve(), Path(__file__).with_name('research_acceptance_guard.py')] + list((Path(__file__).resolve().parents[1] / 'app/research').glob('*.py'))}}
        for task in observed_tasks:
            (output / (task.id + '.json')).write_text(task.model_dump_json(indent=2), encoding='utf-8')
            if task.artifact: (output / 'comparison.md').write_text(task.artifact.markdown, encoding='utf-8')
        (output / 'audit.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        client.close(); listener.close()


if __name__ == '__main__': main()
