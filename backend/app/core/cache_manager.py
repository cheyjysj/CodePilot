"""
缓存管理器
实现四层缓存架构：Prompt Cache、File Read Cache、File State Cache、Disk Cache
借鉴 Claude Code 的缓存策略
"""

import os
import time
import json
import hashlib
from typing import Optional, Dict, Any
from datetime import datetime
import pickle


class FileState:
    """文件状态"""
    def __init__(self, content: str, mtime: float, size: int):
        self.content = content
        self.mtime = mtime  # 修改时间
        self.size = size      # 文件大小
        self.access_time = time.time()
        self.access_count = 1
    
    def update_access(self) -> None:
        """更新访问信息"""
        self.access_time = time.time()
        self.access_count += 1
    
    def is_stale(self, file_path: str) -> bool:
        """
        检查文件是否过期
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否过期
        """
        try:
            current_mtime = os.path.getmtime(file_path)
            return current_mtime != self.mtime
        except OSError:
            return True


class PromptCache:
    """Prompt Cache - API 层缓存"""
    
    def __init__(self):
        self.cache = {}
        self.cache_break = None  # cacheBreak 标识
    
    def get(self, prompt: str, cache_break: Optional[str] = None) -> Optional[str]:
        """
        获取缓存的 Prompt 响应
        
        Args:
            prompt: Prompt 字符串
            cache_break: cacheBreak 标识
            
        Returns:
            缓存的响应，如果没有则返回 None
        """
        # 如果 cacheBreak 变化，使缓存失效
        if cache_break and cache_break != self.cache_break:
            self.clear()
            self.cache_break = cache_break
        
        prompt_hash = self._hash(prompt)
        return self.cache.get(prompt_hash)
    
    def set(self, prompt: str, response: str, cache_break: Optional[str] = None) -> None:
        """
        设置 Prompt 缓存
        
        Args:
            prompt: Prompt 字符串
            response: 响应字符串
            cache_break: cacheBreak 标识
        """
        if cache_break:
            self.cache_break = cache_break
        
        prompt_hash = self._hash(prompt)
        self.cache[prompt_hash] = {
            'response': response,
            'timestamp': time.time(),
            'cache_break': cache_break
        }
    
    def clear(self) -> None:
        """清空缓存"""
        self.cache.clear()
    
    def _hash(self, text: str) -> str:
        """计算哈希值"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()


class FileReadCache:
    """File Read Cache - 文件读取缓存"""
    
    def __init__(self, max_size: int = 1000):
        self.cache = {}
        self.max_size = max_size
    
    def get(self, file_path: str) -> Optional[str]:
        """
        获取缓存的文件内容
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件内容，如果没有则返回 None
        """
        if file_path not in self.cache:
            return None
        
        cached = self.cache[file_path]
        
        # 检查文件是否修改
        try:
            current_mtime = os.path.getmtime(file_path)
            if current_mtime != cached['mtime']:
                # 文件已修改，使缓存失效
                del self.cache[file_path]
                return None
        except OSError:
            # 文件不存在，使缓存失效
            del self.cache[file_path]
            return None
        
        return cached['content']
    
    def set(self, file_path: str, content: str) -> None:
        """
        设置文件缓存
        
        Args:
            file_path: 文件路径
            content: 文件内容
        """
        # 如果缓存已满，淘汰最旧的条目
        if len(self.cache) >= self.max_size:
            oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k]['timestamp'])
            del self.cache[oldest_key]
        
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            mtime = 0
        
        self.cache[file_path] = {
            'content': content,
            'mtime': mtime,
            'timestamp': time.time()
        }
    
    def invalidate(self, file_path: str) -> None:
        """使指定文件的缓存失效"""
        if file_path in self.cache:
            del self.cache[file_path]
    
    def clear(self) -> None:
        """清空缓存"""
        self.cache.clear()


class FileStateCache:
    """File State Cache - LRU 缓存"""
    
    def __init__(self, max_entries: int = 100, max_size_mb: int = 25):
        self.max_entries = max_entries
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.current_size = 0
        
        # 使用 LRU 策略
        self.cache = {}
        self.access_order = []
    
    def get(self, file_path: str) -> Optional[FileState]:
        """
        获取文件状态
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件状态，如果没有则返回 None
        """
        if file_path not in self.cache:
            return None
        
        state = self.cache[file_path]
        
        # 更新访问顺序
        self._update_access_order(file_path)
        
        # 更新访问信息
        state.update_access()
        
        return state
    
    def set(self, file_path: str, state: FileState) -> None:
        """
        设置文件状态
        
        Args:
            file_path: 文件路径
            state: 文件状态
        """
        # 计算新条目大小
        new_size = self._calculate_size(file_path, state)
        
        # 如果缓存已满，淘汰条目
        while (len(self.cache) >= self.max_entries or 
               self.current_size + new_size > self.max_size_bytes):
            if not self.cache:
                break
            self._evict_lru()
        
        # 添加新条目
        self.cache[file_path] = state
        self.current_size += new_size
        self._update_access_order(file_path)
    
    def invalidate(self, file_path: str) -> None:
        """使指定文件的缓存失效"""
        if file_path in self.cache:
            state = self.cache[file_path]
            self.current_size -= self._calculate_size(file_path, state)
            del self.cache[file_path]
            self.access_order.remove(file_path)
    
    def clear(self) -> None:
        """清空缓存"""
        self.cache.clear()
        self.access_order.clear()
        self.current_size = 0
    
    def _update_access_order(self, file_path: str) -> None:
        """更新访问顺序"""
        if file_path in self.access_order:
            self.access_order.remove(file_path)
        self.access_order.append(file_path)
    
    def _evict_lru(self) -> None:
        """淘汰最近最少使用的条目"""
        if not self.access_order:
            return
        
        lru_key = self.access_order[0]
        self.invalidate(lru_key)
    
    def _calculate_size(self, file_path: str, state: FileState) -> int:
        """
        计算缓存条目大小
        
        Args:
            file_path: 文件路径
            state: 文件状态
            
        Returns:
            大小（字节）
        """
        # 文件路径大小 + 内容大小 + 元数据大小
        return len(file_path) * 2 + len(state.content) * 2 + 64
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        return {
            'entries': len(self.cache),
            'max_entries': self.max_entries,
            'current_size_mb': self.current_size / 1024 / 1024,
            'max_size_mb': self.max_size_bytes / 1024 / 1024,
            'hit_rate': self._calculate_hit_rate()
        }
    
    def _calculate_hit_rate(self) -> float:
        """计算命中率（简化版）"""
        # 这里需要跟踪命中/未命中次数
        # 暂时返回 0
        return 0.0


class DiskCache:
    """Disk Cache - 磁盘缓存"""
    
    def __init__(self, cache_dir: str = "~/.codepilot/cache"):
        self.cache_dir = os.path.expanduser(cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def get_path(self, project_path: str) -> str:
        """
        获取磁盘缓存路径
        
        Args:
            project_path: 项目路径
            
        Returns:
            缓存路径
        """
        hash_val = self.djb2_hash(project_path)
        return os.path.join(self.cache_dir, hash_val)
    
    def read(self, project_path: str) -> Optional[Dict[str, Any]]:
        """
        读取磁盘缓存
        
        Args:
            project_path: 项目路径
            
        Returns:
            缓存数据，如果没有则返回 None
        """
        cache_path = self.get_path(project_path)
        
        if not os.path.exists(cache_path):
            return None
        
        try:
            with open(cache_path, 'rb') as f:
                data = pickle.load(f)
            return data
        except Exception:
            return None
    
    def write(self, project_path: str, data: Dict[str, Any]) -> None:
        """
        写入磁盘缓存
        
        Args:
            project_path: 项目路径
            data: 缓存数据
        """
        cache_path = self.get_path(project_path)
        
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f)
        except Exception as e:
            print(f"Error writing disk cache: {e}")
    
    def invalidate(self, project_path: str) -> None:
        """使磁盘缓存失效"""
        cache_path = self.get_path(project_path)
        
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
            except Exception as e:
                print(f"Error removing disk cache: {e}")
    
    def clear(self) -> None:
        """清空磁盘缓存"""
        try:
            for filename in os.listdir(self.cache_dir):
                file_path = os.path.join(self.cache_dir, filename)
                if os.path.isfile(file_path):
                    os.remove(file_path)
        except Exception as e:
            print(f"Error clearing disk cache: {e}")
    
    def djb2_hash(self, text: str) -> str:
        """
        djb2 哈希算法
        
        Args:
            text: 输入字符串
            
        Returns:
            哈希值（十六进制）
        """
        hash_val = 5381
        for char in text:
            hash_val = ((hash_val << 5) + hash_val) + ord(char)
            hash_val = hash_val & 0xFFFFFFFF  # 转换为 32 位整数
        
        return format(hash_val, '08x')  # 返回十六进制字符串


class CacheManager:
    """缓存管理器 - 统一入口"""
    
    def __init__(self):
        # 初始化四层缓存
        self.prompt_cache = PromptCache()
        self.file_read_cache = FileReadCache()
        self.file_state_cache = FileStateCache()
        self.disk_cache = DiskCache()
        
        # 统计数据
        self.stats = {
            'prompt_hits': 0,
            'prompt_misses': 0,
            'file_read_hits': 0,
            'file_read_misses': 0,
            'file_state_hits': 0,
            'file_state_misses': 0,
            'disk_hits': 0,
            'disk_misses': 0
        }
    
    def read_file(self, file_path: str) -> Optional[str]:
        """
        读取文件（带缓存）
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件内容，如果没有则返回 None
        """
        # 1. 检查 File Read Cache
        content = self.file_read_cache.get(file_path)
        if content is not None:
            self.stats['file_read_hits'] += 1
            return content
        
        self.stats['file_read_misses'] += 1
        
        # 2. 检查 File State Cache
        state = self.file_state_cache.get(file_path)
        if state and not state.is_stale(file_path):
            # 从状态缓存读取内容
            content = state.content
            self.file_read_cache.set(file_path, content)
            self.stats['file_state_hits'] += 1
            return content
        
        self.stats['file_state_misses'] += 1
        
        # 3. 从磁盘读取
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 更新缓存
            self.file_read_cache.set(file_path, content)
            
            mtime = os.path.getmtime(file_path)
            size = os.path.getsize(file_path)
            state = FileState(content, mtime, size)
            self.file_state_cache.set(file_path, state)
            
            return content
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return None
    
    def write_file(self, file_path: str, content: str) -> bool:
        """
        写入文件（并使缓存失效）
        
        Args:
            file_path: 文件路径
            content: 文件内容
            
        Returns:
            是否成功
        """
        try:
            # 写入磁盘
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # 使缓存失效
            self.file_read_cache.invalidate(file_path)
            self.file_state_cache.invalidate(file_path)
            
            return True
        except Exception as e:
            print(f"Error writing file {file_path}: {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计
        
        Returns:
            统计信息
        """
        total_hits = sum(v for k, v in self.stats.items() if k.endswith('_hits'))
        total_misses = sum(v for k, v in self.stats.items() if k.endswith('_misses'))
        total_requests = total_hits + total_misses
        
        overall_hit_rate = 0.0
        if total_requests > 0:
            overall_hit_rate = (total_hits / total_requests) * 100
        
        return {
            'overall_hit_rate': f"{overall_hit_rate:.2f}%",
            'prompt_cache_hit_rate': self._calculate_rate('prompt_hits', 'prompt_misses'),
            'file_read_cache_hit_rate': self._calculate_rate('file_read_hits', 'file_read_misses'),
            'file_state_cache_hit_rate': self._calculate_rate('file_state_hits', 'file_state_misses'),
            'disk_cache_hit_rate': self._calculate_rate('disk_hits', 'disk_misses'),
            'file_state_cache_stats': self.file_state_cache.get_stats(),
            'raw_stats': self.stats
        }
    
    def _calculate_rate(self, hits_key: str, misses_key: str) -> str:
        """计算命中率"""
        hits = self.stats[hits_key]
        misses = self.stats[misses_key]
        total = hits + misses
        
        if total == 0:
            return "0.00%"
        
        rate = (hits / total) * 100
        return f"{rate:.2f}%"
    
    def clear_all_caches(self) -> None:
        """清空所有缓存"""
        self.prompt_cache.clear()
        self.file_read_cache.clear()
        self.file_state_cache.clear()
        self.disk_cache.clear()
        
        # 重置统计
        for key in self.stats:
            self.stats[key] = 0
