# 后端 — FastAPI 代码评审服务

对本地已克隆仓库执行 `git pull`,逐个新提交单独评审,结果落库供 Web 界面查看。

## 运行

```bash
python -m venv .venv
./.venv/Scripts/activate         # Linux/mac: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env             # 配置模型凭证与管理员密码
uvicorn app.main:app --reload
```

- 接口文档:http://localhost:8000/docs
- 健康检查:`GET /health`

## 测试

```bash
pytest
```

## 主要接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录,返回会话 Token |
| GET  | `/api/repositories` | 仓库列表 |
| POST | `/api/repositories` | 添加本地仓库(含本地路径 / 分支) |
| PATCH/DELETE | `/api/repositories/{id}` | 更新 / 删除仓库 |
| GET  | `/api/reviews` | 评审列表(可选 `?repository_id=`) |
| GET  | `/api/reviews/{id}` | 评审详情(含 findings) |
| POST | `/api/reviews/check/{repository_id}` | 立即检查:pull + 评审新提交(后台执行) |
| GET  | `/api/settings` | 只读运行时配置 |

## 结构

```
app/
├─ main.py            FastAPI 入口 + CORS + 建表 + 可选定时轮询
├─ config.py          .env 配置
├─ db.py / models.py  SQLAlchemy 引擎与 ORM
├─ auth.py            登录 / 会话 Token / bcrypt(直接调用,72 字节截断)
├─ schemas.py         Pydantic I/O 模型
├─ routers/           auth / repositories / reviews / settings
├─ services/
│  ├─ git_service.py   本地 git 操作(pull / head_sha / new_commits / commit_diff)
│  ├─ ocr_engine.py    调 Alibaba open-code-review 的 `ocr` CLI(默认引擎)
│  ├─ review_engine.py 内置引擎:调 Claude,提取结构化 findings
│  └─ worker.py       后台任务:check_repository(逐提交建 Review)+ run_review
└─ prompts/           评审系统提示词
```

## 说明

- **评审引擎**(`REVIEW_ENGINE`):
  - `ocr`(默认):调用 [Alibaba open-code-review](https://github.com/alibaba/open-code-review) 的 `ocr` CLI(`ocr review -c <sha> --format json`)。它自带确定性的文件筛选、规则匹配与分组,再用**它自己配置的** LLM(`ocr config` / `ocr llm test`)评审,与后端 `ANTHROPIC_*` 独立。仓库的「评审规则」通过 `--background` 传入。`ocr` 未安装/不可用时自动回退内置引擎。
  - `builtin`:内置 `diff→模型` 引擎,用后端 `ANTHROPIC_*` 配置,`client.messages.create` + 稳健 JSON 提取(兼容非官方端点)。
- 提交人/仓库维度:`GET /api/reviews` 支持 `repository_id`、`commit_author` 过滤;`GET /api/reviews/facets` 返回各维度计数供前端筛选。
- 增量评审:仓库 `last_reviewed_sha` 记录基线;首次检查只评审最新提交,之后只评审新增提交,完成后推进基线。
- 后台任务用 FastAPI `BackgroundTasks`;设 `POLL_INTERVAL_MINUTES > 0` 时 `main.py` 会起一个 asyncio 轮询循环定时调用 `check_repository`。
- 会话 Token 存进程内存,重启失效;如需持久化可换 DB/Redis。
- 结果仅在平台内展示,不回帖到任何托管平台。
