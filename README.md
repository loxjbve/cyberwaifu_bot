# Cyber Waifu Bot

这是一个基于 Telegram 的 AI 聊天机器人项目（RP特化、内置炒币蛆角色可获取实时加密市场数据）。

## 项目结构与模块功能说明

```
.
├── Dockerfile             # Docker 镜像构建配置
├── bot.log                # 运行日志文件
├── bot_core               # 机器人核心模块
│   ├── __init__.py        # 包初始化
│   ├── callback.py        # 处理 Telegram 回调按钮与交互
│   ├── conversation.py    # 私聊与群聊对话管理、对话存储与恢复
│   ├── decorators.py      # 命令装饰器，统一异常处理与用户校验
│   ├── exceptions.py      # 自定义异常类型
│   ├── group.py           # 群组管理、管理员校验、群聊触发逻辑
│   ├── keyword.py         # 群组关键词管理与触发、关键词增删查
│   ├── msg.py             # 消息处理主逻辑，群聊/私聊消息分发与回复
│   ├── public.py          # 公共方法，如角色/API/预设列表展示
│   ├── tg.py              # Telegram 相关工具函数，用户与消息解析
│   └── user.py            # 用户信息与配置管理
├── bot_run.py             # 机器人启动入口，命令注册与主循环
├── characters             # 角色配置目录
│   └── cuicuishark.json   # 示例角色，支持加密货币分析
├── config                 # 配置文件目录
│   └── config.json        # 主配置文件（Token、API 列表等）
├── data                   # 数据存储目录
│   └── data.db            # SQLite 数据库，存储用户、对话等信息
├── prompts                # Prompt 配置目录
│   └── prompts.json       # 预设 Prompt 集合
├── requirements.txt       # Python 依赖包列表
└── utils                  # 工具函数模块
    ├── LLM_utils.py       # 大语言模型 API 封装与消息生成、Token 统计
    ├── db_utils.py        # 数据库操作封装，用户/对话/群组等表的增删查改
    ├── file_utils.py      # 配置、角色、Prompt 文件加载与管理
    ├── market_utils.py    # 加密货币行情获取与分析（集成 ccxt）
    ├── prompt_utils.py    # Prompt 构建、插入与 Token 计算
    └── text_utils.py      # 文本处理与标签内容提取
```

### 主要模块功能简介

- **bot_core/**
  - `callback.py`：处理 Telegram 回调按钮（如角色/预设/API 切换、对话加载/删除等）。
  - `conversation.py`：管理私聊和群聊的对话生命周期，包括新建、保存、恢复、总结等。
  - `decorators.py`：为命令处理函数统一加上异常捕获、消息过期校验、用户信息更新等。
  - `exceptions.py`：定义机器人运行时的自定义异常，便于统一处理。
  - `group.py`：群组相关逻辑，包括管理员校验、消息触发条件、群聊对话记录等。
  - `keyword.py`：群组关键词的增删查、触发机制及交互按钮。
  - `msg.py`：消息主处理逻辑，分发群聊/私聊消息，调用 LLM 生成回复。
  - `public.py`：公共交互方法，如角色/API/预设/对话列表的 InlineKeyboard 展示。
  - `tg.py`：Telegram 消息与用户解析、私聊/群聊判定、过期校验等。
  - `user.py`：用户信息与配置的获取、更新、创建。
- **utils/**
  - `LLM_utils.py`：封装大语言模型 API（如 OpenAI），支持流式与非流式回复、Token 统计、对话总结。
  - `db_utils.py`：SQLite 数据库操作，涵盖用户、对话、群组、关键词等表的增删查改。
  - `file_utils.py`：加载配置、角色、Prompt 文件，支持角色与 Prompt 动态扩展。
  - `market_utils.py`：集成 ccxt 获取主流加密货币行情，支持币种关键词自动识别与行情分析。
  - `prompt_utils.py`：Prompt 构建、插入用户输入、Token 计算等。
  - `text_utils.py`：正则提取标签内容等文本处理工具。

## 主要功能

*   基于 Telegram 平台的交互式聊天。
*   集成大语言模型（LLM）提供智能回复。
*   支持关键词触发特定逻辑。
*   管理对话状态和用户信息。
*   支持群组聊天。
*   'cuicuishark'角色包含加密货币分析的功能。

## 如何运行 (使用 Docker)

1.  **确保已安装 Docker:** 如果没有，请先安装 Docker。
2.  **构建 Docker 镜像:** 在项目根目录 (`d:\cyber_waifu`) 打开终端或 PowerShell，运行以下命令：
    ```bash
    docker build -t cyber-waifu-bot .
    ```
3.  **运行 Docker 容器:**
    *   **首次运行或需要修改配置:**
        你需要将本地的 `config`  `data` `prompts` `characters` 目录挂载到容器中，以便持久化配置和数据。请先根据需要修改 `config/config.json` 文件。
        ```bash
        docker run -d --name cyber-waifu-container -v "${PWD}/config:/app/config" -v "${PWD}/prompts:/app/prompts" -v "${PWD}/data:/app/data" cyber-waifu-bot
        ```
        *(注意: `${PWD}` 在 PowerShell 中表示当前目录。如果使用 CMD，请替换为 `%CD%`)*
    *   **查看日志:**
        ```bash
        docker logs -f cyber-waifu-container
        ```
    *   **停止容器:**
        ```bash
        docker stop cyber-waifu-container
        ```
    *   **移除容器:**
        ```bash
        docker rm cyber-waifu-container
        ```

## 配置

主要的配置信息位于 `config/config.json` 文件中。请根据实际情况修改此文件，例如 Telegram Bot Token、API Keys 等。

角色和 Prompt 配置分别位于 `characters/` 和 `prompts/` 目录下的 JSON 文件中。

## ToDoList

以下是未来计划添加或改进的功能：

*   **群组管理:**
    *   添加更丰富的群管功能（如禁言、踢人、入群欢迎、自定义回复规则等）。
    *   优化群组关键词和触发逻辑。
*   **Web 端管理:**
    *   开发 Web 管理界面，方便管理用户、配置、查看统计数据等。
*   **用户自定义:**
    *   ~支持用户上传自定义的角色配置文件。~(Done 25/5/6)
*   **功能增强:**
    *   实现用户额度和余额的实际处理逻辑。
    *   添加更多的市场数据 (`market_utils`)。
    *   _增加视频链接解析转发功能_
*   **健壮性与可维护性:**
    *   完善错误处理机制和日志记录。
    *   优化硬编码参数。
    *   增加单元测试和集成测试。
    *   优化数据库查询性能。
*   **其他:**
    *   考虑添加国际化/多语言支持。
    *   实现更精细化的权限控制。
