import json

from benchmarks.paired_public.runner import fold, measure


def test_duplicate_normalization_stays_in_same_fold():
    assert fold("Card, missing!", 7) == fold("card missing", 7)


def test_paired_path_cannot_obtain_expected_label(tmp_path):
    train = [
        {"text": "card delivery missing", "category": "card"},
        {"text": "charged twice duplicate", "category": "duplicate"},
    ]
    # Deliberately wrong expected label must not become the framework's prediction.
    test = [{"text": "charged twice", "category": "card"}]
    result = measure(tmp_path, "small", train, test, False, 3)
    for arm in result["arms"].values():
        assert arm["n"] == 1
        assert arm["accuracy"] == 0
    assert result["arms"]["framework_prepared"]["prediction_disagreements_with_direct"] == 0
    assert result["audit_events"] == 2
    assert result["permits"] == 0
    lines = (tmp_path / "small/observations.jsonl").read_text().splitlines()
    assert {json.loads(line)["predicted"] for line in lines} == {"duplicate"}
