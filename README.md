# 🤖 GitAgent

![PyPI version](https://img.shields.io/pypi/v/oh-my-git-agent) ![Supported Python](https://img.shields.io/pypi/pyversions/oh-my-git-agent) ![License](https://img.shields.io/pypi/l/oh-my-git-agent)

> ✨ 让 Git 提交变得简单又智能！自动整理变更、确保每天都有提交记录，还能用 AI 生成有趣的提交信息 🎉

![CLI 截图](screenshot.png)
![CLI 截图](screenshot2.png)

---

## 📦 安装

```bash
pip install oh-my-git-agent --upgrade
```

最佳实践：

```bash
# 1. 安装
pip install oh-my-git-agent

# 2. 进入你的 Git 仓库
cd /path/to/your/repo

# 3. 配置（可选，推荐使用 DeepSeek，性价比高）
gcli config --api-key sk-your-deepseek-key --auto-push

# 4. 运行（第一次建议先看看变更）
gcli ls

# 5. 一键提交
# 5.1 指定变更，一个 commit
gcli only src/ tests/ --one-commit
# 5.2 提交所有变更，每个文件一个 commit
gcli
# 5.3 手动添加文件到暂存区，再提交一个 commit
git add src/main.py README.md  # 你可以在可视化工具中操作
gcli --no-staging --one-commit
```

---

## 🚀 快速上手

### 场景 1️⃣：基础提交（无 AI）

最简单的用法，在你的 Git 仓库里直接运行：

```bash
# 💡 自动提交所有变更文件，每个文件单独提交
gcli
```

**效果**：
- ✅ 自动检测所有新增、修改、删除的文件
- ✅ 每个文件一个提交，提交时间均匀分布在"最近一次提交"到"现在"之间
- ✅ 提交信息简洁：`chore add README.md`、`chore rm old.txt` 等

完成后推送到远端：
```bash
git push origin main
```

---

### 场景 2️⃣：使用 AI 生成提交信息（推荐 🌟）

让 AI 帮你写出带 emoji 的有趣提交信息：

#### 使用 DeepSeek（默认，性价比高）

```bash
# 🎯 只需要一个 API Key！
gcli --api-key sk-your-deepseek-key
```

> 💡 **提示**：DeepSeek 是默认配置，无需指定 `--base-url` 和 `--model`

**生成的提交信息示例**：
```
🎉 [add README.md] 添加项目说明文档
✨ [add src/main.py] 实现核心逻辑功能
🐛 [add tests/test_main.py] 修复边界条件测试
🔥 [rm deprecated.py] 移除废弃代码
```

#### 使用 OpenAI GPT（需要梯子）

```bash
# 🌐 使用 OpenAI 官方 API
gcli --api-key sk-your-openai-key \
     --base-url https://api.openai.com/v1 \
     --model gpt-4o-mini
```

#### 使用其他兼容 OpenAI 的服务

```bash
# 🔧 支持任何兼容 OpenAI 协议的服务
gcli --api-key your-api-key \
     --base-url https://your-api-endpoint.com/v1 \
     --model your-model-name
```

---

### 场景 3️⃣：查看变更（不提交）

想先看看有哪些文件变更了？

```bash
# 👀 彩色输出所有变更，带编号
gcli ls
```

**输出示例**：
```
Untracked Files:
?   [  1] new_feature.py
?   [  2] config.yaml

Modified Files:
o   [  3] src/main.py
o   [  4] README.md

Deleted Files:
-   [  5] old_code.py
```

颜色说明：
- 🟡 黄色：未跟踪的新文件
- 🟢 绿色：已暂存的新增文件
- 🔵 蓝色：修改的文件
- 🔴 红色：删除的文件

---

### 场景 4️⃣：只提交特定文件或目录

有时候你只想提交某个目录的变更：

```bash
# 📁 只提交 src/ 目录下的变更
gcli only src/

# 📄 只提交单个文件
gcli only README.md

# 🤖 配合 AI 使用
gcli only src/ --api-key sk-your-deepseek-key
```

**实际案例**：
```bash
# 场景：前端和后端代码都改了，但只想先提交前端
gcli only frontend/

# 场景：只提交文档更新
gcli only docs/
```

---

### 场景 5️⃣：配置管理（避免每次输入 API Key）

#### 保存到本地项目（推荐）

```bash
# 💾 配置 API Key，只在当前项目生效
gcli config --api-key sk-your-deepseek-key

# 📝 配置完整参数
gcli config \
  --api-key sk-your-key \
  --base-url https://api.deepseek.com \
  --model deepseek-chat
```

配置会保存到 `.oh-my-git-agent/config.yaml`，以后直接运行：
```bash
gcli  # 自动读取配置，无需再输入 API Key
```

#### 保存到全局配置

```bash
# 🌍 全局配置，所有项目都能用
gcli config --api-key sk-your-key --global

# 查看当前配置
gcli config --show
```

**配置优先级**（从高到低）：
1. 命令行参数：`--api-key`
2. 本地配置：`./.oh-my-git-agent/config.yaml`
3. 环境变量：`.env` 文件（优先 `GITAGENT_OPENAI_API_KEY`、`GITAGENT_OPENAI_BASE_URL`、`GITAGENT_OPENAI_MODEL`，兼容 `OPENAI_*`）
4. 全局配置：`~/.oh-my-git-agent/config.yaml`


## 场景 6️⃣：合并多个文件为一个提交（新增 -m/--one-commit 参数）

有时候你可能希望将多个文件的变更合并为一个提交，而不是每个文件单独提交。现在你可以使用 `-m/--one-commit` 参数来实现这一点。

```bash
# 将所有变更文件合并为一个 commit
gcli -m
gcli only src/ -m
# 或
gcli --one-commit
gcli only src/ --one-commit
```

## 场景 7️⃣：手动添加文件到暂存区，再使用 GitAgent 提交

你也可以先使用 `git add <file>` 手动将文件添加到暂存区，然后使用 GitAgent 提交这些已暂存的文件。

```bash
# 手动添加文件到暂存区
git add src/main.py README.md
# 使用 GitAgent 提交已暂存的文件。
# 以下指令会忽略工作区的其他变更，只 commit 暂存区的文件，生成一个 commit message。
gcli --no-staging -m
```

---

## 💡 使用技巧

### 组合使用

```bash
# 1️⃣ 先查看有哪些变更
gcli ls

# 2️⃣ 只提交某个目录
gcli only src/ --api-key sk-xxx

# 3️⃣ 推送到远端
git push
```

### 在不同目录运行

```bash
# 🏠 不在仓库根目录？指定路径即可
gcli --repo-dir /path/to/your/repo

# 📍 配合 AI
gcli --repo-dir ~/projects/myapp --api-key sk-xxx
```

### 使用 .env 文件（推荐新手）

在项目根目录创建 `.env` 文件（推荐使用带前缀，避免与其他项目冲突）：

```bash
# .env (推荐)
GITAGENT_OPENAI_API_KEY=sk-your-deepseek-key
GITAGENT_OPENAI_BASE_URL=https://api.deepseek.com
GITAGENT_OPENAI_MODEL=deepseek-chat

# 向后兼容（不推荐）：
# OPENAI_API_KEY=sk-your-deepseek-key
# OPENAI_BASE_URL=https://api.deepseek.com
# OPENAI_MODEL=deepseek-chat
```

然后直接运行：
```bash
gcli  # 自动读取 .env 配置
```

---

## 🔍 工作原理

简单来说，GitAgent 会：

1. 📊 **收集变更**：扫描所有新增、修改、删除的文件
2. ⏰ **计算时间**：从"最近一次提交"到"现在"，均匀分配提交时间
3. 📝 **逐个提交**：每个文件单独提交，时间间隔自然
4. 🤖 **AI 增强**：（可选）读取文件 diff 或内容，生成有趣的提交信息

**为什么要均匀分布时间？**
- 让你的 GitHub 贡献图更好看 🎨
- 提交历史看起来更自然 📅
- 避免一次性提交几十个文件 🚀

---

## ❓ 常见问题

<details>
<summary><b>🔑 我的 API Key 安全吗？</b></summary>

- 配置文件保存在本地，不会上传到 Git
- 建议使用 `.env` 文件（记得加到 `.gitignore`）
- 或使用 `gcli config` 命令保存配置
</details>

<details>
<summary><b>💸 使用 AI 会很贵吗？</b></summary>

- DeepSeek 非常便宜，每次提交约 0.0001 元（不到 1 分钱）
- 100 次提交约 1 分钱，1000 次约 1 毛钱
- OpenAI 会贵一些，建议用 gpt-4o-mini
</details>

<details>
<summary><b>🌐 网络连接失败怎么办？</b></summary>

- 检查 `--base-url` 是否正确
- DeepSeek 无需梯子，直接访问
- OpenAI 需要梯子，或使用国内中转服务
- 可以先用 `gcli ls` 测试，不需要网络
</details>

<details>
<summary><b>📄 哪些文件会被提交？</b></summary>

- 所有 Git 检测到的变更（包括未跟踪文件）
- 自动忽略 `.git/` 目录
- 使用 `gcli ls` 预览哪些文件会被提交
</details>

<details>
<summary><b>🎯 能指定提交信息格式吗？</b></summary>

目前 AI 模式使用固定的 Prompt 生成带 emoji 的提交信息。如需自定义，可以：
- 修改 `gcli.py` 中的 Prompt
- 或使用非 AI 模式：`gcli`（生成 `chore add xxx`）
</details>

<details>
<summary><b>⚡ 命令补全怎么用？</b></summary>

```bash
# 安装补全
gcli --install-completion

# 重启终端或重新加载 shell 配置
source ~/.zshrc  # 或 ~/.bashrc
```
</details>

---

## 📚 命令速查

| 命令 | 说明 | 示例 |
|------|------|------|
| `gcli` | 提交所有变更 | `gcli` |
| `gcli ls` | 查看变更列表 | `gcli ls` |
| `gcli only <path>` | 只提交指定路径 | `gcli only src/` |
| `gcli config` | 配置管理 | `gcli config --show` |
| `--api-key` | 指定 API Key | `gcli --api-key sk-xxx` |
| `--base-url` | 指定 API 地址 | `gcli --base-url https://...` |
| `--model` | 指定模型 | `gcli --model gpt-4o-mini` |
| `--repo-dir` | 指定仓库路径 | `gcli --repo-dir ~/myrepo` |
| `-m/--one-commit` | 多文件合并为一个提交 | `gcli -m` |
| `--no-staging` | 只提交已暂存文件 | `gcli --no-staging` |

---

## 🔗 相关链接

- 📦 **PyPI**: [oh-my-git-agent](https://pypi.org/project/oh-my-git-agent/)
- 💻 **GitHub**: [LinXueyuanStdio/GitAgent](https://github.com/LinXueyuanStdio/GitAgent)
- 📝 **License**: MIT


**祝你提交愉快！** 🚀✨