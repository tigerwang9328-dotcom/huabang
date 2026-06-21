"""百胜签名算法单元测试。"""
import hashlib

from app.integrations.baison.auth import generate_sign


def test_sign_matches_doc_example():
    """文档示例：bar=2, foo=1, foo_bar=3, foobar=4。

    排序拼接 -> bar2foo1foo_bar3foobar4
    签名原文 -> secret + bar2foo1foo_bar3foobar4 + secret
    """
    secret = "secret"
    params = {"bar": 2, "foo": 1, "foo_bar": 3, "foobar": 4}

    expected_raw = "secret" + "bar2foo1foo_bar3foobar4" + "secret"
    expected = hashlib.md5(expected_raw.encode("utf-8")).hexdigest().upper()

    assert generate_sign(params, secret) == expected


def test_sign_param_order_independent():
    """传参顺序不影响签名结果（内部按 ASCII 升序排序）。"""
    secret = "secret"
    a = generate_sign({"foobar": 4, "foo": 1, "bar": 2, "foo_bar": 3}, secret)
    b = generate_sign({"bar": 2, "foo": 1, "foo_bar": 3, "foobar": 4}, secret)
    assert a == b


def test_sign_excludes_sign_param():
    """sign 参数本身不参与签名。"""
    secret = "s"
    with_sign = generate_sign({"a": 1, "sign": "WHATEVER"}, secret)
    without_sign = generate_sign({"a": 1}, secret)
    assert with_sign == without_sign


def test_sign_excludes_none_values():
    """值为 None 的参数不参与签名。"""
    secret = "s"
    with_none = generate_sign({"a": 1, "b": None}, secret)
    without = generate_sign({"a": 1}, secret)
    assert with_none == without


def test_sign_is_uppercase_32_hex():
    """sign 为 32 位大写 MD5。"""
    sign = generate_sign({"a": 1}, "s")
    assert len(sign) == 32
    assert sign == sign.upper()
    assert all(c in "0123456789ABCDEF" for c in sign)
