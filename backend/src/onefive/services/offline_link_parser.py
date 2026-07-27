"""离线转存链接解析

只负责从文本/列表中提取并校验 ed2k / magnet 链接；
不依赖 p115client，不触发网络请求。
显示/整理用文件名保留原始空格；提交 115 时优先对空格做 %20 编码，避免 115 删空格落盘。
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence
from urllib.parse import parse_qsl, quote, unquote, urlencode


# 结构化匹配 ed2k：文件名允许空格，不会被截断
_ED2K_RE = re.compile(
    r"ed2k://\|file\|(?P<name>[^|]*)\|(?P<size>\d+)\|(?P<hash>[0-9a-fA-F]{32})"
    r"(?:\|h=(?P<aich>[0-9a-fA-F]+))?\|?/?",
    re.IGNORECASE,
)

# magnet：参数值允许空格（如 dn）
_MAGNET_RE = re.compile(
    r"magnet:\?xt=urn:btih:(?P<hash>[0-9a-zA-Z]{32,64})"
    r"(?P<rest>(?:&[A-Za-z0-9._-]+=[^&\n\r<>\"'`]*)*)",
    re.IGNORECASE,
)

# 仅清除零宽/不可见字符，不改文件名里的空格 only zero-width / bidi marks; do NOT convert normal/special spaces inside names
_INVISIBLE_RE = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad\u202a-\u202e\u2066-\u2069]")

# 仅清除链接外层尾部标点，不动文件名内容
_TRAILING_PUNCT_RE = re.compile(
    r"[),.;:!?]+$"
)

_HEX32_RE = re.compile(r"^[0-9a-fA-F]{32}$")


@dataclass(frozen=True)
class OfflineLink:
    """解析后的离线链接。"""

    url: str
    url_type: str
    name: str = ""


def _remove_invisible(text: str) -> str:
    """只移除零宽字符，不把空格删掉。"""
    return _INVISIBLE_RE.sub("", text or "")


def _strip_wrapping(text: str) -> str:
    value = _remove_invisible(text).strip()
    if "&" in value and ";" in value:
        value = html.unescape(value).strip()
    wraps = "\"'`"
    if len(value) >= 2 and value[0] in wraps + "<" and value[-1] in wraps + ">":
        value = value[1:-1].strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1].strip()
    value = _TRAILING_PUNCT_RE.sub("", value)
    # also strip common CJK punctuation at ends only
    value = re.sub(r"[\u3001\u3002\uff0c\uff1b\uff01\uff1f\u300d\u300f\u3011\uff09\]]+$", "", value)
    return value.strip()


def _compose_ed2k(name: str, size: str, file_hash: str, aich: str = "") -> str:
    parts = ["ed2k://|file", name, size, file_hash]
    if aich:
        parts.append(f"h={aich}")
    return "|".join(parts) + "|/"


def _normalize_ed2k(url: str) -> str | None:
    """校验并尽量保留原始 ed2k 链接。

    重点：不删除、不重编码文件名中的空格，以免影响后续整理命名。
    """
    cleaned = _strip_wrapping(url)
    source = cleaned if cleaned.lower().startswith("ed2k://") else _remove_invisible(url)
    m = _ED2K_RE.search(source)
    if not m:
        return None

    # Keep original filename EXACTLY as matched. Never strip spaces.
    name = m.group("name") or ""
    size = m.group("size") or ""
    file_hash = m.group("hash") or ""
    aich = m.group("aich") or ""

    if not size.isdigit() or int(size) <= 0:
        return None
    if not _HEX32_RE.fullmatch(file_hash):
        return None

    # Only forbidden character for structure is '|'; replace solely that.
    if "|" in name:
        name = name.replace("|", "_")

    # Prefer matched span if it already ends with standard form and name unchanged.
    matched = m.group(0)
    if (
        matched.endswith("|/")
        and (m.group("name") or "") == name
        and (m.group("hash") or "") == file_hash
        and (m.group("aich") or "") == aich
    ):
        return matched

    return _compose_ed2k(name, size, file_hash, aich)


def _decode_ed2k_name(name: str) -> str:
    """解码 ed2k 文件名（显示/整理用，保留空格）。"""
    try:
        return unquote(name or "")
    except Exception:
        return name or ""


def encode_ed2k_name_for_submit(name: str) -> str:
    """生成提交给 115 的 ed2k 文件名。

    115 对「明文空格」文件名常会直接删空格落盘，导致：
    The Devil ... → TheDevil...
    进而破坏后续识别整理。

    策略：把空格等字符做 percent-encoding（空格→%20），
    让 115 按 URL 规则解码，尽量保留原空格。
    注意：'|' 不能出现在 name 段。
    """
    decoded = _decode_ed2k_name(name)
    # 允许常见文件名安全字符原样通过；空格与其它符号编码
    # 不把空格放进 safe，强制变成 %20
    encoded = quote(decoded, safe=".-_~()[]{}@!+'")
    # 结构分隔符保护
    return encoded.replace("|", "%7C")


def build_ed2k_variants(url: str) -> list[str]:
    """为 ed2k 生成提交回退变体。

    优先「%20 编码空格」的链接（更利于 115 保留空格）；
    再回退原始/结构规范化形式。
    """
    m = _ED2K_RE.search(url or "")
    if not m:
        return [url] if url else []

    name = m.group("name") or ""
    size = m.group("size") or ""
    file_hash = m.group("hash") or ""
    aich = m.group("aich") or ""
    decoded = _decode_ed2k_name(name)

    variants: list[str] = []

    def _add(item: str) -> None:
        if item and item not in variants:
            variants.append(item)

    # 1) 优先：空格等字符 percent-encode（解决 115 删空格）
    encoded_name = encode_ed2k_name_for_submit(decoded)
    _add(_compose_ed2k(encoded_name, size, file_hash, aich))

    # 2) 原始链接（可能含明文空格）
    _add(url)

    # 3) 结构规范化（保留原始 name 形态）
    _add(_compose_ed2k(name, size, file_hash, aich))

    # 4) 解码后的明文 name（若原 name 本身带 %XX）
    if decoded != name:
        _add(_compose_ed2k(decoded, size, file_hash, aich))

    # 5) 最后手段：空格改点号（场景命名，可解析，但不再是原空格）
    dotted = " ".join(decoded.split())  # 压缩重复空白
    dotted = dotted.replace(" ", ".")
    if dotted and dotted != decoded and dotted != encoded_name:
        _add(_compose_ed2k(dotted, size, file_hash, aich))

    return variants


def prefer_ed2k_submit_url(url: str) -> str:
    """选取最优先的 ed2k 提交形态。"""
    variants = build_ed2k_variants(url)
    return variants[0] if variants else (url or "")


def extract_ed2k_hash(url: str) -> str:
    """提取 ed2k 文件 hash（32 hex）。"""
    m = _ED2K_RE.search(url or "")
    if not m:
        return ""
    return (m.group("hash") or "").upper()


def compact_filename(name: str) -> str:
    """去掉空白后的文件名，用于判断 115 是否删空格。"""
    return "".join(ch for ch in (name or "") if not ch.isspace())


def _normalize_magnet(url: str) -> str | None:
    """校验 magnet，尽量保留原始 dn 文本。

    不把空格强制转成 + / %20（主提交路径）。
    """
    cleaned = _strip_wrapping(url)
    source = cleaned if cleaned.lower().startswith("magnet:?") else _remove_invisible(url)
    m = _MAGNET_RE.search(source)
    if not m:
        return None

    btih = m.group("hash") or ""
    if re.fullmatch(r"[0-9a-fA-F]{40}", btih):
        btih_norm = btih.lower()
    elif re.fullmatch(r"[A-Za-z2-7]{32}", btih):
        btih_norm = btih.upper()
    else:
        return None

    matched = m.group(0)
    rest = m.group("rest") or ""
    rest = _TRAILING_PUNCT_RE.sub("", rest)
    rest = re.sub(r"[\u3001\u3002\uff0c\uff1b\uff01\uff1f\u300d\u300f\u3011\uff09\]]+$", "", rest)

    # If original already has valid btih and no dirty trailing junk, keep original match.
    # Only normalize xt hash case when needed; keep dn text as-is (including spaces).
    if matched.lower().startswith("magnet:?xt=urn:btih:") and rest == (m.group("rest") or ""):
        # rebuild only xt hash case; keep rest literally
        return f"magnet:?xt=urn:btih:{btih_norm}{rest}"

    query = f"xt=urn:btih:{btih_norm}"
    if rest.startswith("&"):
        # Keep parameter values literally; do not convert spaces to '+'
        # just drop trailing CJK glued to values if any
        pieces = []
        for part in rest.lstrip("&").split("&"):
            if not part or "=" not in part:
                continue
            k, v = part.split("=", 1)
            key = (k or "").strip()
            if not key or key.lower() == "xt":
                continue
            val = re.sub(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]+$", "", v)
            pieces.append(f"{key}={val}")
        if pieces:
            query = query + "&" + "&".join(pieces)
    elif rest:
        query = query + rest
    return f"magnet:?{query}"


def _guess_ed2k_name(url: str) -> str:
    try:
        parts = url.split("|")
        if len(parts) >= 3 and parts[1].lower() == "file":
            # display only: unquote for readability, do not affect submitted url
            return unquote(parts[2])
    except Exception:
        pass
    return ""


def _guess_magnet_name(url: str) -> str:
    try:
        if "dn=" not in url.lower():
            return ""
        query = url.split("?", 1)[-1]
        for key, value in parse_qsl(query, keep_blank_values=True):
            if key.lower() == "dn":
                return unquote(value)
    except Exception:
        pass
    return ""


def classify_offline_url(url: str) -> OfflineLink | None:
    """判断单条链接是否为可处理的离线链接。"""
    raw = _remove_invisible(url or "")
    if not raw.strip():
        return None
    lower = raw.lower()
    if "ed2k://" in lower:
        normalized = _normalize_ed2k(raw)
        if normalized:
            return OfflineLink(
                url=normalized,
                url_type="ed2k",
                name=_guess_ed2k_name(normalized),
            )
    if "magnet:?" in lower:
        normalized = _normalize_magnet(raw)
        if normalized:
            return OfflineLink(
                url=normalized,
                url_type="magnet",
                name=_guess_magnet_name(normalized),
            )
    return None


def _collect_raw_candidates(urls: str | Sequence[str] | Iterable[str] | None) -> List[str]:
    if urls is None:
        return []
    candidates: List[str] = []

    def _from_text(text: str) -> None:
        text = _remove_invisible(text or "")
        if not text.strip():
            return
        found = False
        for match in _ED2K_RE.finditer(text):
            candidates.append(match.group(0))
            found = True
        for match in _MAGNET_RE.finditer(text):
            candidates.append(match.group(0))
            found = True
        if not found:
            for line in text.replace("\r", "\n").split("\n"):
                cleaned = line.strip()
                if cleaned:
                    candidates.append(cleaned)

    if isinstance(urls, str):
        _from_text(urls)
        return candidates

    for item in urls:
        if item is None:
            continue
        _from_text(str(item))
    return candidates


def parse_offline_links(urls: str | Sequence[str] | Iterable[str] | None) -> List[OfflineLink]:
    """解析输入为 OfflineLink 列表（去重，保序）。"""
    result: List[OfflineLink] = []
    seen: set[str] = set()
    for item in _collect_raw_candidates(urls):
        link = classify_offline_url(item)
        if not link:
            continue
        key = link.url.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(link)
    return result


def extract_offline_links_from_text(text: str) -> List[OfflineLink]:
    """从自由文本中提取 ed2k / magnet 链接。"""
    return parse_offline_links(text or "")


def describe_offline_link(link: OfflineLink) -> dict:
    """生成可安全打印的链接诊断信息。"""
    url = link.url or ""
    info: dict = {
        "url_type": link.url_type,
        "name": link.name or "",
        "length": len(url),
        "has_space": " " in url,
        "has_invisible": bool(_INVISIBLE_RE.search(url)),
    }
    if link.url_type == "ed2k":
        parts = url.split("|")
        file_hash = parts[4] if len(parts) >= 5 else ""
        size = parts[3] if len(parts) >= 4 else ""
        info.update(
            {
                "size": size,
                "hash_prefix": file_hash[:6],
                "hash_suffix": file_hash[-4:] if len(file_hash) >= 4 else file_hash,
                "hash_len": len(file_hash),
                "endswith_standard": url.endswith("|/"),
            }
        )
    elif link.url_type == "magnet":
        m = re.search(r"btih:([0-9a-zA-Z]+)", url, re.I)
        btih = m.group(1) if m else ""
        info.update(
            {
                "hash_prefix": btih[:6],
                "hash_suffix": btih[-4:] if len(btih) >= 4 else btih,
                "hash_len": len(btih),
            }
        )
    return info
