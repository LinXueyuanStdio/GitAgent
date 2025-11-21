from typing import Literal, Optional
from typing_extensions import Annotated
from datetime import datetime, timedelta
from pathlib import Path
from abc import ABC, abstractmethod
import os
import time

import typer
from typer import colors
import git
from loguru import logger
import yaml
from dotenv import load_dotenv

# pip install GitPython

cli = typer.Typer(help="自动填写 commit 信息提交代码")


# ==================== 配置管理 ====================
class ConfigManager:
    """配置管理器，处理多层级配置优先级"""

    GLOBAL_CONFIG_DIR = Path.home() / ".oh-my-git-agent"
    GLOBAL_CONFIG_FILE = GLOBAL_CONFIG_DIR / "config.yaml"
    LOCAL_CONFIG_DIR = Path(".oh-my-git-agent")
    LOCAL_CONFIG_FILE = LOCAL_CONFIG_DIR / "config.yaml"
    LOCAL_ENV_FILE = Path(".env")

    @classmethod
    def get_config(cls, cli_api_key: Optional[str] = None,
                   cli_base_url: Optional[str] = None,
                   cli_model: Optional[str] = None) -> dict:
        """
        获取配置，优先级：
        命令行参数 > ./.oh-my-git-agent/config > .env > ~/.oh-my-git-agent/config
        """
        config = {
            "api_key": None,
            "base_url": "https://api.deepseek.com/v1",
            "model": "deepseek-chat",
            "auto_push": False,
        }

        # 1. 全局配置
        if cls.GLOBAL_CONFIG_FILE.exists():
            with open(cls.GLOBAL_CONFIG_FILE, 'r', encoding='utf-8') as f:
                global_config = yaml.safe_load(f) or {}
                config.update(global_config)

        # 2. 本地 .env 文件
        if cls.LOCAL_ENV_FILE.exists():
            load_dotenv(cls.LOCAL_ENV_FILE)
            # 优先读取带前缀的变量，避免与其他项目冲突；同时兼容历史的无前缀变量
            api_key = os.getenv("GITAGENT_API_KEY")
            base_url = os.getenv("GITAGENT_BASE_URL")
            model = os.getenv("GITAGENT_MODEL")

            if api_key:
                config["api_key"] = api_key
            if base_url:
                config["base_url"] = base_url
            if model:
                config["model"] = model

        # 3. 本地配置文件
        if cls.LOCAL_CONFIG_FILE.exists():
            with open(cls.LOCAL_CONFIG_FILE, 'r', encoding='utf-8') as f:
                local_config = yaml.safe_load(f) or {}
                config.update(local_config)

        # 4. 命令行参数（最高优先级）
        if cli_api_key:
            config["api_key"] = cli_api_key
        if cli_base_url:
            config["base_url"] = cli_base_url
        if cli_model:
            config["model"] = cli_model

        return config

    @classmethod
    def save_config(cls, api_key: Optional[str] = None,
                   base_url: Optional[str] = None,
                   model: Optional[str] = None,
                   auto_push: Optional[bool] = None,
                   global_config: bool = False):
        """保存配置到文件"""
        config_file = cls.GLOBAL_CONFIG_FILE if global_config else cls.LOCAL_CONFIG_FILE
        config_dir = cls.GLOBAL_CONFIG_DIR if global_config else cls.LOCAL_CONFIG_DIR

        # 确保目录存在
        config_dir.mkdir(parents=True, exist_ok=True)

        # 读取现有配置
        existing_config = {}
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                existing_config = yaml.safe_load(f) or {}

        # 更新配置
        if api_key:
            existing_config["api_key"] = api_key
        if base_url:
            existing_config["base_url"] = base_url
        if model:
            existing_config["model"] = model
        if auto_push is not None:
            existing_config["auto_push"] = bool(auto_push)

        # 写入配置
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.safe_dump(existing_config, f, allow_unicode=True)

        scope = "全局" if global_config else "本地"
        print(f"配置已保存到{scope}配置文件: {config_file}")


def _find_git_root(start_path: Path) -> Optional[Path]:
    """向父级追溯寻找 .git 目录，返回仓库根目录路径。"""
    current = start_path
    if current.is_file():
        current = current.parent

    while True:
        git_dir = current / ".git"
        if git_dir.exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def resolve_repo_directory(repo_dir: str) -> tuple[Path, Path]:
    """解析 repo_dir，并在需要时上溯到 git 根目录。

    Returns:
        (resolved_repo_dir, user_cwd)
    """
    user_cwd = Path.cwd().resolve()
    target = Path(repo_dir)
    if not target.is_absolute():
        target = (user_cwd / target).resolve()
    else:
        target = target.resolve()

    git_root = _find_git_root(target)
    if git_root:
        return git_root, user_cwd
    return target, user_cwd


