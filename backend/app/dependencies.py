"""FastAPI dependency injection providers.

Centralizes access to application singletons like AxleManager.
"""

from typing import Annotated

from fastapi import Depends

from app.services.axle_manager import AxleManager, get_axle_manager


def get_current_axle_manager() -> AxleManager:
    """FastAPI 依赖项：获取电驱桥系统管理器单例。

    依赖注入(Dependency Injection)使得控制器与底层通信解耦，
    方便后续编写单元测试或集成测试时替换为模拟对象。
    """
    return get_axle_manager()


AxleManagerDep = Annotated[AxleManager, Depends(get_current_axle_manager)]
