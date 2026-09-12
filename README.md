# PlayGen - Playwright 业务接口采集与用例生成平台

## 技术栈

| 层次 | 技术选型 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite + Element Plus |
| API 服务 | Python 3.12 + FastAPI + Pydantic |
| 浏览器采集 | Playwright Python |
| 接口执行 | pytest + httpx |
| ORM/迁移 | SQLAlchemy 2.0 + Alembic |
| 数据库 | PostgreSQL 15 |
| 缓存与队列 | Redis 7 + Celery 5 |
| 模板引擎 | Jinja2 |
| 对象存储 | MinIO (S3 兼容) |
| 部署 | Docker Compose |

## 项目结构

```
PlayGen/
├── api-server/               # FastAPI 后端
├── web-console/              # Vue 3 前端
├── collector/                # Playwright 采集器
├── analyzer/                 # 流量分析引擎
├── generator/                # DSL 与代码生成
├── executor/                 # pytest/httpx 执行 Worker
├── scheduler/                # 定时调度
└── deploy/                   # Docker Compose 部署配置
```

## 快速启动

### 1. 启动基础设施

```bash
cd deploy
docker-compose up -d postgres redis minio
```

### 2. 启动后端

```bash
cd api-server
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 启动前端

```bash
cd web-console
npm install
npm run dev
```

### 4. 一键 Docker 部署

```bash
cd deploy
docker-compose up -d
```

访问:
- 前端: http://localhost:3000
- API 文档: http://localhost:8000/docs
- MinIO 控制台: http://localhost:9001
