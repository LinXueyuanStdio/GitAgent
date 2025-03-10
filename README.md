# GitAgent

![PyPI](https://img.shields.io/pypi/v/oh-my-git-agent) ![PyPI - Python Version](https://img.shields.io/pypi/pyversions/oh-my-git-agent) ![PyPI - License](https://img.shields.io/pypi/l/oh-my-git-agent)

Git Agent for git operations automation.

It will commit file by file on day by day, to make sure you have a commit every day.

![](screenshot.png)

## Installation
```bash
pip install oh-my-git-agent
```

## Usage

```bash
# You can call gcli. Default is to commit at current directory
gcli

# You can specify the repo-dir and call gcli at any where
gcli --repo-dir .

# You can use ai to generate commit message. Default provider is DeepSeek
gcli --ai --api-key sk-xxx --repo-dir .

# or use openai to generate commit message
gcli --ai --base-url null --api-key sk-xxx --repo-dir .

# After committing, you can push code to remote
git push origin main
```

Full Documentation:

```bash
$ gcli --help

 Usage: cli.py [OPTIONS]

 自动填写 commit 信息提交代码

╭─ Options ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ --repo-dir                         TEXT  git 仓库目录 [default: .]                                                        │
│ --ai                    --no-ai          是否使用 AI 填写 commit 信息 [default: no-ai]                                    │
│ --api-key                          TEXT  OpenAI API Key [default: None]                                                   │
│ --base-url                         TEXT  OpenAI API URL [default: https://api.deepseek.com]                               │
│ --model                            TEXT  OpenAI Model [default: deepseek-chat]                                            │
│ --install-completion                     Install completion for the current shell.                                        │
│ --show-completion                        Show completion for the current shell, to copy it or customize the installation. │
│ --help                                   Show this message and exit.                                                      │
╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```
