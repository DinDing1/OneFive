"""文件名解析服务测试

测试 onefive.services.file_info_service 模块的所有解析函数。

这是最核心的纯函数模块，不依赖数据库和外部 API，直接调用即可。
测试覆盖：
- extract_key_info：主解析函数（标准格式 + guessit 回退）
- has_season_episode_marker：季集标记检测
- format_size：文件大小格式化
- _extract_tmdb_id：TMDB ID 提取
- _extract_video_format：分辨率提取
- _extract_effects：特效信息提取
- _extract_web_source：WEB 来源提取
- _extract_edition：版本信息提取
- _detect_chinese_episode：中文集数检测
"""
import pytest
from onefive.services.file_info_service import (
    extract_key_info,
    has_season_episode_marker,
    format_size,
    _extract_tmdb_id,
    _extract_video_format,
    _extract_effects,
    _extract_web_source,
    _extract_edition,
    _detect_chinese_episode,
)


# ==================== extract_key_info 测试 ====================

class TestExtractKeyInfo:
    """测试主解析函数 extract_key_info"""

    def test_标准格式电影_提取标题年份和TMDB_ID(self):
        # Arrange：标准命名格式 "标题 (年份) {tmdb=ID}.扩展名"
        filename = "电影名 (2023) {tmdb=12345}.mkv"
        # Act
        result = extract_key_info(filename)
        # Assert：标准格式直接走正则提取，不走 guessit
        assert result["title"] == "电影名"
        assert result["year"] == "2023"
        assert result["tmdbId"] == 12345
        assert result["mediaType"] == "movie"
        assert result["season"] is None
        assert result["episode"] is None

    def test_标准格式电视剧_无季集标记判定为电影(self):
        # Arrange：标准格式但无 SxxExx / 第N集 标记
        filename = "剧集名 (2023) {tmdb=67890}.mkv"
        # Act
        result = extract_key_info(filename)
        # Assert：无季集标记时 mediaType 为 movie
        assert result["mediaType"] == "movie"
        assert result["tmdbId"] == 67890

    def test_S01E01格式_提取季集信息(self):
        # Arrange：guessit 能识别的 S01E01 格式
        filename = "Show.Name.S01E01.1080p.mkv"
        # Act
        result = extract_key_info(filename)
        # Assert：非标准格式走 guessit，只断言关键字段
        assert result["season"] == 1
        assert result["episode"] == 1
        assert result["mediaType"] == "tv"

    def test_中文第N集格式_提取集数(self):
        # Arrange：guessit 不支持中文集数，由自定义正则补充
        filename = "某剧.第5集.mkv"
        # Act
        result = extract_key_info(filename)
        # Assert：中文"第N集"格式 season 固定为 1
        assert result["season"] == 1
        assert result["episode"] == 5
        assert result["mediaType"] == "tv"

    def test_Season1格式_提取季数(self):
        # Arrange：Season N 格式（仅季无集）
        filename = "Show.Name.Season.1.1080p.mkv"
        # Act
        result = extract_key_info(filename)
        # Assert：season 提取成功，无集号
        assert result["season"] == 1
        assert result["mediaType"] == "tv"

    def test_无季集标记的电影_判定为movie(self):
        # Arrange：普通电影文件名，无季集标记
        filename = "Movie.Title.2023.1080p.mkv"
        # Act
        result = extract_key_info(filename)
        # Assert：无季集标记，mediaType 为 movie
        assert result["mediaType"] == "movie"
        assert result["season"] is None
        assert result["episode"] is None

    def test_花括号格式TMDB_ID提取(self):
        # Arrange：标准格式带 TMDB ID
        filename = "Title (2023) {tmdb=999}.mkv"
        # Act
        result = extract_key_info(filename)
        # Assert：TMDB ID 从花括号中提取
        assert result["tmdbId"] == 999


# ==================== has_season_episode_marker 测试 ====================

class TestHasSeasonEpisodeMarker:
    """测试季集标记检测函数 has_season_episode_marker"""

    @pytest.mark.parametrize("name", [
        "Show.S01E01.mkv",       # S01E01 格式
        "Show.第5集.mkv",         # 中文第N集
        "Show.EP01.mkv",         # EP01 格式
        "Show.E01.mkv",          # E01 格式
        "Show Season 1.mkv",     # Season 1 格式（实现要求 Season 与数字间为空白）
    ])
    def test_包含季集标记_返回True(self, name):
        # Act & Assert：上述格式应识别为电视剧
        assert has_season_episode_marker(name) is True

    @pytest.mark.parametrize("name", [
        "MOVIE01.mkv",            # 前导边界保护，不误判 E01
        "SAMPLE01.mkv",           # 同上
        "FILE01.mkv",             # 同上
        "Movie.Title.2023.mkv",   # 纯电影文件名
    ])
    def test_不包含季集标记_返回False(self, name):
        # Act & Assert：上述格式不应被误判为电视剧
        assert has_season_episode_marker(name) is False


# ==================== format_size 测试 ====================

