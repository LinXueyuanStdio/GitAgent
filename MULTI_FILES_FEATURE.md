# Multi-Files Commit 功能说明

## 功能概述

新增 `-m/--multi-files` 参数，允许将多个文件合并为一个 commit 提交，而不是每个文件单独生成一个 commit。

## 使用方法

### 1. main 命令

```bash
# 将所有变更文件合并为一个 commit（不使用 AI）
python gcli.py main -m

# 将所有变更文件合并为一个 commit（使用 AI 生成提交信息）
python gcli.py main -m --ai

# 或者使用完整参数名
python gcli.py main --multi-files --ai
```

### 2. only 命令

```bash
# 将指定目录下的所有变更合并为一个 commit
python gcli.py only src/ -m

# 将多个目标路径下的变更合并为一个 commit（使用 AI）
python gcli.py only src/ tests/ -m --ai
```

## 功能特性

### 1. 智能消息生成

**Simple Commit（不使用 AI）:**
- 单一操作类型：`chore add 5 files` 或 `chore rm 3 files`
- 混合操作类型：`chore update 8 files`

**AI Commit（使用 AI）:**
- 分析所有文件的变更内容
- 生成一个总结性的 commit 消息
- 最多展示前 10 个文件的详细信息
- 自动带有 emoji 前缀

### 2. 批量处理

- 所有文件在同一个 commit 中提交
- 支持混合操作（add、modify、delete）
- 自动跳过 .git 目录
- 使用最新的 commit 日期

### 3. 文件描述

AI 模式下会为每个文件收集：
- 文件路径
- 操作类型（add/rm）
- 简要描述（diff 或文件内容前 1024 字符）

## 代码实现

### 1. BaseCommit 抽象类新增方法

```python
@abstractmethod
def generate_batch_message(self, files_info: list[dict]) -> str:
    """生成批量提交消息"""
    pass

def execute_batch(self, files_info: list[dict], commit_date: datetime):
    """批量执行 commit"""
    pass
```

### 2. SimpleCommit 实现

```python
def generate_batch_message(self, files_info: list[dict]) -> str:
    file_count = len(files_info)
    actions = set(info["action"] for info in files_info)

    if len(actions) == 1:
        action = actions.pop()
        return f"chore {action} {file_count} files"
    else:
        return f"chore update {file_count} files"
```

### 3. AICommit 实现

```python
def generate_batch_message(self, files_info: list[dict]) -> str:
    # 构建文件列表描述
    file_list = []
    for info in files_info:
        action = info["action"]
        filepath = info["filepath"]
        brief_desc = info.get("brief_desc")

        if brief_desc:
            file_list.append(f"[{action}] {filepath}:\n{brief_desc[:200]}...")
        else:
            file_list.append(f"[{action}] {filepath}")

    files_desc = "\n".join(file_list[:10])
    if len(file_list) > 10:
        files_desc += f"\n... and {len(file_list) - 10} more files"

    # 调用 AI API 生成消息
    # ...
```

## 使用场景

1. **功能开发完成**：多个相关文件一起提交
2. **批量重构**：一次性提交所有重构的文件
3. **依赖更新**：更新多个配置文件时合并提交
4. **文档更新**：多个文档修改一起提交

## 注意事项

1. 使用 `-m` 参数时，所有文件将使用同一个 commit 日期（最新的 commit 日期）
2. AI 模式下，会读取文件的 diff 或内容来生成更准确的提交消息
3. 如果文件过多（超过 10 个），AI 只会分析前 10 个文件的详细信息
4. 批量提交仍然会自动推送（如果开启了 `auto_push` 配置）

## 示例输出

### Simple Commit

```
[batch] committing 5 files at 2025-11-08 10:30:00
commit message: chore add 5 files
```

### AI Commit

```
[batch] committing 5 files at 2025-11-08 10:30:00
commit message: 🎉 [update] Add user authentication and database schema
```
