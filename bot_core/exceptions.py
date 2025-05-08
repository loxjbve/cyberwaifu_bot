class BotError(Exception):
    """自定义Bot异常基类"""
    pass

class DatabaseError(BotError):
    """数据库操作相关异常"""
    pass

class LLMError(BotError):
    """自定义LLM服务调用异常"""
    pass

class BotRunError(Exception):
    """自定义Bot运行异常基类"""
    pass