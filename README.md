# MQTT Flow Meter Monitor

两台流量计的 MQTT 监控与 15 分钟留痕系统。当前阶段用于 WSL 本地验证，跑通后再迁移到云服务器。

## 架构

- EMQX：MQTT Broker
- PostgreSQL：保存原始读数、15 分钟汇总、设备状态
- FastAPI backend：订阅 MQTT、入库、汇总、提供 API
- Frontend：实时和历史展示

## WSL 快速启动

1. 在 Windows 安装 Docker Desktop，并开启 WSL integration。
2. 在 WSL Ubuntu 里进入项目目录。
3. 复制环境变量文件：

```bash
cp .env.example .env
```

4. 启动服务：

```bash
docker compose up --build
```

5. 打开服务：

- 前端：http://localhost:8080
- 后端健康检查：http://localhost:8000/health
- EMQX 控制台：http://localhost:18083

EMQX 控制台账号密码来自 `.env` 的 `EMQX_DASHBOARD_USER` 和 `EMQX_DASHBOARD_PASSWORD`。

## 模拟两台流量计

在本机或 WSL 里安装脚本依赖：

```bash
python -m pip install -r scripts/requirements.txt
```

发布模拟数据：

```bash
python scripts/simulate_meters.py --host localhost --port 1883 --interval 5
```

模拟设备时间偏差：

```bash
python scripts/simulate_meters.py --host localhost --clock-skew-minutes 5
```

模拟补传历史数据：

```bash
python scripts/simulate_meters.py --host localhost --backfill-minutes 30
```

## API

```bash
curl http://localhost:8000/api/meters/latest
curl "http://localhost:8000/api/intervals?meter_id=FM001&limit=96"
curl "http://localhost:8000/api/readings/recent?meter_id=FM001&limit=20"
curl -X POST "http://localhost:8000/api/intervals/rebuild?hours_back=24"
```

## 当前测试重点

- MQTT 消息是否进入 `raw_readings`
- 设备时间偏差超过 2 分钟时是否标记为 `clock_skew`
- 15 分钟汇总是否进入 `interval_readings`
- 前端是否显示两台表的实时状态和历史汇总
- `docker compose down && docker compose up` 后 PostgreSQL 数据是否保留

## 数据库备份测试

```bash
bash scripts/backup_postgres.sh
```

备份文件默认写入 `./backups`，可通过 `BACKUP_DIR` 指定输出目录。

## 生产部署前待补

- EMQX 禁止匿名访问，改成用户名密码
- Nginx Basic Auth
- 企业微信或钉钉 Webhook
- 数据库每日备份和每周异地备份
- 云服务器安全组最小开放
