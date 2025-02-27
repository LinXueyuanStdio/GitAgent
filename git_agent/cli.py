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
    if filepath.startswith("\"") and filepath.endswith("\""):
        filepath = eval(filepath)
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
def main(repo_dir: Annotated[str, typer.Option(help="git 仓库目录")]):
    logger.info(f"repo_dir: {Path(repo_dir).absolute()}")
    repo = git.Repo(repo_dir)
    index: git.IndexFile = repo.index

    # Get the list of changed files
    added_files = []
    modified_files = []
    deleted_files = []
    untracked_files = []
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
    print(added_files)
    print(modified_files)
    print(deleted_files)
    print(untracked_files)

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
    logger.info(f"commit days: {len(commit_dates)} ({'<' if files_count < len(commit_dates) else '>='}{files_count} files)")
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