class TestFormatSize:
    """测试文件大小格式化函数 format_size"""

    @pytest.mark.parametrize("size,expected", [
        (0, ""),                    # 零字节返回空字符串
        (-1, ""),                   # 负数返回空字符串
        (None, ""),                 # None 返回空字符串
        (500, "500 B"),             # 不足 1KB，显示 B（无小数）
        (1024, "1.0 KB"),           # 恰好 1KB
        (1048576, "1.0 MB"),        # 恰好 1MB
        (1073741824, "1.0 GB"),     # 恰好 1GB
        (1099511627776, "1.0 TB"),  # 恰好 1TB
    ])
    def test_各种大小_格式化正确(self, size, expected):
        # Act & Assert：边界值和常规值都应正确格式化
        assert format_size(size) == expected


# ==================== _extract_tmdb_id 测试 ====================

class TestExtractTmdbId:
    """测试 TMDB ID 提取函数 _extract_tmdb_id"""

    @pytest.mark.parametrize("text,expected", [
        ("{tmdb=12345}", 12345),     # 花括号 + 等号
        ("[tmdb=12345]", 12345),     # 方括号 + 等号
        ("{tmdb-12345}", 12345),     # 花括号 + 短横线
        ("tmdb=12345", 12345),       # 无括号
        ("tmdbid=12345", 12345),     # tmdbid 变体
        ("no tmdb here", None),      # 无 TMDB 标记
    ])
    def test_各种格式_提取TMDB_ID(self, text, expected):
        # Act & Assert：支持花括号、方括号、等号、短横线等多种格式
        assert _extract_tmdb_id(text) == expected


# ==================== _extract_video_format 测试 ====================

class TestExtractVideoFormat:
    """测试分辨率提取函数 _extract_video_format"""

    @pytest.mark.parametrize("base,expected", [
        ("Title.4320p", "4320p"),    # 8K
        ("Title.2160p", "2160p"),    # 4K 标准
        ("Title.4k", "2160p"),       # 4k 简写映射为 2160p
        ("Title.1080p", "1080p"),    # 全高清
        ("Title.720p", "720p"),      # 高清
        ("Title.noformat", ""),      # 无分辨率标记
    ])
    def test_各种分辨率_提取正确(self, base, expected):
        # Act & Assert：支持像素值和简写（4k → 2160p）
        assert _extract_video_format(base) == expected


# ==================== _extract_effects 测试 ====================

class TestExtractEffects:
    """测试特效信息提取函数 _extract_effects"""

    @pytest.mark.parametrize("base,expected", [
        ("Title.DV", "DV"),                       # 杜比视界
        ("Title.HDR10", "HDR10"),                 # HDR10
        ("Title.HDR10+", "HDR10+"),               # HDR10+ 增强版
        ("Title.HDR", "HDR"),                     # 普通 HDR
        ("Title.HLG", "HLG"),                     # HLG
        ("Title.10bit", "10bit"),                 # 色深
        ("Title.24fps", "24fps"),                 # 帧率
        ("Title.DV.HDR10.10bit", "DV HDR10 10bit"),  # 多特效组合
        ("Title.noeffects", ""),                  # 无特效
    ])
    def test_各种特效_提取正确(self, base, expected):
        # Act & Assert：单个特效和多特效组合都应正确提取
        assert _extract_effects(base) == expected


# ==================== _extract_web_source 测试 ====================

class TestExtractWebSource:
    """测试 WEB 来源提取函数 _extract_web_source"""

    @pytest.mark.parametrize("base,expected", [
        ("Title.NF", "Netflix"),       # Netflix 简写
        ("Title.AMZN", "Amazon"),      # Amazon 简写
        ("Title.DSNP", "Disney+"),     # Disney+ 简写
        ("Title.HBO", "HBO"),          # HBO
        ("Title.BILIBILI", "BiliBili"),  # 哔哩哔哩
        ("Title.nosource", ""),         # 无来源标记
    ])
    def test_各种WEB来源_提取正确(self, base, expected):
        # Act & Assert：平台简写应映射为完整名称
        assert _extract_web_source(base) == expected


# ==================== _extract_edition 测试 ====================

class TestExtractEdition:
    """测试版本信息提取函数 _extract_edition"""

    @pytest.mark.parametrize("base,expected", [
        ("Title.DC", "DC"),               # 导演剪辑版
        ("Title.Extended", "Extended"),   # 加长版
        ("Title.IMAX", "IMAX"),           # IMAX
        ("Title.3D", "3D"),               # 3D 版本
        ("Title.PROPER", "PROPER"),       # PROPER 修正版
        ("Title.Remastered", "Remastered"),  # 重制版
        ("Title.noedition", ""),          # 无版本标记
    ])
    def test_各种版本_提取正确(self, base, expected):
        # Act & Assert：各版本标记应正确识别
        assert _extract_edition(base) == expected


# ==================== _detect_chinese_episode 测试 ====================

class TestDetectChineseEpisode:
    """测试中文集数检测函数 _detect_chinese_episode"""

    @pytest.mark.parametrize("filename,expected", [
        ("某剧.第5集", (1, 5)),       # 单数集
        ("某剧.第100集", (1, 100)),   # 三位数集
        ("No episode here", (None, None)),  # 无中文集数
    ])
    def test_中文集数_提取正确(self, filename, expected):
        # Act & Assert：命中"第N集"时 season=1，episode=N
        assert _detect_chinese_episode(filename) == expected
