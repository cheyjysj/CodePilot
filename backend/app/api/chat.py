"""
聊天 API 路由
处理聊天请求和 WebSocket 连接
"""

import time
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from app.core.context_manager import ContextManager
from app.core.memory_manager import MemoryManager
from app.core.llm_client import LLMClient, LLMClientError
from app.tools.tool_registry import ToolRegistry


logger = logging.getLogger(__name__)
router = APIRouter()

# 初始化管理器
context_manager = ContextManager()
memory_manager = MemoryManager()
tool_registry = ToolRegistry()

# 初始化 LLM 客户端
try:
    llm_client = LLMClient()
    logger.info("LLM 客户端初始化成功 (model=%s)", llm_client.model)
except LLMClientError as e:
    logger.error("LLM 客户端初始化失败: %s", e)
    llm_client = None


class ChatMessage(BaseModel):
    """聊天消息"""
    role: str
    content: str
    timestamp: Optional[float] = None


class ChatRequest(BaseModel):
    """聊天请求"""
    messages: List[ChatMessage]
    stream: bool = False
    project_path: Optional[str] = None


@router.post("/send")
async def send_message(request: ChatRequest) -> Dict[str, Any]:
    """
    发送消息
    
    Args:
        request: 聊天请求
        
    Returns:
        响应字典
    """
    try:
        # 转换消息格式
        messages = [msg.model_dump() for msg in request.messages]

        # 应用上下文压缩（异步 LLM 版本）
        messages = await context_manager.process_messages_async(messages)

        # 调用 LLM
        response = await call_llm(messages)

        # 添加到记忆（异步 LLM 压缩版本）
        await memory_manager.session_memory.compact_async()
        memory_manager.add_to_session(
            content=f"User: {request.messages[-1].content}\nAssistant: {response}",
            metadata={'type': 'chat', 'timestamp': time.time()}
        )
        
        return {
            'success': True,
            'message': {
                'role': 'assistant',
                'content': response,
                'timestamp': time.time()
            }
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 端点
    
    Args:
        websocket: WebSocket 连接
    """
    await websocket.accept()
    
    try:
        while True:
            # 接收消息
            data = await websocket.receive_json()
            
            # 处理消息
            messages = data.get('messages', [])
            
            # 应用上下文压缩（异步 LLM 版本）
            messages = await context_manager.process_messages_async(messages)

            # 调用 LLM
            response = await call_llm(messages)

            # 添加到记忆（异步 LLM 压缩版本）
            await memory_manager.session_memory.compact_async()
            user_msgs = [m.get('content', '') for m in messages if m.get('role') == 'user']
            user_content = user_msgs[-1] if user_msgs else ''
            memory_manager.add_to_session(
                content=f"User: {user_content}\nAssistant: {response}",
                metadata={'type': 'chat', 'timestamp': time.time()}
            )

            # 发送响应
            await websocket.send_json({
                'role': 'assistant',
                'content': response,
                'timestamp': time.time()
            })
    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        await websocket.send_json({
            'error': str(e)
        })


async def call_llm(messages: List[Dict[str, Any]]) -> str:
    """
    调用 LLM（使用统一客户端，带指数退避重试和模型降级）

    Args:
        messages: 消息列表

    Returns:
        LLM 响应

    Raises:
        RuntimeError: 所有降级策略均失败时抛出
    """
    if llm_client is None:
        raise RuntimeError("LLM 客户端未初始化，请检查 .env 配置")

    try:
        return await llm_client.chat(messages)
    except LLMClientError as e:
        logger.error("LLM 调用最终失败: %s", e)
        raise RuntimeError(f"AI 服务暂时不可用，请稍后重试。错误: {e}")
    except Exception as e:
        logger.exception("LLM 调用发生未知错误")
        raise RuntimeError(f"AI 服务异常: {e}")


@router.get("/history")
async def get_chat_history() -> Dict[str, Any]:
    """
    获取聊天历史
    
    Returns:
        聊天历史
    """
    # TODO: 实现聊天历史存储
    return {
        'success': True,
        'history': []
    }


@router.post("/clear")
async def clear_chat() -> Dict[str, Any]:
    """
    清空聊天
    
    Returns:
        操作结果
    """
    # TODO: 实现清空聊天历史
    return {
        'success': True,
        'message': 'Chat cleared'
    }


@router.get("/compact/stats")
async def get_compact_stats() -> Dict[str, Any]:
    """
    获取压缩统计
    
    Returns:
        压缩统计信息
    """
    return {
        'success': True,
        'stats': context_manager.get_compact_stats()
    }
