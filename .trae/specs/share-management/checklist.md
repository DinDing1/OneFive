# Checklist

## 数据库
- [x] share_source 表正确创建（id 自增主键，share_code UNIQUE）
- [x] share_file 表正确创建（source_id 关联 share_source.id，source_id+file_id UNIQUE）
- [x] 索引正确创建（source、parent、name、category）

## 后端服务
- [x] share_service 能正确解析 115 分享链接（提取 share_code、receive_code）
- [x] share_service 能调用 p115client share_iterdir 获取文件列表
- [x] share_service 能将文件信息写入 share_file 表（通过 source_id 关联）
- [x] share_service 的 list_files 按 source_id + parent_id 查询
- [x] share_service 的 delete_share 按 source_id 删除（级联删除 share_file）
- [x] share_organize_service 能复用 classify_service 对分享文件进行分类
- [x] share_organize_service 能复用 file_info_service 提取技术信息
- [x] share_organize_service 不执行实际的移动/复制操作
- [x] share_organize_service 整理后正确更新 organized 标志
- [x] 所有 API 接口返回 ApiResponse 格式
- [x] API 删除接口使用 source_id（不用 share_code）

## 前端页面
- [x] /share 路由正常工作
- [x] 侧边栏"分享管理"菜单项显示正确（在文件管理下方）
- [x] 分享链接输入框能正确解析 URL
- [x] 文件列表支持目录层级展开（按 source_id + parent_id）
- [x] 原始视图 / 整理视图切换正常
- [x] 整理视图按分类目录展示（电影/电视剧等）
- [x] 整理视图中未整理文件显示在"未分类"分组
- [x] 面包屑导航正确显示路径
- [x] 搜索功能正常
- [x] 识别/批量识别功能正常
- [x] 删除分享功能正常（含确认弹窗，按 source_id 删除）
- [x] 样式与 Files.vue 风格一致（glass-card、token 化颜色）
- [x] 零硬编码颜色

## Bot 集成
- [x] Bot 能检测消息中的 115 分享链接（115.com/s/ 和 115cdn.com/s/）
- [x] Bot 能正确提取 share_code 和 receive_code
- [x] Bot 调用 share_service.add_share() 成功处理
- [x] Bot 回复格式正确（分享名称、文件数量、总大小、source_id）
- [x] Bot 失败时回复错误信息

## 集成
- [x] 后端启动无报错
- [x] 前端构建无报错（vue-tsc + vite build）
