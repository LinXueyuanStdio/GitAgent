from collections import defaultdict
from pathlib import Path
from typing import Literal
from typing_extensions import Annotated
import git
import random
from datetime import datetime, timedelta
# pip install GitPython

import typer

from loguru import logger


cli = typer.Typer(help="自动填写 commit 信息提交代码")


def commit(
  index: git.IndexFile,
  action: Literal["add", "rm"],
  filepath,
  commit_date: datetime,
):
    filepath = Path(filepath)
    git_path = filepath / ".git"
    filepath = str(filepath.absolute())
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
    message = f"chore {action} {filepath}"
    index.commit(message, author_date=commit_date, commit_date=commit_date)
    logger.info(f"add and commit: {filepath}")


def get_commit_dates(start_date, end_date):
    delta = end_date - start_date
    commit_dates = [start_date + timedelta(days=i) for i in range(delta.days + 1)]
    return commit_dates


@cli.command(
    short_help="自动填写 commit 信息提交代码",
    help="自动填写 commit 信息提交代码",
)
def main(repo_dir: Annotated[str, typer.Option(help="git 仓库目录")]):
    print(repo_dir)
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
        if status_code == '??':
            untracked_files.append(file_path)
        elif status_code == 'A':
            added_files.append(file_path)
        elif status_code == 'M':
            modified_files.append(file_path)
        elif status_code == 'D':
            deleted_files.append(file_path)
        else:
            logger.warning(f"unknown status code: {status_code}")

    # 输出统计结果
    print("Untracked files:", untracked_files)
    print("Added files:", added_files)
    print("Modified files:", modified_files)
    print("Deleted files:", deleted_files)

    # 从 git log 最新日期到今天，获取所有文件修改信息，随机铺满每一天，使得提交记录完整
    files_count = len(added_files) + len(modified_files) + len(deleted_files) + len(untracked_files)
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

    # for item in index.diff(None):
    #     filepath = item.a_path
    #     print(filepath, item.change_type)
            # index.remove([filepath])
    # message = f"chore remove"
    # index.commit(message)

    # for item in index.diff(None):
    #     filepath = item.a_path
    #     commit_date = commit_dates.pop()
    #     commit(index, filepath)
    #     repo.git.commit('--amend', '--no-edit', '--date', commit_date.isoformat())


if __name__ == "__main__":
    cli()
