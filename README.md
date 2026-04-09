# micro-swe-agent

<div id="lang-switcher">
  <a href="README-en.md">🇺🇸 English</a>
  <span>|</span>
  <a href="README-zh.md">🇨🇳 中文</a>
</div>

---

> [!NOTE]
> You are viewing this README in your browser language. Use the links above to switch languages manually.

<script>
  // Auto-redirect based on browser language
  (function () {
    var lang = navigator.language || navigator.userLanguage || '';
    var target = lang.toLowerCase().startsWith('zh') ? 'README-zh.md' : 'README-en.md';
    var note = document.querySelector('blockquote');
    if (note) {
      var current = window.location.pathname.split('/').pop();
      if (current !== target) {
        var msg = lang.toLowerCase().startsWith('zh')
          ? '> [!NOTE]\n> 正在根据您的浏览器语言（中文）跳转至中文版…'
          : '> [!NOTE]\n> Redirecting based on your browser language (English)…';
        note.textContent = msg;
        // Auto-switch via links if on GitHub
        var links = document.querySelectorAll('#lang-switcher a');
        for (var i = 0; i < links.length; i++) {
          if (links[i].getAttribute('href') === target) {
            links[i].style.fontWeight = 'bold';
            break;
          }
        }
      }
    }
  })();
</script>

## Quick Links

| Language | File | Description |
|---|---|---|
| 🇺🇸 English | [README-en.md](README-en.md) | Full English documentation |
| 🇨🇳 中文 | [README-zh.md](README-zh.md) | 完整中文文档 |

## Overview

**micro-swe-agent** is a self-hostable AI coding agent MVP.

It listens for GitHub App issue webhooks, filters low-risk issues, generates minimal patches for Python repositories in isolated workspaces and Docker sandboxes, runs `pytest`, retries self-fix up to 3 rounds, then pushes a branch, creates a PR, comments on the issue, and displays PR/conflict/integration status in a dashboard.

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

## For Full Documentation

- [🇺🇸 English](README-en.md)
- [🇨🇳 中文](README-zh.md)
