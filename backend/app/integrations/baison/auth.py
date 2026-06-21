"""百胜 E3ERP 开放平台签名算法。

签名规则（sign_method=md5）：
1. 取所有请求参数（公共参数 + 业务参数）。
2. 排除 sign 参数。
3. 排除值为 None 的参数（byte[] 二进制参数由调用方在传参前剔除）。
4. 按参数名 ASCII 升序排序。
5. 按「参数名 + 参数值」拼接成一个字符串。
6. 在拼接字符串前后各加一次 AppSecret。
7. 对最终字符串做 MD5。
8. MD5 结果转大写，即为 sign。

文档示例：bar=2, foo=1, foo_bar=3, foobar=4
排序拼接 -> bar2foo1foo_bar3foobar4
签名原文 -> secret + bar2foo1foo_bar3foobar4 + secret
"""
import hashlib


def generate_sign(params: dict, app_secret: str) -> str:
    """根据百胜签名规则生成 sign（MD5 大写）。

    :param params: 全部请求参数（公共 + 业务），可包含 None 值与 sign。
    :param app_secret: 应用密钥，仅用于本地计算签名，不会出现在请求参数中。
    :return: 32 位大写 MD5 签名。
    """
    # 步骤 2 + 3：排除 sign，排除值为 None 的参数
    filtered = {
        key: value
        for key, value in params.items()
        if key != "sign" and value is not None
    }

    # 步骤 4 + 5：按参数名 ASCII 升序，拼接 key + value
    concatenated = "".join(f"{key}{filtered[key]}" for key in sorted(filtered.keys()))

    # 步骤 6：前后加 AppSecret
    raw = f"{app_secret}{concatenated}{app_secret}"

    # 步骤 7 + 8：MD5 后转大写
    return hashlib.md5(raw.encode("utf-8")).hexdigest().upper()
