"""New experiment budgets fork the old checkpoint, never enlarge it in place."""
import hashlib
import json
import sqlite3
import pytest

from scripts.reverify_research_batches import fork_checkpoint


def parent_run(tmp_path):
    parent = tmp_path/'old'
    parent.mkdir()
    with sqlite3.connect(parent/'snapshot.sqlite') as db:
        db.execute('CREATE TABLE marker (value TEXT)')
        db.execute("INSERT INTO marker VALUES ('preserved')")
    report = {'task_id':'task','source_task_sha256':'a'*64,'max_requests':4,
        'calls':[{'status':'failed'}]*4,'status':'failed'}
    (parent/'report.json').write_text(json.dumps(report),encoding='utf-8')
    (parent/'task.json').write_text('{}',encoding='utf-8')
    return parent


def test_fork_has_separate_budget_and_keeps_parent_bytes(tmp_path):
    parent = parent_run(tmp_path)
    before = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in parent.iterdir()}
    result = fork_checkpoint(parent,tmp_path/'new','a'*64,2)
    assert result['max_requests']==6 and result['inherited_requests']==4 and result['new_request_budget']==2
    assert result['parent_max_requests']==4
    with sqlite3.connect(tmp_path/'new/snapshot.sqlite') as db:
        assert db.execute('SELECT value FROM marker').fetchone()==('preserved',)
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in parent.iterdir()}


def test_fork_rejects_wrong_lineage_and_overwrite(tmp_path):
    parent = parent_run(tmp_path)
    with pytest.raises(ValueError):fork_checkpoint(parent,tmp_path/'bad','b'*64,1)
    assert not (tmp_path/'bad').exists()
    with pytest.raises(FileExistsError):fork_checkpoint(parent,parent,'a'*64,1)


@pytest.mark.parametrize('budget',[0,-1,7,True])
def test_new_request_budget_is_finite(tmp_path,budget):
    parent = parent_run(tmp_path)
    with pytest.raises(ValueError):fork_checkpoint(parent,tmp_path/'new','a'*64,budget)