# ==================== Commit 抽象类 ====================
class BaseCommit(ABC):
    """Commit 基类"""

    def __init__(self, index: git.IndexFile):
        self.index = index

    @abstractmethod
    def generate_message(self, action: Literal["add", "rm"],
                        filepath: str,
                        brief_desc: Optional[str] = None) -> str:
        """生成 commit 消息"""
        pass

    @abstractmethod
    def generate_batch_message(self, files_info: list[dict]) -> str:
        """生成批量提交消息

        Args:
            files_info: 文件信息列表，每个元素包含 {"action": "add"/"rm", "filepath": str, "brief_desc": Optional[str]}
        """
        pass

    def execute(self, action: Literal["add", "rm"],
               filepath: str,
               commit_date: datetime,
               brief_desc: Optional[str] = None,
               skip_stage: bool = False):
        """执行 commit"""
        if filepath.startswith('"') and filepath.endswith('"'):
            filepath = eval(filepath)

        logger.info(f"[{action}] committing {filepath} at {commit_date}")

        git_path = Path(filepath) / ".git"
        if git_path.exists() and git_path.is_dir():
            logger.warning(f"skip git directory: {filepath}")
            return

        # 执行 git 操作（若未标记跳过暂存）
        if not skip_stage:
            if action == "add":
                self.index.add([filepath])
            elif action == "rm":
                self.index.remove([filepath])
            else:
                logger.error(f"unknown action: {action}")
                return

        # 生成提交消息
        message = self.generate_message(action, filepath, brief_desc)
        logger.info(f"commit message: {message}")

        # 提交
        self.index.commit(message, author_date=commit_date, commit_date=commit_date)

    def execute_batch(self, files_info: list[dict], commit_date: datetime):
        """批量执行 commit

        Args:
            files_info: 文件信息列表，每个元素包含 {"action": "add"/"rm", "filepath": str, "brief_desc": Optional[str]}
            commit_date: 提交日期
        """
        if not files_info:
            return

        logger.info(f"[batch] committing {len(files_info)} files at {commit_date}")

        # 执行所有 git 操作
        for info in files_info:
            filepath = info["filepath"]
            action = info["action"]
            skip_stage = info.get("skip_stage", False)

            if filepath.startswith('"') and filepath.endswith('"'):
                filepath = eval(filepath)

            git_path = Path(filepath) / ".git"
            if git_path.exists() and git_path.is_dir():
                logger.warning(f"skip git directory: {filepath}")
                continue

            if not skip_stage:
                if action == "add":
                    self.index.add([filepath])
                elif action == "rm":
                    self.index.remove([filepath])
                else:
                    logger.error(f"unknown action: {action}")
                    continue

        # 生成批量提交消息
        message = self.generate_batch_message(files_info)
        logger.info(f"commit message: {message}")

        # 提交
        self.index.commit(message, author_date=commit_date, commit_date=commit_date)


class SimpleCommit(BaseCommit):
    """简单 Commit，不使用 AI"""

    def generate_message(self, action: Literal["add", "rm"],
                        filepath: str,
                        brief_desc: Optional[str] = None) -> str:
        return f"chore {action} {Path(filepath).name}"

    def generate_batch_message(self, files_info: list[dict]) -> str:
        """生成批量提交消息"""
        file_count = len(files_info)
        actions = set(info["action"] for info in files_info)

        if len(actions) == 1:
            action = actions.pop()
            return f"chore {action} {file_count} files"
        else:
            return f"chore update {file_count} files"


class AICommit(BaseCommit):
    """AI Commit，使用 AI 生成 commit 消息"""

    def __init__(self, index: git.IndexFile, api_key: str, base_url: str, model: str):
        super().__init__(index)
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._client = None

    @property
    def client(self):
        """延迟初始化 OpenAI 客户端"""
        if self._client is None:
            import openai
            self._client = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
        return self._client

    def generate_message(self, action: Literal["add", "rm"],
                        filepath: str,
                        brief_desc: Optional[str] = None) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": f"""\
Please write a brief commit message in one line for action {action} on {filepath}.

Example:
🎉 [{action} {filepath}] xxx
(you can use any emoji)

You MUST directly respond with the commit message without any explanation, starting with the emoji.
""" + ('Diff:\n' + brief_desc if brief_desc else ''),
                    }
                ],
                max_tokens=64,
                n=1,
                temperature=0.5,
                stream=False,
            )
            message = response.choices[0].message.content
            if not message:
                return f"chore {action} {Path(filepath).name}"
            return message
        except Exception as e:
            logger.error(f"AI commit failed: {e}, fallback to simple commit")
            return f"chore {action} {Path(filepath).name}"

    def generate_batch_message(self, files_info: list[dict]) -> str:
        """生成批量提交消息"""
        try:
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

            files_desc = "\n".join(file_list[:10])  # 最多展示10个文件
            if len(file_list) > 10:
                files_desc += f"\n... and {len(file_list) - 10} more files"

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": f"""\
Please write a brief commit message in one line for the following changes:

{files_desc}

Example:
🎉 [update] Add user authentication and database schema
(you can use any emoji)

