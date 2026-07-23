"""
文件名质量评分模块

从 media-dashboard 的 duplicates.ts 移植：
- extract_video_info
- calculate_quality_score
- get_quality_level
- generate_video_tags

用于分享洗版：按路径/文件名中的质量标签加权打分。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class VideoInfo:
    resolution: Optional[str] = None
    video_codec: Optional[str] = None
    audio_codec: Optional[str] = None
    hdr_type: Optional[str] = None
    dolby_vision: bool = False
    atmos: bool = False
    source: Optional[str] = None
    bit_depth: Optional[int] = None
    fps: Optional[int] = None
    quality_tags: List[str] = field(default_factory=list)
    hfr: bool = False
    ultra_hd: bool = False
    release_group: Optional[str] = None


_RESOLUTION_PATTERNS = [
    (re.compile(r"7680x4320|4320p|\b8k\b", re.I), "4320p"),
    (re.compile(r"3840x2160|2160p|\b4k\b|ultra\s*hd|uhd", re.I), "2160p"),
    (re.compile(r"1920x1080p|1920x1080|1080p|\bhd1080p\b|bd1080p|1080i", re.I), "1080p"),
    (re.compile(r"1440p|2k", re.I), "1440p"),
    (re.compile(r"1280x720|1280\*720|720p|bd720p", re.I), "720p"),
    (re.compile(r"1024x576|960x540|1024x560|1024x550|1024x554|1024x544", re.I), "576p"),
    (re.compile(r"480p|480i|960x528", re.I), "480p"),
    (re.compile(r"360p", re.I), "360p"),
]

_VIDEO_CODEC_PATTERNS = [
    (re.compile(r"prores", re.I), "ProRes"),
    (re.compile(r"hevc|x265|h\.?265", re.I), "H.265"),
    (re.compile(r"x264|h\.?264|avc", re.I), "H.264"),
    (re.compile(r"av1", re.I), "AV1"),
    (re.compile(r"vp9", re.I), "VP9"),
    (re.compile(r"xvid", re.I), "XviD"),
    (re.compile(r"divx", re.I), "DivX"),
    (re.compile(r"mpeg-2|mpeg2", re.I), "MPEG-2"),
    (re.compile(r"mpeg-4", re.I), "MPEG-4"),
    (re.compile(r"vc-1|vc1", re.I), "VC-1"),
    (re.compile(r"vp8", re.I), "VP8"),
    (re.compile(r"avs", re.I), "AVS"),
    (re.compile(r"realvideo|rv\d+", re.I), "RealVideo"),
    (re.compile(r"thora|theora", re.I), "Theora"),
    (re.compile(r"dirac", re.I), "Dirac"),
]

_AUDIO_CODEC_PATTERNS = [
    (re.compile(r"alac", re.I), "ALAC"),
    (re.compile(r"opus", re.I), "OPUS"),
    (re.compile(r"wav", re.I), "WAV"),
    (re.compile(r"pcm(\s*stereo|\.2\.0|\s*2\.0|\s*stereo)?", re.I), "PCM"),
    (re.compile(r"truehd|true-hd", re.I), "TrueHD"),
    (re.compile(r"dts[\s\-_.]*hd[\s\-_.]*ma", re.I), "DTS-HD MA"),
    (re.compile(r"dts[\s\-_.]*hd|dtshd", re.I), "DTS-HD"),
    (re.compile(r"dts[\s\-_.]*x|dtsx", re.I), "DTS:X"),
    (re.compile(r"dts", re.I), "DTS"),
    (re.compile(r"\bdd\+\b|\bddp\b|eac3", re.I), "DD+"),
    (re.compile(r"ddp\.2\.0|ddp2\.0", re.I), "DD+"),
    (re.compile(r"ddp\.5\.1|ddp5\.1", re.I), "DD+"),
    (re.compile(r"\bdd(?!p)(?=[^a-z]|$)|\\bac3\\b", re.I), "DD"),
    (re.compile(r"\baac\b", re.I), "AAC"),
    (re.compile(r"\bflac\b", re.I), "FLAC"),
    (re.compile(r"\bmp3\b", re.I), "MP3"),
]

_HDR_PATTERNS = [
    (re.compile(r"hdr10\+|hdr10plus", re.I), "HDR10+"),
    (re.compile(r"hdr10", re.I), "HDR10"),
    (re.compile(r"hdr", re.I), "HDR"),
]

_SOURCE_PATTERNS = [
    (re.compile(r"bluray\.?remux|remux", re.I), "REMUX"),
    (re.compile(r"uhd\.?bluray|uhd\.?bd", re.I), "UHD BluRay"),
    (re.compile(r"blu[-\s]?ray|bluray|\bbd\b|blu-ray", re.I), "BluRay"),
    (re.compile(r"brrip", re.I), "BRRip"),
    (re.compile(r"hdrip", re.I), "HDRip"),
    (re.compile(r"hddvd", re.I), "HDDVD"),
    (re.compile(r"dvd\-?(5|9|10|14|18)|dvdrip|dvdscr|pdvd|\bdvd\b", re.I), "DVD"),
    (re.compile(r"web\.?dl|\bweb\b|webdl|amzn\.web\-?dl", re.I), "WEB-DL"),
    (re.compile(r"webrip", re.I), "WEBRip"),
    (re.compile(r"hr\-?hdtv|hdtvrip|tvrip|pdtv|\bhdtv\b", re.I), "HDTV"),
    (re.compile(r"\btv\b|dtv|pdtv", re.I), "TV"),
    (re.compile(r"vhsrip", re.I), "VHSRip"),
    (re.compile(r"vod", re.I), "VOD"),
    (re.compile(r"camrip|\bcam\b|camera", re.I), "CAM"),
    (re.compile(r"\bts\b|tc|hc", re.I), "TS/TC/HC"),
    (re.compile(r"\br5\b", re.I), "R5"),
    (re.compile(r"\bamzn\b", re.I), "AMZN"),
    (re.compile(r"\bnf\b", re.I), "NF"),
    (re.compile(r"\bp2p\b", re.I), "P2P"),
]

_RESOLUTION_SCORES: Dict[str, int] = {
    "4320p": 2000,
    "2160p": 2000,
    "1440p": 1700,
    "1080p": 1500,
    "720p": 1000,
    "576p": 650,
    "480p": 600,
    "360p": 300,
}

_VIDEO_CODEC_SCORES: Dict[str, int] = {
    "AV1": 500,
    "H.265": 400,
    "H.264": 300,
    "VP9": 250,
    "ProRes": 350,
    "VC-1": 220,
    "VP8": 200,
    "Dirac": 200,
    "MPEG-2": 180,
    "MPEG-4": 160,
    "AVS": 150,
    "XviD": 150,
    "Theora": 120,
    "DivX": 100,
    "RealVideo": 80,
}

_AUDIO_CODEC_SCORES: Dict[str, int] = {
    "TrueHD": 300,
    "DTS:X": 280,
    "DTS-HD MA": 260,
    "DTS-HD": 250,
    "DTS": 200,
    "DD+": 150,
    "DD": 120,
    "PCM": 120,
    "WAV": 110,
    "AAC": 100,
    "ALAC": 100,
    "FLAC": 90,
    "OPUS": 90,
    "MP3": 50,
}

_HDR_SCORES: Dict[str, int] = {
    "HDR10+": 200,
    "HDR10": 150,
    "HDR": 100,
}

_SOURCE_SCORES: Dict[str, int] = {
    "REMUX": 400,
    "UHD BluRay": 350,
    "BluRay": 300,
    "HDDVD": 280,
    "WEB-DL": 250,
    "AMZN": 240,
    "NF": 230,
    "VOD": 220,
    "WEBRip": 200,
    "P2P": 200,
    "BRRip": 180,
    "HDTV": 150,
    "TV": 120,
    "DVDRip": 100,
    "DVD": 80,
    "R5": 70,
    "TS/TC/HC": 50,
    "CAM": 20,
    "VHSRip": 10,
}

_QUALITY_TAG_SCORES: Dict[str, int] = {
    "REMUX": 200,
    "PROPER": 50,
    "REPACK": 30,
    "EXTENDED": 40,
    "IMAX": 100,
    "ULTRAHD": 70,
    "HFR": 60,
    "HQ": 40,
    "EDR": 120,
}


def extract_video_info(path: str) -> VideoInfo:
    """从路径/文件名解析画质相关信息。"""
    result = VideoInfo()
    if not path:
        return result

    lower_path = path.lower()

    for pattern, resolution in _RESOLUTION_PATTERNS:
        if pattern.search(lower_path):
            result.resolution = resolution
            break

    if re.search(r"\bultrahd\b|\buhd\b", lower_path):
        result.ultra_hd = True

    for pattern, codec in _VIDEO_CODEC_PATTERNS:
        if pattern.search(lower_path):
            result.video_codec = codec
            break

    audio_codecs: List[str] = []
    for pattern, codec in _AUDIO_CODEC_PATTERNS:
        if pattern.search(lower_path):
            audio_codecs.append(codec)
    if audio_codecs:
        filtered = []
        for c in audio_codecs:
            if c in ("DTS-HD MA", "DTS:X"):
                filtered.append(c)
            elif c == "DTS-HD" and (
                "DTS-HD MA" in audio_codecs or "DTS:X" in audio_codecs
            ):
                continue
            elif c == "DTS" and (
                "DTS-HD MA" in audio_codecs
                or "DTS:X" in audio_codecs
                or "DTS-HD" in audio_codecs
            ):
                continue
            else:
                filtered.append(c)
        unique: List[str] = []
        seen = set()
        for c in filtered:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        result.audio_codec = " | ".join(unique)

    for pattern, hdr_type in _HDR_PATTERNS:
        if pattern.search(lower_path):
            result.hdr_type = hdr_type
            break

    if re.search(r"\bdv\b|dolby\.?vision|dovi|doblyvison|dolby\.vision", lower_path):
        result.dolby_vision = True

    if re.search(r"atmos|atomos|dolby.?atmos", lower_path):
        result.atmos = True

    fps_match = re.search(r"(\d{2,3})\s*fps", lower_path)
    if fps_match:
        result.fps = int(fps_match.group(1))

    if re.search(r"\bhfr\b", lower_path):
        result.hfr = True

    for pattern, source in _SOURCE_PATTERNS:
        if pattern.search(lower_path):
            result.source = source
            break

    quality_tags: List[str] = []
    if re.search(r"remux", lower_path):
        quality_tags.append("REMUX")
    if re.search(r"proper", lower_path):
        quality_tags.append("PROPER")
    if re.search(r"repack", lower_path):
        quality_tags.append("REPACK")
    if re.search(r"extended|director.?cut", lower_path):
        quality_tags.append("EXTENDED")
    if re.search(r"imax", lower_path):
        quality_tags.append("IMAX")
    if re.search(r"\bhq\b", lower_path):
        quality_tags.append("HQ")
    if result.ultra_hd:
        quality_tags.append("ULTRAHD")
    if result.hfr:
        quality_tags.append("HFR")
    if re.search(r"\bedr\b|edr10", lower_path):
        quality_tags.append("EDR")
    result.quality_tags = quality_tags

    bit_depth_match = re.search(r"(\d+)\s*bit", lower_path)
    if bit_depth_match:
        result.bit_depth = int(bit_depth_match.group(1))

    result.release_group = _extract_release_group_from_path(path) or None

    return result


def _extract_release_group_from_path(path: str) -> str:
    """从路径/文件名解析发布组（复用整理模块的内置+自定义发布组）。"""
    if not path:
        return ""
    try:
        from .file_info_service import _extract_release_group
    except Exception:
        return ""

    parts = [p for p in re.split(r"[/\\]", path) if p]
    # 优先文件名，其次父目录名，再次整段路径文本
    candidates: List[str] = []
    if parts:
        candidates.append(parts[-1])
    if len(parts) >= 2:
        candidates.append(parts[-2])
    candidates.append(path)

    for raw in candidates:
        base = raw.rsplit(".", 1)[0] if ("." in raw and not raw.startswith(".")) else raw
        group = _extract_release_group(base)
        if group:
            return group
    return ""


def calculate_quality_score(path: str, size: int = 0) -> int:
    """根据文件名/路径与体积计算质量分。"""
    info = extract_video_info(path)
    score = 0

    if info.resolution:
        score += _RESOLUTION_SCORES.get(info.resolution, 0)

    if info.video_codec:
        score += _VIDEO_CODEC_SCORES.get(info.video_codec, 0)

    if info.audio_codec:
        best_audio = 0
        for token in info.audio_codec.split("|"):
            best_audio = max(best_audio, _AUDIO_CODEC_SCORES.get(token.strip(), 0))
        score += best_audio

    if info.hdr_type:
        score += _HDR_SCORES.get(info.hdr_type, 0)

    if info.dolby_vision:
        score += 250
    if info.atmos:
        score += 150

    if info.bit_depth:
        if info.bit_depth >= 12:
            score += 80
        elif info.bit_depth >= 10:
            score += 50

    if info.fps:
        if info.fps >= 50:
            score += 70
        elif info.fps >= 30:
            score += 15

    if info.source:
        score += _SOURCE_SCORES.get(info.source, 0)

    for tag in info.quality_tags:
        score += _QUALITY_TAG_SCORES.get(tag, 0)

    size_gb = size / (1024 * 1024 * 1024) if size else 0
    if size_gb > 0:
        ideal_size = 2.0
        if info.resolution in ("2160p", "4320p"):
            ideal_size = 25.0
        elif info.resolution == "1440p":
            ideal_size = 12.0
        elif info.resolution == "1080p":
            ideal_size = 8.0
        elif info.resolution == "720p":
            ideal_size = 4.0
        elif info.resolution == "576p":
            ideal_size = 2.5

        size_ratio = size_gb / ideal_size
        if 0.5 <= size_ratio <= 2.0:
            size_score = 200 - abs(size_ratio - 1.0) * 100
        else:
            size_score = max(0.0, 100 - abs(size_ratio - 1.0) * 50)
        score += round(size_score)

    return int(round(score))


def get_quality_level(score: int) -> str:
    if score >= 4000:
        return "优秀"
    if score >= 3000:
        return "良好"
    if score >= 2000:
        return "一般"
    return "较差"


def generate_video_tags(path: str) -> List[str]:
    """生成展示用标签列表（含发布组）。"""
    info = extract_video_info(path)
    tags: List[str] = []
    if info.resolution:
        tags.append(info.resolution)

    quality_section: List[str] = []
    if info.hdr_type:
        quality_section.append(info.hdr_type)
    if info.dolby_vision:
        quality_section.append("Dolby Vision")
    if info.atmos:
        quality_section.append("Dolby Atmos")
    if "REMUX" in info.quality_tags:
        quality_section.append("REMUX")
    if "IMAX" in info.quality_tags:
        quality_section.append("IMAX")
    if "ULTRAHD" in info.quality_tags:
        quality_section.append("UHD")
    if "HFR" in info.quality_tags:
        quality_section.append("HFR")
    if "HQ" in info.quality_tags:
        quality_section.append("HQ")
    if "EDR" in info.quality_tags:
        quality_section.append("EDR")
    if quality_section:
        tags.append(" / ".join(quality_section))

    if info.fps:
        tags.append(f"{info.fps}fps")
    if info.bit_depth:
        tags.append(f"{info.bit_depth}bit")
    if info.audio_codec:
        tags.append(info.audio_codec)
    if info.source and info.source != "REMUX":
        tags.append(info.source)
    if info.video_codec:
        tags.append(info.video_codec)
    if info.release_group:
        tags.append(info.release_group)

    return tags


def extract_release_group(path: str) -> str:
    """对外暴露：从路径提取发布组。"""
    return _extract_release_group_from_path(path)
