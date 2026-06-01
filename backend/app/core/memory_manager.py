"""
记忆管理器
实现三层记忆架构：Session Memory、Project Memory、Long-term Memory
借鉴 Claude Code 的记忆管理策略
"""

import json
import time
import asyncio
import chromadb
import warnings
from typing import Dict, List, Optional, Any
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from datetime import datetime
import os

# 抑制 SentenceTransformers 的 FutureWarning
warnings.filterwarnings("ignore", category=FutureWarning, module="sentence_transformers")

# 设置 HuggingFace 镜像（解决国内访问问题）
os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')


class MemoryItem:
    """记忆条目"""
    def __init__(self, content: str, metadata: Dict[str, Any] = None):
        self.content = content
        self.metadata = metadata or {}
        self.timestamp = time.time()
        self.id = f"mem_{int(self.timestamp * 1000)}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'content': self.content,
            'metadata': self.metadata,
            'timestamp': self.timestamp
        }


class SessionMemory:
    """会话记忆 - 短期记忆"""

    def __init__(self, max_items: int = 100):
        self.memories: List[MemoryItem] = []
        self.max_items = max_items
        self.summary: Optional[str] = None
        self._llm_client = None  # 延迟初始化

    def _get_llm_client(self):
        """延迟获取 LLM 客户端"""
        if self._llm_client is None:
            try:
                from app.core.llm_client import LLMClient
                self._llm_client = LLMClient()
            except Exception as e:
                print(f"LLM 客户端初始化失败: {e}")
                self._llm_client = None
        return self._llm_client

    def add(self, item: MemoryItem) -> None:
        """添加记忆"""
        self.memories.append(item)

        # 如果超过最大条目，压缩
        if len(self.memories) > self.max_items:
            # 尝试异步压缩，如果不在事件循环中则同步压缩
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(self.compact_async())
                else:
                    self.compact()
            except RuntimeError:
                self.compact()

    def compact(self) -> str:
        """
        压缩会话记忆（同步版本，使用 LLM 生成摘要）
        如果 LLM 不可用，使用简单摘要作为降级

        Returns:
            压缩后的摘要
        """
        if not self.memories:
            return ""

        # 拼接所有记忆
        content = "\n".join([m.content for m in self.memories])

        # 尝试使用 LLM 生成摘要
        llm = self._get_llm_client()
        if llm:
            try:
                # 在同步环境中运行异步 LLM 调用
                summary = asyncio.run(
                    llm.generate_memory_summary(
                        memories=[m.content for m in self.memories],
                    )
                )
                if summary:
                    self.summary = summary
                    self.memories.clear()
                    return self.summary
            except Exception as e:
                print(f"LLM 摘要生成失败，使用降级策略: {e}")

        # 降级策略：使用简单摘要
        self.summary = (
            f"[Session Summary] {len(self.memories)} items, "
            f"last update: {datetime.now().isoformat()}"
        )

        # 清空记忆
        self.memories.clear()

        return self.summary

    async def compact_async(self) -> str:
        """
        压缩会话记忆（异步版本，使用 LLM 生成摘要）

        Returns:
            压缩后的摘要
        """
        if not self.memories:
            return ""

        # 拼接所有记忆
        content = "\n".join([m.content for m in self.memories])

        # 使用 LLM 生成摘要
        llm = self._get_llm_client()
        if llm:
            try:
                summary = await llm.generate_memory_summary(
                    memories=[m.content for m in self.memories],
                )
                if summary:
                    self.summary = summary
                    self.memories.clear()
                    return self.summary
            except Exception as e:
                print(f"LLM 异步摘要生成失败，使用降级策略: {e}")

        # 降级：使用同步 compact
        return self.compact()
    
    def search(self, query: str, top_k: int = 5) -> List[MemoryItem]:
        """
        搜索会话记忆
        
        Args:
            query: 查询字符串
            top_k: 返回前 k 个结果
            
        Returns:
            相关记忆列表
        """
        if not self.memories:
            return []
        
        # 简单关键词匹配（可以用向量检索优化）
        results = []
        keywords = set(query.lower().split())
        
        for item in self.memories:
            content_lower = item.content.lower()
            if any(keyword in content_lower for keyword in keywords):
                results.append(item)
        
        return results[:top_k]
    
    def clear(self) -> None:
        """清空会话记忆"""
        self.memories.clear()
        self.summary = None


