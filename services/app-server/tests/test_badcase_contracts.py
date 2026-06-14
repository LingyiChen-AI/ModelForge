import pytest
from app import badcase_contracts as bc

def test_validate_input_ok_and_bad():
    bc.validate_input("classification", {"text": "hi"})           # ok
    with pytest.raises(ValueError):
        bc.validate_input("classification", {"foo": "bar"})        # missing text
    bc.validate_input("ner", {"tokens": ["a", "b"]})
    bc.validate_input("pair", {"text_a": "x", "text_b": "y"})
    bc.validate_input("embedding", {"query": "q", "candidates": ["c1", "c2"]})

def test_validate_annotation():
    bc.validate_annotation("classification", {"label": "A"})
    with pytest.raises(ValueError):
        bc.validate_annotation("ner", {"label": "A"})              # needs tags
    bc.validate_annotation("embedding", {"pos": ["c1"], "neg": []})
    with pytest.raises(ValueError):
        bc.validate_annotation("embedding", {"pos": [], "neg": []})  # pos empty

def test_to_training_row():
    assert bc.to_training_row("classification", {"text": "hi"}, {"label": "A"}) == {"text": "hi", "label": "A"}
    assert bc.to_training_row("ner", {"tokens": ["a"]}, {"tags": ["O"]}) == {"tokens": ["a"], "tags": ["O"]}
    assert bc.to_training_row("pair", {"text_a": "x", "text_b": "y"}, {"label": "1"}) == {"text_a": "x", "text_b": "y", "label": "1"}
    assert bc.to_training_row("embedding", {"query": "q", "candidates": ["c1", "c2"]}, {"pos": ["c1"], "neg": ["c2"]}) == {"query": "q", "pos": ["c1"], "neg": ["c2"]}
    # embedding with neg omitted -> neg defaults to []
    assert bc.to_training_row("embedding", {"query": "q", "candidates": ["c1"]}, {"pos": ["c1"]}) == {"query": "q", "pos": ["c1"], "neg": []}

def test_category_and_rules():
    assert bc.category_of("classification", {"label": "A", "score": 0.9}) == "A"
    assert bc.category_of("ner", {"tags": ["O"]}) is None
    rules = bc.rules()
    assert {r["task_type"] for r in rules} == {"classification", "ner", "pair", "embedding"}
    assert "example" in rules[0]
