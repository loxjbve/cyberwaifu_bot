# Cyber Waifu Bot

一个基于 Telegram 的多角色 AI 聊天机器人，支持自定义角色、群组管理、关键词触发、加密货币行情分析等多种扩展功能，适合 RP 聊天、群聊娱乐与自动化管理。

---

## 目录结构

```
.
├── Dockerfile           # Docker 镜像构建配置
├── LICENSE              # 许可证
├── README.md            # 项目说明文档
├── bot_run.py           # 启动入口，注册命令与主循环
├── bot_core/            # 机器人核心模块
│   ├── callback.py      # 回调按钮与交互逻辑
│   ├── commands.py      # 命令处理与注册
│   ├── conversation.py  # 对话管理与存储
│   ├── decorators.py    # 装饰器与统一校验
│   ├── exceptions.py    # 自定义异常
│   ├── keyword.py       # 群组关键词管理
│   ├── msg.py           # 消息分发与回复
│   ├── public.py        # 公共方法与菜单
│   └── ...              # 其它核心功能
├── characters/          # 角色配置（支持自定义上传）
├── config/              # 主配置（Token、API、管理员等）
├── data/                # 数据存储（如 SQLite 数据库）
├── prompts/             # Prompt 预设集合
├── requirements.txt     # Python 依赖包列表
├── utils/               # 工具函数模块
│   ├── LLM_utils.py     # 大语言模型 API 封装
│   ├── db_utils.py      # 数据库操作
│   ├── file_utils.py    # 配置/角色/Prompt 加载
│   ├── market_utils.py  # 加密货币行情与分析
│   ├── prompt_utils.py  # Prompt 构建与 Token 计算
│   └── text_utils.py    # 文本处理
└── core_renew/          # 预留新架构/重构实验区
```

## 主要特性

- 支持 Telegram 群聊与私聊，命令丰富，体验友好
- 多角色体系，支持自定义角色上传与管理
- 群组关键词触发与自动回复，支持管理员权限校验
- 集成主流大语言模型（如 OpenAI、Gemini），支持流式/非流式回复
- 内置加密货币行情分析（集成 ccxt），币种自动识别
- 对话状态持久化，支持多会话管理与恢复
- 丰富的 Prompt 预设与自定义构建
- 完善的异常处理与日志记录，便于维护与排查
- 支持 Docker 一键部署，配置灵活

## 快速开始

### 依赖环境
- Python 3.9+
- pip
- Docker（可选，推荐生产环境部署）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置
1. 复制 `config/config.json`，填写 Telegram Bot Token、API Keys、管理员等信息。
2. 可根据需要自定义 `characters/` 角色和 `prompts/` 预设。

### 启动

```bash
python bot_run.py
```

或使用 Docker：

```bash
docker build -t cyber-waifu-bot .
docker run -d --name cyber-waifu-container -v "${PWD}/config:/app/config" -v "${PWD}/prompts:/app/prompts" -v "${PWD}/data:/app/data" -v "${PWD}/characters:/app/characters" cyber-waifu-bot
```

> Windows PowerShell 下 `${PWD}` 表示当前目录，CMD 用 `%CD%`

### 常用命令（Telegram 内）
- `/start` 打招呼
- `/me` 查看个人信息
- `/char` 选择/上传角色
- `/newchar` 创建私人角色
- `/api` 选择大模型 API
- `/preset` 选择 Prompt 预设
- `/kw` 群组关键词管理
- `/cremake` 群聊重开对话
- `/switch` 群聊切换角色
- `/status` 查看当前配置
- `/stream` 切换流式传输



## 未来规划
- Web 管理后台（用户、角色、数据统计等）
- 群管功能增强（禁言、欢迎、踢人等）
- 视频/图片多模态支持
- 国际化与多语言适配
- 更丰富的权限与额度管理

---

如有建议或需求，欢迎 issue 或 PR！