class ProjectMemory:
    """项目记忆 - 中期记忆"""
    
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.memories: Dict[str, MemoryItem] = {}
        self.metadata = {
            'project_name': os.path.basename(project_path),
            'created_at': time.time(),
            'last_accessed': time.time()
        }
    
    def add(self, key: str, item: MemoryItem) -> None:
        """添加项目记忆"""
        self.memories[key] = item
        self.metadata['last_accessed'] = time.time()
    
    def get(self, key: str) -> Optional[MemoryItem]:
        """获取项目记忆"""
        return self.memories.get(key)
    
    def search(self, query: str, top_k: int = 5) -> List[MemoryItem]:
        """
        搜索项目记忆
        
        Args:
            query: 查询字符串
            top_k: 返回前 k 个结果
            
        Returns:
            相关记忆列表
        """
        if not self.memories:
            return []
        
        results = []
        keywords = set(query.lower().split())
        
        for item in self.memories.values():
            content_lower = item.content.lower()
            if any(keyword in content_lower for keyword in keywords):
                results.append(item)
        
        return results[:top_k]
    
    def save(self) -> None:
        """保存项目记忆到磁盘"""
        memory_file = os.path.join(self.project_path, '.codepilot', 'project_memory.json')
        os.makedirs(os.path.dirname(memory_file), exist_ok=True)
        
        data = {
            'metadata': self.metadata,
            'memories': {k: v.to_dict() for k, v in self.memories.items()}
        }
        
        with open(memory_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load(self) -> None:
        """从磁盘加载项目记忆"""
        memory_file = os.path.join(self.project_path, '.codepilot', 'project_memory.json')
        
        if not os.path.exists(memory_file):
            return
        
        with open(memory_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.metadata = data.get('metadata', {})
        self.memories = {
            k: MemoryItem(**v) for k, v in data.get('memories', {}).items()
        }


class LongTermMemory:
    """长期记忆 - 持久化记忆"""
    
    def __init__(self, db_path: str = "~/.codepilot/chroma"):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(self.db_path, exist_ok=True)
        
        # 初始化 ChromaDB
        self.client = chromadb.PersistentClient(path=self.db_path)
        self.collection = self.client.get_or_create_collection(
            name="codepilot_memories",
            metadata={"hnsw:space": "cosine"}
        )
        
        # 初始化嵌入模型（使用镜像源）
        model_name = 'all-MiniLM-L6-v2'
        cache_folder = os.path.join(os.path.dirname(__file__), '..', 'models', 'cache')
        os.makedirs(cache_folder, exist_ok=True)
        
        try:
            # 尝试从本地缓存加载，如果失败则从镜像源下载
            self.embedding_model = SentenceTransformer(
                model_name, 
                cache_folder=cache_folder,
                use_auth_token=False
            )
        except Exception as e:
            print(f"警告: 模型加载失败 ({e})")
            print("尝试使用离线模式...")
            try:
                self.embedding_model = SentenceTransformer(
                    model_name,
                    cache_folder=cache_folder,
                    local_files_only=True
                )
            except:
                raise RuntimeError(
                    f"无法加载模型 {model_name}。\n"
                    "请手动下载模型或使用 VPN 后重试。\n"
                    "或设置环境变量: $env:HF_ENDPOINT='https://hf-mirror.com'"
                )
    
    def add(self, item: MemoryItem) -> None:
        """
        添加长期记忆
        
        Args:
            item: 记忆条目
        """
        # 生成嵌入
        embedding = self.embedding_model.encode(item.content)
        
        # 添加到向量数据库
        self.collection.add(
            embeddings=[embedding.tolist()],
            documents=[item.content],
            metadatas=[item.metadata],
            ids=[item.id]
        )
    
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        搜索长期记忆（向量检索）
        
        Args:
            query: 查询字符串
            top_k: 返回前 k 个结果
            
        Returns:
            相关记忆列表
        """
        # 生成查询嵌入
        query_embedding = self.embedding_model.encode(query)
        
        # 向量检索
        results = self.collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=top_k
        )
        
        # 格式化结果
        memories = []
        if results and results['documents']:
            for i, doc in enumerate(results['documents'][0]):
                memory = {
                    'content': doc,
                    'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                    'distance': results['distances'][0][i] if results['distances'] else 0.0
                }
                memories.append(memory)
        
        return memories
    
    def delete(self, memory_id: str) -> None:
        """删除长期记忆"""
        self.collection.delete(ids=[memory_id])
    
    def clear(self) -> None:
        """清空长期记忆"""
        self.collection.delete(where={})


class MemoryManager:
    """记忆管理器 - 统一入口"""
    
    def __init__(self, project_path: str = "."):
        self.project_path = project_path
        
        # 初始化二层记忆（会话 + 项目）
        self.session_memory = SessionMemory()
        self.project_memory = ProjectMemory(project_path)
        
        # LongTermMemory 延迟加载（需要下载模型，避免阻塞启动）
        self._long_term_memory = None
        self._long_term_init_failed = False  # 标记初始化是否已失败
        
        # 加载项目记忆
        self.project_memory.load()
    
    @property
    def long_term_memory(self):
        """延迟初始化长期记忆（首次访问时才加载模型）"""
        if self._long_term_memory is None and not self._long_term_init_failed:
            try:
                self._long_term_memory = LongTermMemory()
            except Exception as e:
                self._long_term_init_failed = True
                print(f"警告: 长期记忆初始化失败 ({e})，向量检索功能不可用。")
        return self._long_term_memory
    
    def add_to_session(self, content: str, metadata: Dict[str, Any] = None) -> None:
        """
        添加到会话记忆
        
        Args:
            content: 记忆内容
            metadata: 元数据
        """
        item = MemoryItem(content, metadata)
        self.session_memory.add(item)
    
    def add_to_project(self, key: str, content: str, metadata: Dict[str, Any] = None) -> None:
        """
        添加到项目记忆
        
        Args:
            key: 记忆键
            content: 记忆内容
            metadata: 元数据
        """
        item = MemoryItem(content, metadata)
        self.project_memory.add(key, item)
        
        # 持久化
        self.project_memory.save()
    
    def add_to_long_term(self, content: str, metadata: Dict[str, Any] = None) -> None:
        """
        添加到长期记忆
        
        Args:
            content: 记忆内容
            metadata: 元数据
        """
        if self.long_term_memory is None:
            return
        item = MemoryItem(content, metadata)
        self.long_term_memory.add(item)
    
    def recall(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        从三层记忆中检索
        
        Args:
            query: 查询字符串
            top_k: 每层返回前 k 个结果
            
        Returns:
            相关记忆列表
        """
        results = []
        
        # 1. 搜索会话记忆
        session_items = self.session_memory.search(query, top_k)
        for item in session_items:
            results.append({
                'content': item.content,
                'source': 'session',
                'metadata': item.metadata,
                'timestamp': item.timestamp
            })
        
        # 2. 搜索项目记忆
        project_items = self.project_memory.search(query, top_k)
        for item in project_items:
            results.append({
                'content': item.content,
                'source': 'project',
                'metadata': item.metadata,
                'timestamp': item.timestamp
            })
        
        # 3. 搜索长期记忆（如果可用）
        if self.long_term_memory is not None:
            long_term_items = self.long_term_memory.search(query, top_k)
            for item in long_term_items:
                results.append({
                    'content': item['content'],
                    'source': 'long_term',
                    'metadata': item['metadata'],
                    'distance': item['distance']
                })
        
        # 按相关性排序（这里简单按来源排序）
        results.sort(key=lambda x: (
            0 if x['source'] == 'session' else
            1 if x['source'] == 'project' else 2
        ))
        
        return results[:top_k * 3]
    
    def compact_session(self) -> str:
        """
        压缩会话记忆（同步）

        Returns:
            压缩后的摘要
        """
        summary = self.session_memory.compact()

        # 将摘要保存到项目记忆
        if summary:
            self.add_to_project(
                f"session_summary_{int(time.time())}",
                summary,
                {'type': 'session_summary'}
            )

        return summary

    async def compact_session_async(self) -> str:
        """
        压缩会话记忆（异步，使用 LLM 生成摘要）

        Returns:
            压缩后的摘要
        """
        summary = await self.session_memory.compact_async()

        # 将摘要保存到项目记忆
        if summary:
            self.add_to_project(
                f"session_summary_{int(time.time())}",
                summary,
                {'type': 'session_summary'}
            )

        return summary
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取记忆统计
        
        Returns:
            统计信息
        """
        return {
            'session_memory_count': len(self.session_memory.memories),
            'project_memory_count': len(self.project_memory.memories),
            'long_term_memory_count': (
                self.long_term_memory.collection.count()
                if self.long_term_memory is not None else 0
            ),
            'session_summary': self.session_memory.summary
        }
