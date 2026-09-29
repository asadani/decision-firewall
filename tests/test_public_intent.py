import pytest

from benchmarks.public_intent.runner import LexicalModel, run


def test_public_baseline_uses_training_content_only():
    model = LexicalModel(
        [
            {"text": "card missing delivery", "category": "card"},
            {"text": "duplicate charged twice", "category": "duplicate"},
        ]
    )
    assert model.predict("charged twice") == "duplicate"
    assert model.predict("missing card") == "card"


def test_rejects_fake_ten_thousand_test_rows_before_download(tmp_path):
    with pytest.raises(ValueError, match="only 3080"):
        run(tmp_path / "results", tmp_path / "cache", 10000)
    assert not (tmp_path / "cache").exists()
