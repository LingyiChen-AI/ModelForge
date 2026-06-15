from worker.badcase_scoring import judge, score


def test_judge_classification():
    assert judge("classification", "售后服务", {"label": "售后服务"}) is True
    assert judge("classification", "物流查询", {"label": "售后服务"}) is False


def test_judge_pair():
    assert judge("pair", "1", {"label": "1"}) is True
    assert judge("pair", "0", {"label": "1"}) is False


def test_judge_ner():
    assert judge("ner", ["B-PER", "I-PER", "O"], {"tags": ["B-PER", "I-PER", "O"]}) is True
    assert judge("ner", ["B-PER", "O", "O"], {"tags": ["B-PER", "I-PER", "O"]}) is False
    assert judge("ner", ["B-PER", "I-PER"], {"tags": ["B-PER", "I-PER", "O"]}) is False


def test_judge_embedding():
    assert judge("embedding", "在设置页重置密码", {"pos": ["在设置页重置密码"]}) is True
    assert judge("embedding", "联系客服热线", {"pos": ["在设置页重置密码"]}) is False


def test_judge_guards():
    assert judge("classification", "x", None) is False
    assert judge("unknown_type", "x", {"label": "x"}) is False
    assert judge("ner", [], {"tags": []}) is True


def test_score_empty_and_unknown():
    assert score("classification", "/no/such/dir", []) == []
    assert score("unknown_type", "/no/such/dir", [{"input": {}, "annotation": {}}]) == [False]
