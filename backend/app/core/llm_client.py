"""
统一 LLM 客户端
支持 DeepSeek/OpenAI API，实现 Claude Code 风格的指数退避重试和模型降级策略
"""

import os
import asyncio
import logging
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """LLM 客户端基础异常"""
    pass


class LLMClient:
    """
    统一 LLM 客户端

    - 从 .env 读取 API 配置（优先 DeepSeek，回退 OpenAI）
    - 指数退避重试（2s/4s/8s/16s，最多 4 次重试）
    - 模型降级（primary → fallback → 错误提示）
    """

    PRIMARY_MODEL = "deepseek-chat"
    FALLBACK_MODEL = "gpt-3.5-turbo"

    # 指数退避配置（与 Claude Code 一致）
    RETRY_DELAYS = [2, 4, 8, 16]  # 秒
    MAX_RETRIES = 4

    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.deepseek.com"
        self.model = os.getenv("LLM_MODEL", self.PRIMARY_MODEL)

        if not self.api_key:
            raise LLMClientError(
                "未找到 API 密钥。请在 .env 文件中配置 DEEPSEEK_API_KEY 或 OPENAI_API_KEY"
            )

        self._client: Optional[AsyncOpenAI] = None
        self._current_model = self.model

    def _get_client(self) -> AsyncOpenAI:
        """延迟初始化 AsyncOpenAI 客户端"""
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        return self._client

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> str:
        """
        调用 LLM，带指数退避重试

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            model: 模型名称（覆盖默认模型）

        Returns:
            LLM 响应内容

        Raises:
            LLMClientError: 所有重试和降级都失败后抛出
        """
        last_error = None
        model_to_use = model or self._current_model

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                client = self._get_client()
                response = await client.chat.completions.create(
                    model=model_to_use,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = response.choices[0].message.content
                if content is None:
                    raise LLMClientError("LLM 返回了空响应")
                return content

            except Exception as e:
                last_error = e
                logger.warning(
                    "LLM 调用失败 (attempt %d/%d, model=%s): %s",
                    attempt + 1, self.MAX_RETRIES + 1, model_to_use, e,
                )

                # 最后一次尝试失败后，尝试模型降级
                if attempt == self.MAX_RETRIES:
                    if model_to_use != self.FALLBACK_MODEL and self._is_available(self.FALLBACK_MODEL):
                        logger.info("尝试模型降级: %s → %s", model_to_use, self.FALLBACK_MODEL)
                        model_to_use = self.FALLBACK_MODEL
                        # 重置重试计数，用降级模型再试一轮
                        attempt = -1
                        continue
                    break

                # 指数退避等待
                delay = self.RETRY_DELAYS[attempt]
                await asyncio.sleep(delay)

        raise LLMClientError(
            f"LLM 调用失败（已重试 {self.MAX_RETRIES} 次并尝试模型降级）: {last_error}"
        )

    async def generate_summary(
        self,
        content: str,
        instructions: str = "请生成以下内容的简洁摘要，保留关键信息和决策点：",
        temperature: float = 0.3,
        max_tokens: int = 500,
    ) -> str:
        """
        使用 LLM 生成内容摘要

        Args:
            content: 待摘要的内容
            instructions: 摘要指令（system prompt）
            temperature: 温度参数（摘要任务用低温度）
            max_tokens: 摘要最大长度

        Returns:
            生成的摘要
        """
        messages = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": content},
        ]
        return await self.chat(messages, temperature=temperature, max_tokens=max_tokens)

    async def generate_memory_summary(
        self,
        memories: List[str],
        context: Optional[str] = None,
    ) -> str:
        """
        使用 LLM 生成会话记忆摘要

        Args:
            memories: 记忆条目列表
            context: 额外上下文信息（可选）

        Returns:
            生成的记忆摘要
        """
        content = "\n---\n".join(memories)
        if context:
            content = f"上下文信息: {context}\n\n会话内容:\n{content}"

        return await self.generate_summary(
            content=content,
            instructions="你是一个会话记忆摘要专家。请分析以下对话记录，生成一个简洁但信息丰富的摘要。"
                         "请包含：\n1. 讨论的主要话题\n2. 用户的关键需求\n3. 已经做出的决策"
                         "\n4. 待办事项\n5. 重要的代码变更或技术选型",
            temperature=0.3,
            max_tokens=800,
        )

    async def generate_context_summary(
        self,
        content: str,
        tool_name: Optional[str] = None,
    ) -> str:
        """
        使用 LLM 生成上下文压缩摘要

        Args:
            content: 待压缩的上下文内容
            tool_name: 工具名称（可选）

        Returns:
            压缩后的摘要
        """
        tool_context = f"这是 {tool_name} 工具的执行结果。" if tool_name else ""

        return await self.generate_summary(
            content=content,
            instructions=f"{tool_context}请压缩以下内容，保留所有关键信息。"
                         "生成一个简洁的结构化摘要。如果包含代码或数据，请保留核心部分。",
            temperature=0.3,
            max_tokens=1000,
        )

    def _is_available(self, model: str) -> bool:
        """检查模型是否可用（基于基本配置判断）"""
        # 如果 base_url 指向 DeepSeek，则 deepseek-chat 可用
        if "deepseek" in self.base_url:
            return "deepseek" in model or "gpt" in model
        # 如果 base_url 指向 OpenAI，则 gpt 模型可用
        if "openai" in self.base_url:
            return "gpt" in model
        # 默认认为可用
        return True

    async def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ):
        """
        流式调用 LLM，逐 token 产出

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大输出 token 数
            model: 模型名称

        Yields:
            str: 每个 token
        """
        client = self._get_client()
        model_to_use = model or self._current_model

        try:
            stream = await client.chat.completions.create(
                model=model_to_use,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens or 4096,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as e:
            raise LLMClientError(f"LLM 流式调用失败: {e}") from e

    @property
    def client(self) -> AsyncOpenAI:
        """获取底层 OpenAI 客户端（供高级用法）"""
        return self._get_client()
