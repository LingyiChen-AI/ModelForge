from modelforge_common.prompt_template import extract_params, validate_template


def test_extract_basic_order():
    assert extract_params("你好 {{ name }},来自 {{ city }}") == ["name", "city"]


def test_extract_dedup_chinese_no_space():
    assert extract_params("{{ 城市 }}{{a}}{{ 城市 }}") == ["城市", "a"]


def test_extract_empty():
    assert extract_params("") == []
    assert extract_params("没有参数") == []


def test_validate_ok():
    assert validate_template("{{ a }} 与 {{中文}}") == []
    assert validate_template("纯文本") == []


def test_validate_empty_param():
    assert any("空参数" in e for e in validate_template("hi {{ }}"))


def test_validate_illegal_char():
    assert any("非法" in e for e in validate_template("{{ a-b }}"))


def test_validate_unbalanced():
    assert validate_template("{{ a }") != []


def test_validate_nested():
    assert validate_template("{{ {{ x }} }}") != []
