# micro-swe-agent

**[🇺🇸 English](README-en.md)** | **[🇨🇳 中文](README-zh.md)**

---

micro-swe-agent 是一个可本地自托管运行的 AI coding agent MVP。

它会监听 GitHub App 的 issue webhook，筛选低风险 issue，在隔离工作目录和 Docker 沙箱中为 Python 仓库生成最小补丁，运行 `pytest`，最多自我修复 3 轮，成功后推送分支、创建 PR、回写 issue 评论，并在 dashboard 中展示 PR、冲突状态和整合操作。

## Architecture

```
received -> triaged -> sandbox_ready -> patching -> testing -> retrying -> patching
testing -> ready_for_pr -> pr_opened -> done
* -> failed
```

## Quick Start

### Docker Compose

```bash
cp .env.example .env
# Fill in OPENAI_API_KEY, GITHUB_APP_ID, GITHUB_WEBHOOK_SECRET, etc.
docker compose up --build
docker compose exec api alembic upgrade head
```

### Local Python

```bash
python -m pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# In another terminal
python -m app.workers.poller
```

## Full Documentation

| Language | File | Description |
|---|---|---|
| 🇺🇸 English | [README-en.md](README-en.md) | Full English documentation |
| 🇨🇳 中文 | [README-zh.md](README-zh.md) | 完整中文文档 |
