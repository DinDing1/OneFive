"""路径处理测试

测试 onefive.paths.split_accessible_paths 函数。

该函数解析飞牛授权路径列表，需兼容：
- Linux 冒号分隔（正式环境）
- Windows 盘符路径（本地测试，不能按冒号拆盘符）
- 换行分隔、分号分隔
- 去重、空白处理、空段过滤

注意：导入 onefive.paths 会触发模块级 DATA_DIR 目录创建，属正常行为。
"""
import pytest
from onefive.paths import split_accessible_paths


class TestSplitAccessiblePaths:
    """测试授权路径解析函数 split_accessible_paths"""

    def test_空字符串_返回空列表(self):
        # Act & Assert：空输入返回空列表
        assert split_accessible_paths("") == []

    def test_None输入_返回空列表(self):
        # Act & Assert：None 输入返回空列表（函数内部 `if not raw` 处理）
        assert split_accessible_paths(None) == []

    def test_Linux冒号分隔_拆分多个路径(self):
        # Arrange：飞牛正式环境格式
        raw = "/vol1/media:/vol2/downloads"
        # Act
        result = split_accessible_paths(raw)
        # Assert：按冒号拆分为两个路径
        assert result == ["/vol1/media", "/vol2/downloads"]

    def test_Windows单盘符路径_不拆分(self):
        # Arrange：Windows 盘符路径，盘符后的冒号不能作为分隔符
        raw = "D:\\OneFive\\strm-test"
        # Act
        result = split_accessible_paths(raw)
        # Assert：保持完整路径，不能拆成 "D" 和 "\\OneFive\\strm-test"
        assert result == ["D:\\OneFive\\strm-test"]

    def test_Windows分号分隔_拆分多个路径(self):
        # Arrange：Windows 多路径用分号分隔
        raw = "D:\\path1;D:\\path2"
        # Act
        result = split_accessible_paths(raw)
        # Assert：按分号拆分
        assert result == ["D:\\path1", "D:\\path2"]

    def test_换行分隔_拆分多个路径(self):
        # Arrange：每行一个路径（accessible_paths.env 格式）
        raw = "/path1\n/path2"
        # Act
        result = split_accessible_paths(raw)
        # Assert：按换行拆分
        assert result == ["/path1", "/path2"]

    def test_混合换行和冒号_全部拆分(self):
        # Arrange：换行 + 冒号混合
        raw = "/path1\n/path2:/path3"
        # Act
        result = split_accessible_paths(raw)
        # Assert：先按换行拆，再按冒号拆
        assert result == ["/path1", "/path2", "/path3"]

    def test_去重_保持顺序(self):
        # Arrange：重复路径
        raw = "/path1:/path1:/path2"
        # Act
        result = split_accessible_paths(raw)
        # Assert：去重后保持首次出现的顺序
        assert result == ["/path1", "/path2"]

    def test_空白处理_自动strip(self):
        # Arrange：路径前后有空格
        raw = "  /path1  :  /path2  "
        # Act
        result = split_accessible_paths(raw)
        # Assert：每段自动 strip 空白
        assert result == ["/path1", "/path2"]

    def test_空段过滤_忽略空路径(self):
        # Arrange：连续冒号产生空段
        raw = "/path1::/path2"
        # Act
        result = split_accessible_paths(raw)
        # Assert：空段被过滤
        assert result == ["/path1", "/path2"]
