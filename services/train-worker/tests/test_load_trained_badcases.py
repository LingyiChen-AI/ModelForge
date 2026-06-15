from sqlalchemy import create_engine, text


def _mk(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path}/b.db")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE badcases (id INTEGER PRIMARY KEY, dataset_version_id INT, "
                       "input TEXT, annotation TEXT)"))
        c.execute(text("INSERT INTO badcases (id, dataset_version_id, input, annotation) VALUES "
                       "(1, 10, '{\"text\":\"a\"}', '{\"label\":\"x\"}'),"
                       "(2, 10, '{\"text\":\"b\"}', NULL),"
                       "(3, 99, '{\"text\":\"c\"}', '{\"label\":\"y\"}')"))
    return eng


def test_load_trained_badcases_filters(tmp_path):
    from worker.db import load_trained_badcases
    eng = _mk(tmp_path)
    rows = load_trained_badcases(eng, [10])
    assert [r["id"] for r in rows] == [1]
    assert rows[0]["input"] == {"text": "a"} and rows[0]["annotation"] == {"label": "x"}


def test_load_trained_badcases_empty(tmp_path):
    from worker.db import load_trained_badcases
    eng = _mk(tmp_path)
    assert load_trained_badcases(eng, []) == []
