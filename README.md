# GitAgent
Git Agent for git operations automation

## Installation
```bash
pip install oh-my-git-agent
```
```bash
$ gcli --help
 Usage: gcli [OPTIONS]

 自动填写 commit 信息提交代码

╭─ Options ──────────────────────────────────────────────────────────────────────────────────────────────────────╮
│ *  --repo-dir                  TEXT  git 仓库目录 [default: None] [required]                                   │
│    --install-completion              Install completion for the current shell.                                 │
│    --show-completion                 Show completion for the current shell, to copy it or customize the        │
│                                      installation.                                                             │
│    --help                            Show this message and exit.                                               │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

## Usage

```bash
gcli --repo-dir .
git push origin main
```
