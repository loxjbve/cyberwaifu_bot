# 使用官方 Python 基础镜像，slim 版本更轻量
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 复制项目文件到容器中，包括所有文件和文件夹
COPY . /app

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 暴露端口（如果您的 Bot 使用 webhook 模式，需要暴露 Telegram webhook 端口，例如 8443）
# EXPOSE 8443  # 如果不需要，可以注释掉

# 指定容器启动时运行的命令（假设 bot.py 是主入口）
CMD ["python", "bot_run.py"]
