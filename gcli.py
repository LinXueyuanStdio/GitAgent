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
            "model": "deepseek-chat"
        }

        # 1. 全局配置
        if cls.GLOBAL_CONFIG_FILE.exists():
            with open(cls.GLOBAL_CONFIG_FILE, 'r', encoding='utf-8') as f:
                global_config = yaml.safe_load(f) or {}
                config.update(global_config)

        # 2. 本地 .env 文件
        if cls.LOCAL_ENV_FILE.exists():
            load_dotenv(cls.LOCAL_ENV_FILE)
            if os.getenv("OPENAI_API_KEY"):
                config["api_key"] = os.getenv("OPENAI_API_KEY")
            if os.getenv("OPENAI_BASE_URL"):
                config["base_url"] = os.getenv("OPENAI_BASE_URL")
            if os.getenv("OPENAI_MODEL"):
                config["model"] = os.getenv("OPENAI_MODEL")

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

        # 写入配置
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.safe_dump(existing_config, f, allow_unicode=True)

        scope = "全局" if global_config else "本地"
        logger.info(f"配置已保存到{scope}配置文件: {config_file}")


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

    def execute(self, action: Literal["add", "rm"],
               filepath: str,
               commit_date: datetime,
               brief_desc: Optional[str] = None):
        """执行 commit"""
        if filepath.startswith('"') and filepath.endswith('"'):
            filepath = eval(filepath)

        logger.info(f"[{action}] committing {filepath} at {commit_date}")

        git_path = Path(filepath) / ".git"
        if git_path.exists() and git_path.is_dir():
            logger.warning(f"skip git directory: {filepath}")
            return

        # 执行 git 操作
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


class SimpleCommit(BaseCommit):
    """简单 Commit，不使用 AI"""

    def generate_message(self, action: Literal["add", "rm"],
                        filepath: str,
                        brief_desc: Optional[str] = None) -> str:
        return f"chore {action} {Path(filepath).name}"


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


# ==================== 原有的工具函数 ====================
commit_client = None


def is_textual_file(file_path, chunk_size=1024):
    """通过检查文件内容是否包含空字节或大量非ASCII字符来判断"""
    with open(file_path, 'rb') as f:
        chunk = f.read(chunk_size)
        # 空字节是二进制文件的强指示器
        if b'\x00' in chunk:
            return True
        # 检查非文本字符的比例
        text_chars = bytearray({7,8,9,10,12,13,27} | set(range(0x20, 0x100)) - {0x7f})
        non_text = chunk.translate(None, text_chars)
        return len(non_text) / len(chunk) <= 0.3 if chunk else True


def collect_changes(repo: git.Repo):
    """收集工作区变更，返回新增、修改、删除、未跟踪文件列表"""
    added_files: list[str] = []
    modified_files: list[str] = []
    deleted_files: list[str] = []
    untracked_files: list[str] = []

    # Untracked files
    untracked_files.extend(repo.untracked_files)

    # Modified files in the working tree
    for item in repo.index.diff(None):
        if item.change_type == "A":
            added_files.append(item.a_path)
        elif item.change_type == "M":
            modified_files.append(item.a_path)
        elif item.change_type == "D":
            deleted_files.append(item.a_path)
        else:
            logger.warning(f"unknown change type: {item.change_type}")

    # Modified files in the index (staged)
    for item in repo.index.diff(repo.head.commit):
        if item.change_type == "A":
            added_files.append(item.a_path)
        elif item.change_type == "M":
            modified_files.append(item.a_path)
        elif item.change_type == "D":
            deleted_files.append(item.a_path)
        else:
            logger.warning(f"unknown change type: {item.change_type}")

    return added_files, modified_files, deleted_files, untracked_files


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
):
    """按给定路径过滤变更（文件精确匹配；目录为前缀匹配）"""
    # 规范化路径并转换为相对仓库根目录的 POSIX 路径
    root = repo_root.resolve()
    in_path = Path(target_path)
    if not in_path.is_absolute():
        in_path = (root / in_path).resolve(strict=False)
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
    """获取文件的简要描述（用于 AI commit）"""
    brief_desc_for_file = None
    if action == "add":
        diff = index.diff(None, paths=filepath, create_patch=True)
        if len(diff) > 0:
            diff = diff.pop()
            if diff.diff:
                brief_desc_for_file = diff.diff
                if isinstance(brief_desc_for_file, bytes):
                    brief_desc_for_file = brief_desc_for_file.decode("utf-8")
                logger.debug(f"\n{brief_desc_for_file}")
        else:
            path = Path(filepath)
            if path.is_file() and path.stat().st_size < 10_000_000:  # 10MB以下
                if is_textual_file(filepath):
                    with open(filepath, "r") as f:
                        brief_desc_for_file = f.read()
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
    brief_desc: Optional[str] = None
):
    """执行单个文件的提交"""
    committer.execute(action, filepath, commit_date, brief_desc)


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
    api_key: Annotated[str, typer.Option(help="OpenAI API Key")] = None,
    base_url: Annotated[str, typer.Option(help="OpenAI API URL")] = "https://api.deepseek.com",
    model: Annotated[str, typer.Option(help="OpenAI Model")] = "deepseek-chat",
):
    logger.info(f"repo_dir: {Path(repo_dir).absolute()}")
    repo = git.Repo(repo_dir)
    index: git.IndexFile = repo.index

    # Get the list of changed files
    added_files, modified_files, deleted_files, untracked_files = collect_changes(repo)

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

    files_count = (
        len(added_files)
        + len(modified_files)
        + len(deleted_files)
        + len(untracked_files)
    )
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

    # 获取配置并创建 committer
    config = ConfigManager.get_config(api_key, base_url, model)
    committer = create_committer(index, config)

    # 处理新增文件
    for item in added_files:
        commit_date = commit_dates.pop()
        logger.info(f"commit_date: {commit_date}")
        brief_desc = get_brief_desc(index, "add", item) if isinstance(committer, AICommit) else None
        commit_file(committer, "add", item, commit_date, brief_desc)
    # 处理修改文件
    for item in modified_files:
        commit_date = commit_dates.pop()
        logger.info(f"commit_date: {commit_date}")
        brief_desc = get_brief_desc(index, "add", item) if isinstance(committer, AICommit) else None
        commit_file(committer, "add", item, commit_date, brief_desc)
    # 处理删除文件
    for item in deleted_files:
        commit_date = commit_dates.pop()
        logger.info(f"commit_date: {commit_date}")
        commit_file(committer, "rm", item, commit_date, None)
    # 处理未跟踪文件
    for item in untracked_files:
        commit_date = commit_dates.pop()
        logger.info(f"commit_date: {commit_date}")
        brief_desc = get_brief_desc(index, "add", item) if isinstance(committer, AICommit) else None
        commit_file(committer, "add", item, commit_date, brief_desc)

    logger.info("Everything done!")


