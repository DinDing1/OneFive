"""重命名服务测试

测试 onefive.services.rename_service 模块。

测试覆盖：
- render_template：模板渲染（变量替换、条件渲染、非法字符清理）
- generate_movie_path：电影目标路径生成
- generate_tv_path：电视剧目标路径生成

依赖说明：
- render_template 是纯函数，直接调用
- generate_movie_path / generate_tv_path 在函数内部调用 get_config_service()，
  需用 patch_rename_config_service fixture 隔离数据库
"""
import pytest
from onefive.services.rename_service import (
    render_template,
    generate_movie_path,
    generate_tv_path,
)


# ==================== render_template 测试 ====================

class TestRenderTemplate:
    """测试模板渲染函数 render_template"""

    def test_变量替换_基本场景(self):
        # Arrange：模板含两个变量
        template = "{{title}}.{{year}}"
        variables = {"title": "电影", "year": "2023"}
        # Act
        result = render_template(template, variables)
        # Assert：变量被替换为对应值
        assert result == "电影.2023"

    def test_条件渲染_if为真_渲染内容(self):
        # Arrange：webSource 有值时渲染（前缀 Prefix 避免前导点号被清理规则移除）
        template = "Prefix{% if webSource %}.{{webSource}}{% endif %}"
        variables = {"webSource": "Netflix"}
        # Act
        result = render_template(template, variables)
        # Assert：条件为真，渲染 ".Netflix"（前缀保留）
        assert result == "Prefix.Netflix"

    def test_条件渲染_if为假_不渲染(self):
        # Arrange：webSource 为空时不渲染（前缀 Prefix 避免前导点号被清理规则移除）
        template = "Prefix{% if webSource %}.{{webSource}}{% endif %}"
        variables = {"webSource": ""}
        # Act
        result = render_template(template, variables)
        # Assert：条件为假，只保留前缀
        assert result == "Prefix"

    def test_条件分支_if为真_渲染if分支(self):
        # Arrange：x 有值时渲染 A
        template = "{% if x %}A{% else %}B{% endif %}"
        variables = {"x": "yes"}
        # Act
        result = render_template(template, variables)
        # Assert：if 分支命中
        assert result == "A"

    def test_条件分支_if为假_渲染else分支(self):
        # Arrange：x 无值时渲染 B
        template = "{% if x %}A{% else %}B{% endif %}"
        variables = {}
        # Act
        result = render_template(template, variables)
        # Assert：else 分支命中
        assert result == "B"

    def test_变量缺失_替换为空字符串(self):
        # Arrange：模板引用了 variables 中不存在的变量
        template = "{{title}}"
        variables = {}
        # Act
        result = render_template(template, variables)
        # Assert：缺失变量替换为空，不报错
        assert result == ""

    def test_清理非法字符_删除特殊符号(self):
        # Arrange：模板含 Windows 非法字符 : | *
        template = "a:b|c*d"
        variables = {}
        # Act
        result = render_template(template, variables)
        # Assert：: | * 被删除，保留正常字符
        assert result == "abcd"

    def test_清理多余点号_合并连续点号(self):
        # Arrange：模板含连续两个点号
        template = "a..b"
        variables = {}
        # Act
        result = render_template(template, variables)
        # Assert：连续点号合并为一个
        assert result == "a.b"


# ==================== generate_movie_path 测试 ====================

class TestGenerateMoviePath:
    """测试电影路径生成函数 generate_movie_path

    使用 patch_rename_config_service fixture，mock 默认返回 None，
    使函数使用 DEFAULT_MOVIE_TEMPLATE。
    """

    def test_生成电影路径_包含目录和文件名(self, patch_rename_config_service):
        # Arrange：电影基础信息 + 技术信息
        tech_info = {
            "videoFormat": "1080p",
            "videoCodec": "x264",
            "audioCodec": "AAC",
            "fileExt": ".mkv",
        }
        # Act
        result = generate_movie_path("电影", "2023", "123", tech_info)
        # Assert：返回值结构正确，包含 dir 和 filename 两个键
        assert "dir" in result
        assert "filename" in result

    def test_生成电影路径_目录包含标题和年份(self, patch_rename_config_service):
        # Arrange
        tech_info = {
            "videoFormat": "1080p",
            "videoCodec": "x264",
            "audioCodec": "AAC",
            "fileExt": ".mkv",
        }
        # Act
        result = generate_movie_path("电影", "2023", "123", tech_info)
        # Assert：目录格式为 "标题 (年份) {tmdb=ID}"
        assert "电影" in result["dir"]
        assert "2023" in result["dir"]

    def test_生成电影路径_文件名包含扩展名(self, patch_rename_config_service):
        # Arrange
        tech_info = {
            "videoFormat": "1080p",
            "videoCodec": "x264",
            "audioCodec": "AAC",
            "fileExt": ".mkv",
        }
        # Act
        result = generate_movie_path("电影", "2023", "123", tech_info)
        # Assert：文件名以 .mkv 结尾
        assert result["filename"].endswith(".mkv")


# ==================== generate_tv_path 测试 ====================

class TestGenerateTvPath:
    """测试电视剧路径生成函数 generate_tv_path"""

    def test_生成电视剧路径_文件名包含SxxExx(self, patch_rename_config_service):
        # Arrange：电视剧基础信息 + 技术信息 + 季集信息
        tech_info = {
            "videoFormat": "1080p",
            "videoCodec": "x264",
            "audioCodec": "AAC",
            "fileExt": ".mkv",
        }
        # Act
        result = generate_tv_path(
            title="剧集", year="2023", tmdb_id="456",
            tech_info=tech_info, season="1", episode="1",
            season_year="2023",
        )
        # Assert：文件名应包含 "S01E01" 季集标记
        assert "S01E01" in result["filename"]
