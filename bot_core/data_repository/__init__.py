"""
bot_core/repository - 数据库访问层

这个模块提供了按数据表分类的Repository类，封装了所有数据库CRUD操作。
每个Repository类都提供了统一的字典格式返回结果，包含success、data、error字段。
"""

from .users_repository import UsersRepository
from .user_config_repository import UserConfigRepository
from .user_profiles_repository import UserProfilesRepository
from .conversations_repository import ConversationsRepository
from .groups_repository import GroupsRepository
from .sign_repository import SignRepository
from .gateways import ConversationGateway, DataAccessError, GroupGateway, UserGateway

__all__ = [
    'UsersRepository',
    'UserConfigRepository',
    'UserProfilesRepository',
    'ConversationsRepository',
    'GroupsRepository',
    'SignRepository',
    'ConversationGateway',
    'DataAccessError',
    'GroupGateway',
    'UserGateway',
]

# 创建便捷的访问方式
users = UsersRepository()
user_config = UserConfigRepository()
user_profiles = UserProfilesRepository()
conversations = ConversationsRepository()
groups = GroupsRepository()
sign = SignRepository()