@cli.command("ls", help="列出当前工作区变更并编号（彩色输出）")
def ls_cmd(
    repo_dir: Annotated[str, typer.Option(help="git 仓库目录")] = ".",
):
    repo = git.Repo(repo_dir)
    added_files, modified_files, deleted_files, untracked_files = collect_changes(repo)
    print_changes_numbered(added_files, modified_files, deleted_files, untracked_files)


@cli.command("only", help="仅提交指定文件或目录下的变更")
def only_cmd(
    target: Annotated[str, typer.Argument(help="目标文件或目录路径，相对或绝对均可")],
    repo_dir: Annotated[str, typer.Option(help="git 仓库目录")] = ".",
    ai: Annotated[bool, typer.Option(help="是否使用 AI 填写 commit 信息")] = False,
    api_key: Annotated[str, typer.Option(help="OpenAI API Key")] = None,
    base_url: Annotated[str, typer.Option(help="OpenAI API URL")] = "https://api.deepseek.com",
    model: Annotated[str, typer.Option(help="OpenAI Model")] = "deepseek-chat",
):
    repo = git.Repo(repo_dir)
    index: git.IndexFile = repo.index
    repo_root = Path(repo.working_tree_dir)

    added_files, modified_files, deleted_files, untracked_files = collect_changes(repo)
    # 过滤只保留目标路径内的变更
    added_files, modified_files, deleted_files, untracked_files = _filter_changes_by_path(
        repo_root, target, added_files, modified_files, deleted_files, untracked_files
    )

    if not (added_files or modified_files or deleted_files or untracked_files):
        typer.secho("目标路径下无待提交变更。", fg=colors.BRIGHT_BLACK)
        return

    # 输出彩色列表
    print_changes_numbered(added_files, modified_files, deleted_files, untracked_files)

    files_count = (
        len(added_files) + len(modified_files) + len(deleted_files) + len(untracked_files)
    )
    latest_commit_date = repo.head.commit.committed_datetime
    today = datetime.now(latest_commit_date.tzinfo)
    commit_dates = get_commit_dates(latest_commit_date, today, files_count)
    commit_dates.sort()
    commit_dates = commit_dates[::-1]

    # 获取配置并创建 committer
    config = ConfigManager.get_config(api_key, base_url, model)
    committer = create_committer(index, config)

    # 依序提交
    for item in added_files:
        commit_date = commit_dates.pop()
        brief_desc = get_brief_desc(index, "add", item) if isinstance(committer, AICommit) else None
        commit_file(committer, "add", item, commit_date, brief_desc)
    for item in modified_files:
        commit_date = commit_dates.pop()
        brief_desc = get_brief_desc(index, "add", item) if isinstance(committer, AICommit) else None
        commit_file(committer, "add", item, commit_date, brief_desc)
    for item in deleted_files:
        commit_date = commit_dates.pop()
        commit_file(committer, "rm", item, commit_date, None)
    for item in untracked_files:
        commit_date = commit_dates.pop()
        brief_desc = get_brief_desc(index, "add", item) if isinstance(committer, AICommit) else None
        commit_file(committer, "add", item, commit_date, brief_desc)

    logger.info("Selected changes committed. ✅")


@cli.command("config", help="配置 AI commit 参数（API Key、Base URL、Model）")
def config_cmd(
    api_key: Annotated[Optional[str], typer.Option("-k", "--api-key", help="OpenAI API Key")] = None,
    base_url: Annotated[Optional[str], typer.Option("-u", "--base-url", help="OpenAI API URL")] = None,
    model: Annotated[Optional[str], typer.Option("-m", "--model", help="OpenAI Model")] = None,
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
        return

    if not any([api_key, base_url, model]):
        typer.secho("请至少提供一个配置项: --api-key, --base-url, 或 --model", fg=colors.RED)
        typer.secho("或使用 --show 查看当前配置", fg=colors.YELLOW)
        return

    # 保存配置
    ConfigManager.save_config(
        api_key=api_key,
        base_url=base_url,
        model=model,
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
        typer.secho("  2) 在 .env 设置 OPENAI_API_KEY", fg=colors.YELLOW)
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


if __name__ == "__main__":
    cli_wrapper()
