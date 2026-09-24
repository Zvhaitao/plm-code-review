# PLM 自动代码评审平台

基于 Claude(或兼容端点)的自动代码评审 Web 平台:对**本地已克隆**的仓库执行 `git pull`,逐个新提交单独评审,结果保存在平台内查看。支持在 Web 界面手动「立即检查」,也可开启定时轮询自动检查。

## 技术栈

- **后端**:Python + FastAPI + SQLAlchemy(SQLite,可切 PostgreSQL)
- **智能后端**:Claude API(`anthropic` SDK),兼容第三方 Anthropic 协议端点
- **前端**:React + Vite + TypeScript + Ant Design
- **代码来源**:本地已克隆的 git 仓库(通过 `git` 命令行读取)
- **认证**:简单登录(单管理员账号 + 会话 Token)

## 架构

```
本地已克隆仓库 ──git pull / log / show──▶ FastAPI 后端
                                          ├─ 按 last_reviewed_sha 找出新提交
                                          ├─ 每个新提交单独取 diff
                                          ├─ 调 Claude 评审引擎 → 结构化 findings
                                          ├─ 落库 (Review / Finding),推进基线
                                          └─ 结果仅在平台内展示(不回帖)
React + AntD 前端 ──REST + 登录──▶ 后端(看板 / 仓库配置 / 评审详情 / 设置)
```

触发方式:**手动「立即检查」为主**;可选设置 `POLL_INTERVAL_MINUTES > 0` 开启后台定时轮询。

## 快速开始

### 后端

```bash
cd backend
python -m venv .venv
./.venv/Scripts/activate        # Windows;Linux/mac 用 source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # 填入模型凭证 / 管理员密码
uvicorn app.main:app --reload   # http://localhost:8000 ,接口文档 /docs
```

首次启动会自动建表并按 `.env` 初始化管理员账号。修改 `.env` 后需重启后端。

### 前端

```bash
cd frontend                     # 需 Node 18+
npm install
npm run dev                     # http://localhost:5173 (已代理 /api 到后端)
```

## 接入仓库

1. 先把目标仓库 **克隆到本地**(平台不负责克隆,只负责拉取和评审)。
2. Web 界面登录后,在 **仓库配置** 中「添加仓库」,填写:
   - 分组/前缀、仓库名(仅用于展示区分)
   - **本地路径**:已克隆仓库目录的绝对路径(如 `D:\repos\schpro_package`)
   - 分支(可选,留空用仓库当前分支)
   - 评审规则(可选,如「重点关注 SQL 注入与空指针」)
3. 点「立即检查」:后端会 `git pull`,对自上次基线以来的每个新提交单独评审。
   - **首次检查**(无基线)只评审最新一次提交,并把基线设为该提交。
   - 之后每次检查只评审新增提交,评审完成后推进基线。
4. 在**看板**查看评审列表,点进**评审详情**看摘要、评分与逐条 findings。

## 目录

- [backend/](backend/) — FastAPI 后端(见 [backend/README.md](backend/README.md))
- [frontend/](frontend/) — React 前端

## 安全说明

- 所有 `/api/*` 接口经登录 Token 保护;CORS 仅放行 `FRONTEND_ORIGIN`。
- 模型凭证(`ANTHROPIC_API_KEY` 或 `ANTHROPIC_AUTH_TOKEN`)仅存后端 `.env`,不下发前端、不回显。
- 提交 diff 会发送到所配置的模型端点(外部服务),评审敏感代码前请确认合规。
- 平台以本地文件系统权限读取仓库目录;请确保填写的本地路径可信。
