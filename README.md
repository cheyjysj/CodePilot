# CodePilot - 本地化 AI 编程助手
### 1. 上下文压缩系统
-  **MicroCompact**：工具结果时间基裁剪（超过 5 分钟自动压缩）
-  **AutoCompact**：Token 阈值触发压缩（超过 100K tokens 自动触发）
-  **Manual Compact**：用户手动触发压缩


### 2. 记忆管理系统
- **Session Memory**：会话记忆（短期，会话结束释放）
-  **Project Memory**：项目记忆（中期，项目生命周期）
-  **Long-term Memory**：长期记忆（持久化，跨项目）
- 集成 **ChromaDB 向量数据库**

### 3. 缓存系统
-  **Prompt Cache**：API 层缓存（cacheBreak 感知）
-  **File Read Cache**：文件读取缓存（基于 mtime）
-  **File State Cache**：文件状态缓存（LRU + 大小感知）
-  **Disk Cache**：磁盘缓存（djb2Hash 确保跨版本稳定）


### 4. 工具系统
-  **File Tools**：`FileRead`、`FileEdit`、`FileWrite`
-  **Bash Tool**：终端命令执行
-  **Search Tools**：`Grep`、`Glob`
-  **12 种编程工具**

### 5. 技能系统
-  **Bundled Skills**：内置技能（代码审查、文档生成、测试用例生成）
-  **Disk-based Skills**：用户自定义技能
-  **MCP Skills**：远程技能（支持 MCP 协议）


## 📂 项目结构

```
codepilot/
├── backend/                   # Python 后端
│   ├── app/
│   │   ├── api/             # FastAPI 路由
│   │   │   ├── chat.py      # 聊天 API
│   │   │   ├── tools.py     # 工具 API
│   │   │   └── skills.py    # 技能 API
│   │   ├── core/            # 核心引擎
│   │   │   ├── context_manager.py   # 上下文压缩
│   │   │   ├── memory_manager.py    # 记忆管理
│   │   │   └── cache_manager.py     # 缓存管理
│   │   ├── tools/           # 工具系统
│   │   │   ├── base_tool.py
│   │   │   ├── file_tools.py
│   │   │   ├── bash_tool.py
│   │   │   ├── search_tools.py
│   │   │   └── tool_registry.py
│   │   ├── skills/          # 技能系统
│   │   │   ├── loader.py
│   │   │   └── executor.py
│   │   └── models/          # Pydantic 模型
│   ├── requirements.txt      # Python 依赖
│   └── main.py             # 入口文件
│
├── frontend/                  # React 前端
│   ├── src/
│   │   ├── components/      # React 组件
│   │   │   ├── ChatWindow.tsx
│   │   │   ├── ToolPanel.tsx
│   │   │   └── SkillPanel.tsx
│   │   ├── pages/           # 页面
│   │   ├── services/        # API 调用
│   │   │   └── WebSocketProvider.tsx
│   │   └── store/          # 状态管理
│   ├── package.json
│   └── tsconfig.json
│
└── README.md
```



## 📦 安装依赖

### 后端依赖

```bash
cd backend
pip install -r requirements.txt
```

### 前端依赖

```bash
cd frontend
npm install
```

## 🚀 运行项目

### 1. 启动后端

```bash
cd backend
python main.py
```

后端将在 `http://localhost:8000` 启动。

### 2. 启动前端

```bash
cd frontend
npm run dev
```

前端将在 `http://localhost:3000` 启动。

### 3. 安装 Ollama（可选）

如果想要使用本地 LLM 推理，需要安装 Ollama：

```bash
# macOS/Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows
# 下载并安装：https://ollama.com/download

# 拉取模型
ollama pull qwen2.5:14b
```


## 📖 使用指南

### 聊天功能

1. 打开前端界面 `http://localhost:3000`
2. 在输入框中输入消息
3. 按 `Enter` 发送（按 `Shift + Enter` 换行）
4. AI 助手将回复你的消息

### 工具功能

1. 点击顶部导航栏的 `Tools` 标签
2. 选择要使用的工具
3. 在 JSON 输入框中输入工具参数
4. 点击 `Execute Tool` 执行工具

### 技能功能

1. 点击顶部导航栏的 `Skills` 标签
2. 选择要使用的技能
3. 在 JSON 输入框中输入技能参数
4. 点击 `Execute Skill` 执行技能

## 🔧 配置说明

### 后端配置

编辑 `backend/main.py` 中的配置：

```python
# Ollama 模型
model='qwen2.5:14b'

# CORS 配置
allow_origins=["http://localhost:3000"]
```

### 前端配置

编辑 `frontend/vite.config.ts` 中的配置：

```typescript
// 代理配置
proxy: {
  '/api': {
    target: 'http://localhost:8000',
    changeOrigin: true,
  },
  '/ws': {
    target: 'ws://localhost:8000',
    ws: true,
  },
}
```

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 🙏 致谢

本项目借鉴了 **Claude Code** 的架构设计，特此致谢。
