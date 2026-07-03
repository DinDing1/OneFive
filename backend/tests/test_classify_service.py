"""分类服务测试

测试 onefive.services.classify_service 模块。

测试覆盖：
- _match_rule：单条规则匹配（条件内 OR、条件间 AND）
- classify_media：基于策略的分类主流程
- _normalize_to_list：值归一化工具
- get_genre_name / get_country_name：ID/代码 → 中文名称查找

依赖说明：
- _match_rule / _normalize_to_list / get_genre_name / get_country_name 是纯函数，直接调用
- classify_media 在 strategy=None 时会调用 get_config_service()，需用 fixture 隔离
"""
import pytest
from onefive.services.classify_service import (
    _match_rule,
    classify_media,
    _normalize_to_list,
    get_genre_name,
    get_country_name,
    DEFAULT_STRATEGY,
)


# ==================== _match_rule 测试 ====================

class TestMatchRule:
    """测试单条规则匹配函数 _match_rule

    匹配逻辑：条件内 OR（任一命中即满足），条件间 AND（全部满足才命中）
    """

    def test_空条件规则_总是匹配(self):
        # Arrange：空 conditions 表示无条件匹配
        details = {"genres": [], "origin_country": []}
        rule = {"category": "默认", "conditions": {}}
        # Act
        result = _match_rule(details, rule)
        # Assert：空条件总是返回 True（作为兜底规则）
        assert result is True

    def test_genreIds命中_返回True(self):
        # Arrange：媒体类型包含规则要求的类型 ID
        details = {"genres": [{"id": 16}]}
        rule = {"category": "动画", "conditions": {"genreIds": "16"}}
        # Act
        result = _match_rule(details, rule)
        # Assert：类型 ID 16 命中
        assert result is True

    def test_genreIds未命中_返回False(self):
        # Arrange：媒体类型不包含规则要求的类型 ID
        details = {"genres": [{"id": 18}]}
        rule = {"category": "动画", "conditions": {"genreIds": "16"}}
        # Act
        result = _match_rule(details, rule)
        # Assert：类型 ID 18 不匹配 16
        assert result is False

    def test_originCountry命中_返回True(self):
        # Arrange：媒体原产国在规则要求的国家列表中
        details = {"origin_country": ["CN"]}
        rule = {"category": "国产", "conditions": {"originCountry": "CN,TW,HK"}}
        # Act
        result = _match_rule(details, rule)
        # Assert：CN 在 CN,TW,HK 列表中
        assert result is True

    def test_originCountry未命中_返回False(self):
        # Arrange：媒体原产国不在规则要求的国家列表中
        details = {"origin_country": ["US"]}
        rule = {"category": "国产", "conditions": {"originCountry": "CN,TW,HK"}}
        # Act
        result = _match_rule(details, rule)
        # Assert：US 不在 CN,TW,HK 列表中
        assert result is False

    def test_多条件AND命中_返回True(self):
        # Arrange：两个条件都满足
        details = {"genres": [{"id": 16}], "origin_country": ["CN"]}
        rule = {"category": "国产动漫", "conditions": {"genreIds": "16", "originCountry": "CN,TW,HK"}}
        # Act
        result = _match_rule(details, rule)
        # Assert：genreIds 和 originCountry 都命中
        assert result is True

    def test_多条件AND未命中_返回False(self):
        # Arrange：genreIds 命中但 originCountry 未命中
        details = {"genres": [{"id": 16}], "origin_country": ["US"]}
        rule = {"category": "国产动漫", "conditions": {"genreIds": "16", "originCountry": "CN,TW,HK"}}
        # Act
        result = _match_rule(details, rule)
        # Assert：AND 逻辑下任一条件不满足即整体不命中
        assert result is False


# ==================== classify_media 测试 ====================

class TestClassifyMedia:
    """测试分类主函数 classify_media

    使用 patch_classify_config_service fixture 隔离数据库，
    mock 默认返回 None，使 classify_media 使用 DEFAULT_STRATEGY。
    """

    def test_默认策略_国产电影分类(self, patch_classify_config_service):
        # Arrange：剧情片，原产国中国
        details = {"genres": [{"id": 18}], "origin_country": ["CN"]}
        # Act
        result = classify_media(details, "movie")
        # Assert：匹配 originCountry=CN 规则 → 国产电影
        assert result == "电影/国产电影"

    def test_默认策略_动画电影分类(self, patch_classify_config_service):
        # Arrange：动画类型（genre 16），原产国美国
        details = {"genres": [{"id": 16}], "origin_country": ["US"]}
        # Act
        result = classify_media(details, "movie")
        # Assert：动画规则优先级最高 → 动画电影
        assert result == "电影/动画电影"

    def test_默认策略_无匹配回退到欧美电影(self, patch_classify_config_service):
        # Arrange：剧情片，原产国美国（不匹配国产/日韩/动画规则）
        details = {"genres": [{"id": 18}], "origin_country": ["US"]}
        # Act
        result = classify_media(details, "movie")
        # Assert：空条件规则兜底 → 欧美电影
        assert result == "电影/欧美电影"

    def test_自定义策略_优先级匹配(self):
        # Arrange：自定义策略，第一条规则空条件匹配
        custom_strategy = {
            "movie": [
                {"category": "自定义/全部", "conditions": {}},
                {"category": "电影/动画电影", "conditions": {"genreIds": "16"}},
            ]
        }
        details = {"genres": [{"id": 16}], "origin_country": ["US"]}
        # Act
        result = classify_media(details, "movie", strategy=custom_strategy)
        # Assert：第一条规则匹配后立即返回，不再检查后续规则
        assert result == "自定义/全部"


# ==================== _normalize_to_list 测试 ====================

class TestNormalizeToList:
    """测试值归一化函数 _normalize_to_list"""

    @pytest.mark.parametrize("value,expected", [
        (None, []),                       # None → 空列表
        ("CN,TW,HK", ["CN", "TW", "HK"]),  # 逗号分隔字符串
        (["CN", "TW"], ["CN", "TW"]),      # 列表原样返回
        ("CN", ["CN"]),                    # 单值字符串
    ])
    def test_各种输入_归一化为列表(self, value, expected):
        # Act & Assert：字符串拆分、列表保留、None 返回空
        assert _normalize_to_list(value) == expected


# ==================== get_genre_name / get_country_name 测试 ====================

class TestLookups:
    """测试类型和国家代码查找函数"""

    def test_get_genre_name_已知ID_返回中文名(self):
        # Act & Assert：16 → 动画
        assert get_genre_name(16) == "动画"

    def test_get_genre_name_未知ID_返回未知(self):
        # Act & Assert：不存在的 ID 返回"未知"
        assert get_genre_name(99999) == "未知"

    def test_get_country_name_已知代码_返回中文名(self):
        # Act & Assert：CN → 中国
        assert get_country_name("CN") == "中国"

    def test_get_country_name_未知代码_返回原值(self):
        # Act & Assert：未知代码原样返回
        assert get_country_name("xx") == "xx"