You MUST directly respond with the commit message without any explanation, starting with the emoji.
""",
                    }
                ],
                max_tokens=128,
                n=1,
                temperature=0.5,
                stream=False,
            )
            message = response.choices[0].message.content
            if not message:
                return f"chore update {len(files_info)} files"
            return message
        except Exception as e:
            logger.error(f"AI batch commit failed: {e}, fallback to simple commit")
            return f"chore update {len(files_info)} files"


# ==================== 原有的工具函数 ====================
commit_client = None


def is_textual_file(file_path: str, chunk_size: int = 2048) -> bool:
    """判断文件是否为文本文件。

    策略：
    - 读取头部少量字节；若含有空字节(\x00)则视为二进制。
    - 允许常见空白控制字符与可打印 ASCII；统计非文本字符比例，超过阈值视为二进制。
    - 对空文件返回 True（当作文本）。
    """
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(chunk_size)
    except Exception:
        # 读取异常时，保守认为非文本，避免后续按文本方式读取
        return False

    if not chunk:
        return True

    # 空字节强指示器：存在则判定为二进制
    if b"\x00" in chunk:
        return False

    # 优先尝试 UTF-8 严格解码：能完整解码即认为是文本（支持中文等非 ASCII）
    try:
        chunk.decode("utf-8", errors="strict")
        return True
    except UnicodeDecodeError:
        pass

    # 回退策略：基于 ASCII 可打印字符比例的启发式判断
    text_chars = set([7, 8, 9, 10, 12, 13, 27]) | set(range(0x20, 0x7F))
    non_text_count = sum(1 for b in chunk if b not in text_chars)
    return (non_text_count / len(chunk)) <= 0.30


def collect_changes(repo: git.Repo):  # 保留旧接口（向后兼容），仍返回合并列表
    data = collect_changes_separated(repo)
    # 合并 staged 与 unstaged，用于旧调用位置（如 ls 命令）
    added = list(dict.fromkeys(data['staged']['added'] + data['unstaged']['added']))
    modified = list(dict.fromkeys(data['staged']['modified'] + data['unstaged']['modified']))
    deleted = list(dict.fromkeys(data['staged']['deleted'] + data['unstaged']['deleted']))
    untracked = data['unstaged']['untracked']
    return added, modified, deleted, untracked


def collect_changes_separated(repo: git.Repo):
    """收集变更并区分 staged 与 unstaged。

    Returns:
        {
          'staged':   {'added': [], 'modified': [], 'deleted': []},
          'unstaged': {'added': [], 'modified': [], 'deleted': [], 'untracked': []}
        }
    """
    staged = {'added': [], 'modified': [], 'deleted': []}
    unstaged = {'added': [], 'modified': [], 'deleted': [], 'untracked': []}

    # 使用 GitPython 的结构化 diff：
    # repo.index.diff(None)        -> 工作区(未暂存) 与 index 差异 (unstaged changes)
    # repo.index.diff(repo.head.commit) -> index 与 HEAD 差异 (staged changes)

    try:
        diff_unstaged = repo.index.diff(None)
    except Exception as e:
        logger.warning(f"读取未暂存 diff 失败: {e}")
        diff_unstaged = []
    try:
        # 与 HEAD 的差异即为已暂存变更（使用 INDEX 对比 HEAD，b_path 指向索引中的新路径）
        diff_staged = repo.index.diff(repo.head.commit)
    except Exception as e:
        logger.warning(f"读取暂存区 diff 失败: {e}")
        diff_staged = []

    def _classify(diff_entry, bucket: dict, kind: str):
        ct = diff_entry.change_type
        # 优先使用 b_path（新路径），退回 a_path（旧路径）
        new_path = getattr(diff_entry, 'b_path', None) or diff_entry.a_path
        old_path = diff_entry.a_path
        if ct == 'A':
            bucket['added'].append(new_path)
        elif ct == 'M':
            bucket['modified'].append(new_path)
        elif ct == 'D':
            fs_path = Path(repo.working_tree_dir) / (old_path or new_path)
            if kind == 'unstaged':
                if fs_path.exists():
                    bucket['modified'].append(new_path or old_path)
                    logger.debug(f"{kind} diff D 但文件存在，视为修改: {new_path or old_path}")
                else:
                    bucket['deleted'].append(old_path or new_path)
            else:  # staged
                # 在 index.diff(HEAD) 时，新增文件可能表现为 D（index 有/HEAD 无）。若文件存在，则归为 added
                if fs_path.exists():
                    bucket['added'].append(new_path or old_path)
                    logger.debug(f"staged diff D 但文件存在，视为新增: {new_path or old_path}")
                else:
                    bucket['deleted'].append(old_path or new_path)
        elif ct == 'R':
            bucket['modified'].append(new_path)
        else:
            bucket['modified'].append(new_path)
            logger.debug(f"{kind} diff 未识别类型 {ct} -> 视为修改: {new_path}")

    for d in diff_staged:
        _classify(d, staged, 'staged')
    for d in diff_unstaged:
        _classify(d, unstaged, 'unstaged')

    # 未跟踪文件
    try:
        unstaged['untracked'].extend(repo.untracked_files)
    except Exception as e:
        logger.warning(f"获取未跟踪文件失败: {e}")

    # 去重保持顺序
    def _dedup(seq: list[str]) -> list[str]:
        return list(dict.fromkeys(seq))
    for k in staged:
        staged[k] = _dedup(staged[k])
    for k in unstaged:
        if k != 'untracked':
            unstaged[k] = _dedup(unstaged[k])
    unstaged['untracked'] = _dedup(unstaged['untracked'])

    return {'staged': staged, 'unstaged': unstaged}


def _auto_push_if_enabled(repo: git.Repo, enabled: bool):
    """若开启自动推送，则将当前分支推送到 origin 同名分支。"""
    if not enabled:
        return
    try:
        # 当前分支名
        try:
            branch = repo.active_branch.name
        except Exception:
            logger.warning("当前处于 detached HEAD 状态，跳过自动推送。")
            return

        # 远程 origin 检查
        remote_names = [r.name for r in repo.remotes]
        if "origin" not in remote_names:
            logger.warning("未发现名为 origin 的远程仓库，跳过自动推送。")
            return

        logger.info(f"开始自动推送: git push origin {branch}")
        # 使用 GitPython 执行 push
        repo.git.push("origin", branch)
        logger.info("自动推送完成 ✅")
    except Exception as e:
        logger.error(f"自动推送失败: {e}")


def print_changes_numbered(
    added_files: list[str],
    modified_files: list[str],
    deleted_files: list[str],
    untracked_files: list[str],
):
    """彩色输出变更，并为每个文件从 1 开始编号"""
    idx = 1
    any_changes = False

    def echo_header(text: str, color):
        typer.secho(text, fg=color, bold=True)

    def echo_line(prefix: str, file: str, color):
        nonlocal idx
        typer.secho(f"{prefix} [{idx:>3}] {file}", fg=color)
        idx += 1

    if untracked_files:
        any_changes = True
        echo_header("Untracked Files:", colors.YELLOW)
        for f in untracked_files:
            echo_line("?", f, colors.YELLOW)

    if added_files:
        any_changes = True
        echo_header("Added Files:", colors.GREEN)
        for f in added_files:
            echo_line("+", f, colors.GREEN)

    if modified_files:
        any_changes = True
        echo_header("Modified Files:", colors.CYAN)
        for f in modified_files:
            echo_line("o", f, colors.CYAN)

    if deleted_files:
        any_changes = True
        echo_header("Deleted Files:", colors.RED)
        for f in deleted_files:
            echo_line("-", f, colors.RED)

    if not any_changes:
        typer.secho("No changes in working directory.", fg=colors.BRIGHT_BLACK)


def _filter_changes_by_path(
    repo_root: Path,
    target_path: str,
    added_files: list[str],
    modified_files: list[str],
    deleted_files: list[str],
    untracked_files: list[str],
    base_dir: Optional[Path] = None,
):
    """按给定路径过滤变更（文件精确匹配；目录为前缀匹配）"""
    # 规范化路径并转换为相对仓库根目录的 POSIX 路径
    root = repo_root.resolve()
    base = (base_dir or Path.cwd()).resolve()
    in_path = Path(target_path)
    if not in_path.is_absolute():
        in_path = (base / in_path).resolve(strict=False)
    else:
        in_path = in_path.resolve(strict=False)

    try:
        rel = in_path.relative_to(root)
        rel_posix = rel.as_posix()
    except Exception:
        # 不在仓库内，退化使用原始字符串进行包含判断
        rel_posix = Path(target_path).as_posix()

    # 判断目录：优先以真实目录为准；若不存在则依据输入末尾斜杠判断
    is_dir = in_path.is_dir() or target_path.endswith(("/", "\\"))

    def match(p: str) -> bool:
        if is_dir:
            return p == rel_posix or p.startswith(rel_posix.rstrip("/") + "/")
        else:
            return p == rel_posix

    f_added = [p for p in added_files if match(p)]
    f_modified = [p for p in modified_files if match(p)]
    f_deleted = [p for p in deleted_files if match(p)]
    f_untracked = [p for p in untracked_files if match(p)]
    return f_added, f_modified, f_deleted, f_untracked


def get_brief_desc(index: git.IndexFile, action: Literal["add", "rm"], filepath: str) -> Optional[str]:
    """获取文件的简要描述（用于 AI commit）

    注意：
    - 对于二进制文件（如图片、压缩包），不读取内容，返回 None，让上层只传文件名给 AI。
    - 文本读取使用 UTF-8 并忽略无法解码的字符，避免 UnicodeDecodeError。
    """
    brief_desc_for_file: Optional[str] = None

    if action == "add":
        # 优先尝试 diff（适用于已被索引跟踪的改动）
        try:
            diff = index.diff(None, paths=filepath, create_patch=True)
        except Exception:
            diff = []

        if len(diff) > 0:
            d = diff.pop()
            if getattr(d, 'diff', None):
                content = d.diff
                if isinstance(content, bytes):
                    try:
                        content = content.decode("utf-8", errors="ignore")
                    except Exception:
                        content = None
                brief_desc_for_file = content
                if brief_desc_for_file:
                    logger.debug(f"\n{brief_desc_for_file}")
        else:
            # 未有 diff 时，对小文本文件读取部分内容
            path = Path(filepath)
            if path.is_file() and path.stat().st_size < 10_000_000:  # 10MB 以下
                if is_textual_file(filepath):
                    try:
                        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                            brief_desc_for_file = f.read(2048)
                    except Exception:
                        brief_desc_for_file = None
                else:
                    # 二进制文件：不读取内容，由调用者仅传文件名
                    brief_desc_for_file = None

        if brief_desc_for_file and len(brief_desc_for_file) > 1024:
            brief_desc_for_file = brief_desc_for_file[:1024]

    return brief_desc_for_file


def create_committer(index: git.IndexFile, config: dict) -> BaseCommit:
    """根据配置创建对应的 Committer"""
    if config.get("api_key"):
        return AICommit(
            index=index,
            api_key=config["api_key"],
            base_url=config["base_url"],
            model=config["model"]
        )
    else:
        return SimpleCommit(index=index)


def commit_file(
    committer: BaseCommit,
    action: Literal["add", "rm"],
    filepath: str,
    commit_date: datetime,
    brief_desc: Optional[str] = None,
    skip_stage: bool = False,
):
    """执行单个文件的提交"""
    committer.execute(action, filepath, commit_date, brief_desc, skip_stage=skip_stage)


def get_commit_dates(start_date: datetime, end_date: datetime, count) -> list[datetime]:
    if end_date < start_date:
        commit_dates = []
        # 1秒提交一个
        for i in range(count):
            commit_dates.append(start_date + timedelta(seconds=i))
        return commit_dates
        # raise ValueError("end_date must be greater than start_date")
    delta = end_date - start_date
    # millis = delta.total_seconds() * 1000
    if delta.days <= 0:
        # 今天已有提交
        commit_dates = []
        for i in range(count):
            delta_i = delta * (i + 1) / (count + 1)
            commit_dates.append(start_date + delta_i)
        return commit_dates
    elif count <= 0:
        # 没有文件需要提交
        return []
    elif count == 1:
        # 只有一个文件需要提交
        return [start_date + delta / 2]
    elif delta.days < count:
        # 均匀提交
        # 由于容斥原理，每天至少有一个文件提交
        commit_dates = []
        for i in range(count):
            delta_i = delta * (i + 1) / (count + 1)
            commit_dates.append(start_date + delta_i)
        return commit_dates
    else:
        # 待提交文件数小于天数，优先在最早的日期提交
        commit_dates = []
        for i in range(count):
            commit_dates.append(start_date + timedelta(days=i))
        return commit_dates


@cli.command(
    short_help="自动填写 commit 信息提交代码",
    help="自动填写 commit 信息提交代码",
)
def main(
    repo_dir: Annotated[str, typer.Option(help="git 仓库目录")] = ".",
    ls: Annotated[bool, typer.Option("--ls", help="列出当前工作区变更并编号")] = False,
    one_commit: Annotated[bool, typer.Option("-m", "--one-commit", help="将所有文件合并为一个 commit")] = False,
    staging: Annotated[bool, typer.Option("--staging/--no-staging", help="是否自动将未暂存变更加入暂存区",)] = True,
    ai: Annotated[Optional[bool], typer.Option("--ai/--no-ai", help="是否使用 AI 填写 commit 信息")] = None,
    api_key: Annotated[str, typer.Option(help="OpenAI API Key")] = None,
    base_url: Annotated[str, typer.Option(help="OpenAI API URL")] = "https://api.deepseek.com",
    model: Annotated[str, typer.Option(help="OpenAI Model")] = "deepseek-chat",
):
    resolved_repo_dir, _ = resolve_repo_directory(repo_dir)
    original_repo_dir = Path(repo_dir).resolve()
    if original_repo_dir != resolved_repo_dir:
        logger.info(f"repo_dir: {resolved_repo_dir} (from {original_repo_dir})")
    else:
        logger.info(f"repo_dir: {resolved_repo_dir}")
    repo = git.Repo(resolved_repo_dir)
    index: git.IndexFile = repo.index

    # 分离获取变更
    sep = collect_changes_separated(repo)
    staged = sep['staged']
    unstaged = sep['unstaged']

    # 合并供展示
    added_files = list(dict.fromkeys(staged['added'] + unstaged['added']))
    modified_files = list(dict.fromkeys(staged['modified'] + unstaged['modified']))
    deleted_files = list(dict.fromkeys(staged['deleted'] + unstaged['deleted']))
    untracked_files = list(dict.fromkeys(unstaged['untracked']))

    # 只列出变更则直接打印并退出
    if ls:
        print_changes_numbered(added_files, modified_files, deleted_files, untracked_files)
        return
    # print(added_files)
    # print(modified_files)
    # print(deleted_files)
    # print(untracked_files)

    # 使用git status，统计新增、修改、删除的文件
    # status = repo.git.status(porcelain=True)
    # added_files = []
    # modified_files = []
    # deleted_files = []
    # untracked_files = []

    # for line in status.splitlines():
    #     status_code, file_path = line[:2].strip(), line[3:].strip()
    #     if status_code == "??":
    #         untracked_files.append(file_path)
    #     elif status_code == "A":
    #         added_files.append(file_path)
    #     elif status_code == "M":
    #         modified_files.append(file_path)
    #     elif status_code == "D":
    #         deleted_files.append(file_path)
    #     else:
    #         logger.warning(f"unknown status code: {status_code}")

    # 真实提交文件数取决于 staging 策略
    if staging:
        files_count = (len(staged['added']) + len(staged['modified']) + len(staged['deleted']) +
                       len(unstaged['added']) + len(unstaged['modified']) + len(unstaged['deleted']) + len(unstaged['untracked']))
    else:
        files_count = (len(staged['added']) + len(staged['modified']) + len(staged['deleted']))
    # 获取最新的提交日期
    latest_commit_date = repo.head.commit.committed_datetime
    today = datetime.now(latest_commit_date.tzinfo)
    # 从 git log 最新日期到今天，获取所有文件修改信息，随机铺满每一天，使得提交记录完整
    commit_dates = get_commit_dates(latest_commit_date, today, files_count)
    # 按早到晚的顺序提交
    commit_dates.sort()

    # 输出统计结果
    logger.info(f"latest commit date: {latest_commit_date}")
    logger.info(f"today: {today}")
    logger.info(
        f"commit days: {len(commit_dates)} "
        f"({'<' if files_count < len(commit_dates) else '>='}{files_count} files)"
    )
    # 继续保留原有日志输出，便于调试
    msgs = []
    if len(untracked_files) > 0:
        msgs.append("Untracked Files:")
        msgs.extend([f"? {f}" for f in untracked_files])
    if len(added_files) > 0:
        msgs.append("Added Files:")
        msgs.extend([f"+ {f}" for f in added_files])
    if len(modified_files) > 0:
        msgs.append("Modified Files:")
        msgs.extend([f"o {f}" for f in modified_files])
    if len(deleted_files) > 0:
        msgs.append("Deleted Files:")
        msgs.extend([f"- {f}" for f in deleted_files])
    if msgs:
        logger.info("\n" + "\n".join(msgs))

    commit_dates = commit_dates[::-1]

    # 获取配置并创建 committer（--ai 显式覆盖配置逻辑）
    config = ConfigManager.get_config(api_key, base_url, model)
    if ai is True:
        if not config.get("api_key"):
            typer.secho("已指定 --ai，但未检测到 API Key。请通过以下任一方式设置:", fg=colors.RED)
            typer.secho("  1) gcli config --api-key YOUR_KEY", fg=colors.YELLOW)
            typer.secho("  2) 在 .env 设置 GITAGENT_API_KEY", fg=colors.YELLOW)
            typer.secho("  3) 通过 --api-key 传参", fg=colors.YELLOW)
            raise typer.Exit(code=1)
        committer = AICommit(index=index, api_key=config["api_key"], base_url=config["base_url"], model=config["model"])
    elif ai is False:
        committer = SimpleCommit(index=index)
    else:
        committer = create_committer(index, config)

    # 根据 staging 策略确定需要提交的文件集合
    commit_added = []
    commit_modified = []
    commit_deleted = []
    commit_untracked = []

    if staging:
        # 先暂存所有未暂存变更（保留 diff 内容用于 AI）
        logger.info("staging 未暂存变更 ...")
        # 生成描述后暂存
        for path in unstaged['added'] + unstaged['modified']:
            # 描述用于后续 AI，暂存动作在 batch/execute 中处理，这里不提前 add 以便 diff 可见
            pass
        # 删除文件直接 stage 删除
        for path in unstaged['deleted']:
            pass  # 删除的 diff 不用于 AI
        # untracked 文件
        for path in unstaged['untracked']:
            pass
        # 合并所有（提交时执行暂存动作）
        commit_added = staged['added'] + unstaged['added'] + unstaged['modified'] + unstaged['untracked']
        # modified 与 added 都统一 action=add 逻辑
        commit_modified = []  # 已并入 commit_added
        commit_deleted = staged['deleted'] + unstaged['deleted']
    else:
        # 仅提交已经暂存的变更
        commit_added = staged['added'] + staged['modified']
        commit_deleted = staged['deleted']
        if not (commit_added or commit_deleted):
            typer.secho("无已暂存变更。使用 --staging 以自动暂存并提交。", fg=colors.BRIGHT_BLACK)
            return

    # 批量提交模式（one commit）
    if one_commit:
        files_info = []
        # added (含 modified/untracked 合并) -> action add
        for item in commit_added:
            brief_desc = get_brief_desc(index, "add", item) if isinstance(committer, AICommit) else None
            # 若该文件原本已 staged，跳过再次暂存
            skip_stage = (item in staged['added'] or item in staged['modified']) and staging
            files_info.append({"action": "add", "filepath": item, "brief_desc": brief_desc, "skip_stage": skip_stage})
        for item in commit_deleted:
            skip_stage = (item in staged['deleted']) and staging
            files_info.append({"action": "rm", "filepath": item, "brief_desc": None, "skip_stage": skip_stage})

        if commit_dates:
            commit_date = commit_dates[-1]
        else:
            commit_date = datetime.now(latest_commit_date.tzinfo)
        logger.info(f"commit_date: {commit_date}")
        committer.execute_batch(files_info, commit_date)
    else:
        # 单文件提交模式（时间分布）
        to_commit = [("add", f) for f in commit_added] + [("rm", f) for f in commit_deleted]
        # 逆序日期列表与数量可能不匹配，防御
        for action, path in to_commit:
            if not commit_dates:
                cd = datetime.now(latest_commit_date.tzinfo)
            else:
                cd = commit_dates.pop()
            brief_desc = None
            if action == "add" and isinstance(committer, AICommit):
                brief_desc = get_brief_desc(index, "add", path)
            skip_stage = staging and ((path in staged['added']) or (path in staged['modified']) or (path in staged['deleted']))
            commit_file(committer, action, path, cd, brief_desc, skip_stage=skip_stage)

    # 自动推送（若开启）
    _auto_push_if_enabled(repo, config.get("auto_push", False))

    logger.info("Everything done!")


@cli.command("ls", help="列出当前工作区变更并编号（彩色输出）")
def ls_cmd(
    repo_dir: Annotated[str, typer.Option(help="git 仓库目录")] = ".",
):
    resolved_repo_dir, _ = resolve_repo_directory(repo_dir)
    original_repo_dir = Path(repo_dir).resolve()
    if original_repo_dir != resolved_repo_dir:
        logger.info(f"repo_dir: {resolved_repo_dir} (from {original_repo_dir})")
    repo = git.Repo(resolved_repo_dir)
    added_files, modified_files, deleted_files, untracked_files = collect_changes(repo)
    print_changes_numbered(added_files, modified_files, deleted_files, untracked_files)


@cli.command("only", help="仅提交指定文件或目录下的变更（支持多个路径）")
def only_cmd(
    targets: Annotated[list[str], typer.Argument(help="一个或多个目标文件或目录路径，相对或绝对均可", metavar="TARGET...")],
    repo_dir: Annotated[str, typer.Option(help="git 仓库目录")] = ".",
    one_commit: Annotated[bool, typer.Option("-m", "--one-commit", help="将所有文件合并为一个 commit")] = False,
    staging: Annotated[bool, typer.Option("--staging/--no-staging", help="是否自动将未暂存变更加入暂存区",)] = True,
    ai: Annotated[Optional[bool], typer.Option("--ai/--no-ai", help="是否使用 AI 填写 commit 信息")] = None,
    api_key: Annotated[str, typer.Option(help="OpenAI API Key")] = None,
    base_url: Annotated[str, typer.Option(help="OpenAI API URL")] = "https://api.deepseek.com",
    model: Annotated[str, typer.Option(help="OpenAI Model")] = "deepseek-chat",
):
    resolved_repo_dir, user_cwd = resolve_repo_directory(repo_dir)
    original_repo_dir = Path(repo_dir).resolve()
    if original_repo_dir != resolved_repo_dir:
        logger.info(f"repo_dir: {resolved_repo_dir} (from {original_repo_dir})")
    repo = git.Repo(resolved_repo_dir)
    index: git.IndexFile = repo.index
    repo_root = Path(repo.working_tree_dir)
    root_path = repo_root.resolve()
    base_dir = user_cwd

    sep = collect_changes_separated(repo)
    staged = sep['staged']
    unstaged = sep['unstaged']

    # 基于路径过滤分别处理
    def _flt(lst: list[str], target: str) -> list[str]:
        in_path = Path(target)
        if not in_path.is_absolute():
            in_path = (base_dir / in_path).resolve(strict=False)
        else:
            in_path = in_path.resolve(strict=False)
        try:
            rel = in_path.relative_to(root_path).as_posix()
        except Exception:
            rel = Path(target).as_posix()
        is_dir = in_path.is_dir() or target.endswith(("/", "\\"))
        out = []
        for p in lst:
            if is_dir:
                if p == rel or p.startswith(rel.rstrip('/') + '/'):
                    out.append(p)
            else:
                if p == rel:
                    out.append(p)
        return out

    agg = {k: [] for k in ['staged_added','staged_modified','staged_deleted','unstaged_added','unstaged_modified','unstaged_deleted','unstaged_untracked']}
    for t in targets:
        agg['staged_added'] += _flt(staged['added'], t)
        agg['staged_modified'] += _flt(staged['modified'], t)
        agg['staged_deleted'] += _flt(staged['deleted'], t)
        agg['unstaged_added'] += _flt(unstaged['added'], t)
        agg['unstaged_modified'] += _flt(unstaged['modified'], t)
        agg['unstaged_deleted'] += _flt(unstaged['deleted'], t)
        agg['unstaged_untracked'] += _flt(unstaged['untracked'], t)

    def _dedup(seq: list[str]) -> list[str]:
        return list(dict.fromkeys(seq))

    for k in agg:
        agg[k] = _dedup(agg[k])

    # 展示使用合并视图
    added_files = agg['staged_added'] + agg['unstaged_added'] + agg['unstaged_modified']
    modified_files = []  # 已并入 added_files
    deleted_files = agg['staged_deleted'] + agg['unstaged_deleted']
    untracked_files = agg['unstaged_untracked']
    # 参数校验
    if not targets:
        typer.secho("未提供任何目标路径。", fg=colors.RED)
        return

    # 过滤：支持多个目标，聚合并去重（保留首次出现顺序）
    agg_added: list[str] = []
    agg_modified: list[str] = []
    agg_deleted: list[str] = []
    agg_untracked: list[str] = []

    for target in targets:
        fa, fm, fd, fu = _filter_changes_by_path(
            repo_root, target, added_files, modified_files, deleted_files, untracked_files, base_dir=base_dir
        )
        agg_added.extend(fa)
        agg_modified.extend(fm)
        agg_deleted.extend(fd)
        agg_untracked.extend(fu)

    def _dedup_preserve(items: list[str]) -> list[str]:
        seen = set()
        out = []
        for x in items:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    added_files = _dedup_preserve(agg_added)
    modified_files = _dedup_preserve(agg_modified)
    deleted_files = _dedup_preserve(agg_deleted)
    untracked_files = _dedup_preserve(agg_untracked)

    if not (added_files or modified_files or deleted_files or untracked_files):
        typer.secho("目标路径下无待提交变更。", fg=colors.BRIGHT_BLACK)
        return

    # 输出彩色列表
    print_changes_numbered(added_files, modified_files, deleted_files, untracked_files)

    if staging:
        files_count = (len(added_files) + len(deleted_files) + len(untracked_files))
    else:
        files_count = (len(agg['staged_added']) + len(agg['staged_modified']) + len(agg['staged_deleted']))
    latest_commit_date = repo.head.commit.committed_datetime
    today = datetime.now(latest_commit_date.tzinfo)
    commit_dates = get_commit_dates(latest_commit_date, today, files_count)
    commit_dates.sort()
    commit_dates = commit_dates[::-1]

    # 获取配置并创建 committer（--ai 显式覆盖配置逻辑）
    config = ConfigManager.get_config(api_key, base_url, model)
    if ai is True:
        if not config.get("api_key"):
            typer.secho("已指定 --ai，但未检测到 API Key。请通过以下任一方式设置:", fg=colors.RED)
            typer.secho("  1) gcli config --api-key YOUR_KEY", fg=colors.YELLOW)
            typer.secho("  2) 在 .env 设置 GITAGENT_API_KEY", fg=colors.YELLOW)
            typer.secho("  3) 通过 --api-key 传参", fg=colors.YELLOW)
            raise typer.Exit(code=1)
        committer = AICommit(index=index, api_key=config["api_key"], base_url=config["base_url"], model=config["model"])
    elif ai is False:
        committer = SimpleCommit(index=index)
    else:
        committer = create_committer(index, config)

    # 构造提交集合
    if staging:
        commit_added = added_files + untracked_files  # modified 已合并入 added_files
        commit_deleted = deleted_files
    else:
        commit_added = agg['staged_added'] + agg['staged_modified']
        commit_deleted = agg['staged_deleted']
        if not (commit_added or commit_deleted):
            typer.secho("目标路径下无已暂存变更。使用 --staging 以自动暂存。", fg=colors.BRIGHT_BLACK)
            return

    if one_commit:
        files_info = []
        for item in commit_added:
            brief_desc = get_brief_desc(index, "add", item) if isinstance(committer, AICommit) else None
            skip_stage = staging and (item in agg['staged_added'] or item in agg['staged_modified'])
            files_info.append({"action": "add", "filepath": item, "brief_desc": brief_desc, "skip_stage": skip_stage})
        for item in commit_deleted:
            skip_stage = staging and (item in agg['staged_deleted'])
            files_info.append({"action": "rm", "filepath": item, "brief_desc": None, "skip_stage": skip_stage})

        if commit_dates:
            commit_date = commit_dates[-1]
        else:
            latest_commit_date = repo.head.commit.committed_datetime
            commit_date = datetime.now(latest_commit_date.tzinfo)
        logger.info(f"commit_date: {commit_date}")
        committer.execute_batch(files_info, commit_date)
    else:
        to_commit = [("add", f) for f in commit_added] + [("rm", f) for f in commit_deleted]
        for action, path in to_commit:
            if not commit_dates:
                cd = datetime.now(repo.head.commit.committed_datetime.tzinfo)
            else:
                cd = commit_dates.pop()
            brief_desc = None
            if action == "add" and isinstance(committer, AICommit):
                brief_desc = get_brief_desc(index, "add", path)
            skip_stage = staging and ((path in agg['staged_added']) or (path in agg['staged_modified']) or (path in agg['staged_deleted']))
            commit_file(committer, action, path, cd, brief_desc, skip_stage=skip_stage)

    # 自动推送（若开启）
    _auto_push_if_enabled(repo, config.get("auto_push", False))

    logger.info("Selected changes committed. ✅")


@cli.command("config", help="配置 AI commit 参数（API Key、Base URL、Model）")
def config_cmd(
    api_key: Annotated[Optional[str], typer.Option("-k", "--api-key", help="OpenAI API Key")] = None,
    base_url: Annotated[Optional[str], typer.Option("-u", "--base-url", help="OpenAI API URL")] = None,
    model: Annotated[Optional[str], typer.Option("-m", "--model", help="OpenAI Model")] = None,
    auto_push: Annotated[Optional[bool], typer.Option("--auto-push/--no-auto-push", help="是否在提交后自动执行 git push origin <当前分支>")] = None,
    global_config: Annotated[bool, typer.Option("-g", "--global", help="保存到全局配置")] = False,
    show: Annotated[bool, typer.Option("--show", help="显示当前配置")] = False,
):
    """配置管理命令"""
    if show:
        # 显示当前配置
        config = ConfigManager.get_config()
        typer.secho("当前配置:", fg=colors.BRIGHT_BLUE, bold=True)
        typer.secho(f"  API Key: {config.get('api_key', 'N/A')}", fg=colors.CYAN)
        typer.secho(f"  Base URL: {config.get('base_url', 'N/A')}", fg=colors.CYAN)
        typer.secho(f"  Model: {config.get('model', 'N/A')}", fg=colors.CYAN)
        typer.secho(f"  Auto Push: {config.get('auto_push', False)}", fg=colors.CYAN)
        return

    if not any([api_key, base_url, model, auto_push is not None]):
        typer.secho("请至少提供一个配置项: --api-key, --base-url, 或 --model", fg=colors.RED)
        typer.secho("或使用 --show 查看当前配置", fg=colors.YELLOW)
        return

    # 保存配置
    ConfigManager.save_config(
        api_key=api_key,
        base_url=base_url,
        model=model,
        auto_push=auto_push,
        global_config=global_config
    )

    scope = "全局" if global_config else "本地"
    typer.secho(f"✅ 配置已保存到{scope}配置", fg=colors.GREEN)


@cli.command("test-api", help="测试 AI Committer 是否能正常连接并返回响应")
def test_api_cmd(
    api_key: Annotated[Optional[str], typer.Option("-k", "--api-key", help="OpenAI API Key")] = None,
    base_url: Annotated[Optional[str], typer.Option("-u", "--base-url", help="OpenAI API URL")] = None,
    model: Annotated[Optional[str], typer.Option("-m", "--model", help="OpenAI Model")] = None,
    instruction: Annotated[Optional[str], typer.Option("-i", "--instruction", help="用于测试的提示词/指令内容")] = None,
    timeout: Annotated[int, typer.Option(help="请求超时时间（秒）", min=1)] = 20,
    verbose: Annotated[bool, typer.Option("-v", "--verbose", help="显示更多调试信息")] = False,
):
    """尝试调用一次最小聊天补全以验证 API 连通性。

    优先级：命令行参数 > ./.oh-my-git-agent/config > .env > ~/.oh-my-git-agent/config
    """
    # 组装配置
    config = ConfigManager.get_config(cli_api_key=api_key, cli_base_url=base_url, cli_model=model)
    resolved_key = config.get("api_key")
    resolved_url = config.get("base_url")
    resolved_model = config.get("model")

    if verbose:
        typer.secho("使用配置:", fg=colors.BRIGHT_BLUE, bold=True)
        typer.secho(f"  base_url: {resolved_url}", fg=colors.CYAN)
        typer.secho(f"  model:    {resolved_model}", fg=colors.CYAN)
        typer.secho(f"  api_key:  {'已提供' if resolved_key else '未提供'}", fg=colors.CYAN)

    if not resolved_key:
        typer.secho("未检测到 API Key。请通过以下任一方式设置:", fg=colors.RED)
        typer.secho("  1) gcli config --api-key YOUR_KEY", fg=colors.YELLOW)
        typer.secho("  2) 在 .env 设置 GITAGENT_API_KEY", fg=colors.YELLOW)
        typer.secho("  3) 通过 --api-key 传参", fg=colors.YELLOW)
        raise typer.Exit(code=1)

    try:
        import openai

        # 设置请求超时：openai>=1.0 支持在客户端构造时传入超时
        client = openai.OpenAI(api_key=resolved_key, base_url=resolved_url, timeout=timeout)

        start = time.time()
        # 若未提供 instruction，使用默认最小回声提示
        prompt = instruction.strip() if instruction else "Reply with a single word: pong"

        resp = client.chat.completions.create(
            model=resolved_model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=8,
            temperature=0,
            n=1,
            stream=False,
        )
        elapsed_ms = int((time.time() - start) * 1000)
        typer.secho(f"Response: {resp}", fg=colors.BRIGHT_BLACK) if verbose else None

        content = (resp.choices[0].message.content or "").strip()
        typer.secho(
            f"✅ AI API 连接成功 | {elapsed_ms}ms\n  base_url: {resolved_url}\n  model:    {resolved_model}\n  prompt:   {prompt}\n  reply:    {content}",
            fg=colors.GREEN,
        )
    except ImportError:
        typer.secho("未找到 openai 库，请先安装依赖: pip install openai", fg=colors.RED)
    except Exception as e:
        typer.secho("❌ AI API 连通性测试失败", fg=colors.RED, bold=True)
        typer.secho(f"  base_url: {resolved_url}", fg=colors.BRIGHT_BLACK)
        typer.secho(f"  model:    {resolved_model}", fg=colors.BRIGHT_BLACK)
        typer.secho(f"  错误信息: {e}", fg=colors.YELLOW)
        typer.secho("请检查: API Key 是否有效、Base URL 是否正确、模型名称是否可用以及网络连通性。", fg=colors.BRIGHT_BLACK)


def cli_wrapper():
    """包装器：当不提供子命令时，默认执行 main 命令"""
    import sys

    # 获取命令行参数
    args = sys.argv[1:]

    # 如果没有参数，或第一个参数是选项（以 - 开头），则默认执行 main
    if not args or (args[0].startswith('-') and args[0] not in ['--help', '-h']):
        # 在参数开头插入 'main'
        sys.argv.insert(1, 'main')

    cli()


# ==================== 版本信息 ====================
def _read_version_from_pyproject(pyproject_path: Path) -> Optional[str]:
    """从给定 pyproject.toml 路径解析版本号。

    解析顺序：
    1) 使用 tomllib/tomli 严格解析
    2) 回退到正则匹配 [tool.poetry] 下的 version 字段
    """
    try:
        if pyproject_path.exists():
            try:
                # Python 3.11+
                import tomllib  # type: ignore
                data = tomllib.loads(pyproject_path.read_bytes())
                v = (
                    data.get('tool', {})
                    .get('poetry', {})
                    .get('version')
                )
                if isinstance(v, str) and v.strip():
                    return v.strip()
            except ImportError:
                try:
                    import tomli  # type: ignore
                    data = tomli.loads(pyproject_path.read_text(encoding='utf-8'))
                    v = (
                        data.get('tool', {})
                        .get('poetry', {})
                        .get('version')
                    )
                    if isinstance(v, str) and v.strip():
                        return v.strip()
                except Exception:
                    pass
            except Exception:
                # toml 解析失败时回退到正则
                pass

            # 简单正则回退：优先匹配 [tool.poetry] 区块内的 version
            try:
                import re
                text = pyproject_path.read_text(encoding='utf-8', errors='ignore')
                # 限定在 [tool.poetry] 段落中查找 version
                m_block = re.search(r"\[tool\.poetry\](.*?)(\n\[|\Z)", text, re.S)
                scope = m_block.group(1) if m_block else text
                m = re.search(r"^\s*version\s*=\s*['\"]([^'\"]+)['\"]\s*$", scope, re.M)
                if m:
                    return m.group(1).strip()
            except Exception:
                pass
    except Exception:
        pass
    return None


def get_version() -> str:
    """获取当前程序版本号。

    优先从已安装分发中读取；若不可用，则尝试读取工程根目录的 pyproject.toml；再退回到脚本同级目录。
    """
    # 1) 已安装环境（更稳健）
    try:
        try:
            from importlib import metadata as _ilm  # py3.8+
        except Exception:
            import importlib_metadata as _ilm  # type: ignore
        v = _ilm.version("oh-my-git-agent")
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception:
        pass

    # 2) 尝试工程根目录（当前工作目录）
    cwd_pyproject = Path.cwd() / "pyproject.toml"
    v = _read_version_from_pyproject(cwd_pyproject)
    if v:
        return v

    # 3) 脚本所在目录（开发场景）
    here_pyproject = Path(__file__).resolve().parent / "pyproject.toml"
    v = _read_version_from_pyproject(here_pyproject)
    if v:
        return v

    # 4) 回退默认
    return "0.0.0"


@cli.command("version", help="显示版本信息")
def version_cmd(
    short: Annotated[bool, typer.Option("--short", help="仅输出纯版本号，不带名称")] = False,
):
    v = get_version()
    if short:
        typer.echo(v)
    else:
        typer.secho(f"oh-my-git-agent v{v}", fg=colors.BRIGHT_BLUE, bold=True)


if __name__ == "__main__":
    cli_wrapper()
