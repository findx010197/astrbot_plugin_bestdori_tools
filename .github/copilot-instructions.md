# AstrBot Bestdori Tools Copilot Instructions

## 项目架构与核心模块
- 插件主入口为 `main.py`，负责注册命令和初始化服务。
- `client.py` 封装了 Bestdori API 的访问，所有数据获取均通过此模块。
- `models.py` 定义了核心数据结构（如 Event、Card、Gacha），数据流动以模型为中心。
- `birthday_service.py` 处理角色生日相关逻辑，包括数据读取和卡片渲染。
- `render_service.py` 负责 HTML 渲染和长图生成，调用 Jinja2 模板和 html2image。
- `consts.py` 存放常量和角色映射（如 CHARACTER_MAP），是昵称与ID转换的关键。
- 所有 HTML 模板位于 `templates/` 目录，渲染服务会自动加载。

## 关键开发流程
- 依赖安装：`pip install -r requirements.txt`，需在 AstrBot 虚拟环境下执行。
- 插件安装后需重启 AstrBot。
- 数据文件（如 cards.json、events.json）位于 `data/`，部分缓存和资源在 `data/bestdori_cache/` 和 `data/birthdays/`。
- 图片渲染依赖 ffmpeg，Windows 下可用 `install_ffmpeg.ps1` 自动安装。

## 项目约定与模式
- 所有 API 数据访问统一通过 `client.py`，禁止直接请求外部 API。
- 角色昵称与ID映射请参考 `consts.py` 的 CHARACTER_MAP。
- 渲染服务只接受模型对象作为输入，避免直接传递原始 dict。
- 生日卡片和活动长图均通过 Jinja2 模板渲染，模板文件需保持与服务接口一致。
- 异步操作优先使用 `aiohttp`，图片处理统一用 Pillow。

## 典型用例与命令
- 查询活动：`/bd event [ID|current]`
- 查询生日：`/bd event 0 [角色昵称|完整名]`
- 生成长图：调用 `render_service.py` 的渲染接口，传入模型对象和模板名。

## 重要文件/目录参考
- `main.py`：插件入口与命令注册
- `client.py`：API 数据获取
- `models.py`：核心数据结构
- `birthday_service.py`：生日逻辑
- `render_service.py`：渲染与图片生成
- `templates/`：所有 HTML 模板
- `data/`：原始与缓存数据
- `consts.py`：常量与映射

## 其他说明
- 插件仅支持在 AstrBot 环境下运行。
- 依赖 html2image、Jinja2、Pillow、aiohttp，需确保全部安装。
- 若需扩展命令或服务，建议参考现有模块结构与数据流。

---
如有不清楚或遗漏的部分，请反馈以便补充完善。