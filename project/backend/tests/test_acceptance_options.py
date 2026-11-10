from pathlib import Path
import pytest
from scripts.serve_research_acceptance import acceptance_options, acceptance_paths


def args_for(tmp_path):
    return ['--source-run', str(tmp_path / 'source'), '--vectors', str(tmp_path / 'vectors'),
        '--output', str(tmp_path / 'new'), '--allow-live']


def test_retry_mode_requires_explicit_flag_and_keeps_small_caps(tmp_path):
    args = acceptance_options(args_for(tmp_path) + ['--retry-copy', '--task-name', 'failed.json', '--database-name', 'snapshot.sqlite',
        '--completion-limit', '6', '--embedding-limit', '2'])
    assert args.retry_copy and args.completion_limit == 6 and args.embedding_limit == 2
    assert acceptance_paths(args) == (tmp_path / 'source', tmp_path / 'vectors', tmp_path / 'new')
    assert not (tmp_path / 'new').exists()


@pytest.mark.parametrize('name', ['../outside.json', '/outside.json', 'C:\\outside.json', '..'])
def test_snapshot_file_cannot_escape_source(tmp_path, name):
    with pytest.raises(ValueError): acceptance_options(args_for(tmp_path) + ['--task-name', name])


@pytest.mark.parametrize('flag,value', [('--completion-limit', '9'), ('--completion-limit', '0'), ('--embedding-limit', '4')])
def test_oversized_budget_rejected_before_credentials(tmp_path, flag, value):
    with pytest.raises(SystemExit): acceptance_options(args_for(tmp_path) + [flag, value])


@pytest.mark.parametrize('output', ['source', 'source/nested', '.'])
def test_outputs_cannot_alias_or_contain_retained_input(tmp_path, output):
    args = acceptance_options(args_for(tmp_path))
    args.output = tmp_path / output
    with pytest.raises(ValueError): acceptance_paths(args)
