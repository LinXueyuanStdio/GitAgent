from typing import Literal
from typing_extensions import Annotated
from datetime import datetime, timedelta
from pathlib import Path
import random

import typer
import git
from loguru import logger

# pip install GitPython

cli = typer.Typer(help="自动填写 commit 信息提交代码")


def commit(
    index: git.IndexFile,
    action: Literal["add", "rm"],
    filepath,
    commit_date: datetime,
):
    logger.info(f"commit: {filepath}")
    git_path = Path(filepath) / ".git"
    if git_path.exists() and git_path.is_dir():
        logger.warning(f"skip git directory: {filepath}")
        return
    if action == "add":
        index.add([filepath])
    elif action == "rm":
        index.remove([filepath])
    else:
        logger.error(f"unknown action: {action}")
        return
    message = f"chore {action} {Path(filepath).name}"
    index.commit(message, author_date=commit_date, commit_date=commit_date)


def get_commit_dates(start_date, end_date):
    delta = end_date - start_date
    commit_dates = [start_date + timedelta(days=i) for i in range(delta.days + 1)]
    return commit_dates


@cli.command(
    short_help="自动填写 commit 信息提交代码",
    help="自动填写 commit 信息提交代码",
)
def main(repo_dir: Annotated[str, typer.Option(help="git 仓库目录")]):
    logger.info(f"repo_dir: {Path(repo_dir).absolute()}")
    repo = git.Repo(repo_dir)
    index: git.IndexFile = repo.index
    # 获取最新的提交日期
    latest_commit_date = repo.head.commit.committed_datetime
    today = datetime.now(latest_commit_date.tzinfo)
    commit_dates = get_commit_dates(latest_commit_date, today)

    # 使用git status，统计新增、修改、删除的文件
    status = repo.git.status(porcelain=True)
    added_files = []
    modified_files = []
    deleted_files = []
    untracked_files = []

    for line in status.splitlines():
        status_code, file_path = line[:2].strip(), line[3:].strip()
        if status_code == "??":
            untracked_files.append(file_path)
        elif status_code == "A":
            added_files.append(file_path)
        elif status_code == "M":
            modified_files.append(file_path)
        elif status_code == "D":
            deleted_files.append(file_path)
        else:
            logger.warning(f"unknown status code: {status_code}")

    # 输出统计结果
    logger.info(f"latest commit date: {latest_commit_date}")
    logger.info(f"today: {today}")
    logger.info(f"commit days: {len(commit_dates)}")
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
    logger.info("\n".join(msgs))

    # 从 git log 最新日期到今天，获取所有文件修改信息，随机铺满每一天，使得提交记录完整
    files_count = (
        len(added_files)
        + len(modified_files)
        + len(deleted_files)
        + len(untracked_files)
    )
    days_count = len(commit_dates)
    if files_count > days_count:
        # 自动随机复制date, 使得days_count >= files_count
        rest_count = files_count - days_count
        commit_dates.extend(random.choices(commit_dates, k=rest_count))
    # 随机打乱小时、分钟、秒
    for i in range(len(commit_dates)):
        commit_dates[i] = commit_dates[i].replace(
            hour=random.randint(0, 23),
            minute=random.randint(0, 59),
            second=random.randint(0, 59),
        )
    # 按早到晚的顺序提交
    commit_dates.sort()

    # 处理新增文件
    for item in added_files:
        commit_date = commit_dates.pop()
        commit(index, "add", item, commit_date)
    # 处理修改文件
    for item in modified_files:
        commit_date = commit_dates.pop()
        commit(index, "add", item, commit_date)
    # 处理删除文件
    for item in deleted_files:
        commit_date = commit_dates.pop()
        commit(index, "rm", item, commit_date)
    # 处理未跟踪文件
    for item in untracked_files:
        commit_date = commit_dates.pop()
        commit(index, "add", item, commit_date)


if __name__ == "__main__":
    cli()
