from training.datasets.build_retrieval_dataset import build_rows
from training.evaluation.evaluate_ranking import evaluate


def test_build_rows_prefers_high_scoring_hard_negatives():
    records = [
        {
            "query_id": "q1",
            "query": "什么是证据门禁？",
            "candidates": [
                {"id": "positive", "text": "正例", "label": True, "score": 0.8},
                {"id": "easy", "text": "简单负例", "label": False, "score": 0.1},
                {"id": "hard", "text": "困难负例", "label": False, "score": 0.9},
            ],
        }
    ]

    embedding, reranker, ranking = build_rows(records, max_negatives=1)

    assert embedding == [
        {
            "query_id": "q1",
            "anchor": "什么是证据门禁？",
            "positive": "正例",
            "negative": "困难负例",
        }
    ]
    assert [row["passage"] for row in reranker] == ["正例", "困难负例"]
    assert ranking[0]["ranked_ids"] == ["hard", "positive", "easy"]


def test_ranking_metrics_are_computed_at_each_cutoff():
    result = evaluate(
        [{"query_id": "q1", "relevant_ids": ["a"], "ranked_ids": ["b", "a", "c"]}],
        [1, 2],
    )

    assert result["queries"] == 1
    assert result["metrics"]["@1"] == {"recall": 0.0, "mrr": 0.0, "ndcg": 0.0}
    assert result["metrics"]["@2"]["recall"] == 1.0
    assert result["metrics"]["@2"]["mrr"] == 0.5
