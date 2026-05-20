# MQTT 流量计监控系统

两台流量计的 MQTT 监控与 15 分钟留痕系统。当前阶段用于 WSL 本地验证，跑通后再迁移到云服务器。

## 架构

- EMQX：MQTT Broker
- PostgreSQL：保存原始读数、15 分钟汇总、设备状态
- FastAPI backend：订阅 MQTT、入库、汇总、告警、提供 API
- Frontend：实时和历史展示页面

推荐现场链路：

```text
流量计 -> 主动采集型 Modbus/MQTT 网关 -> MQTT Broker -> 后端 -> 数据库/前端
```

如果使用 USR-G770，建议确认是支持本地 Modbus 轮询和 MQTT JSON 上报的轻边缘版。

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

## MQTT 数据格式

默认订阅 topic：

```text
meters/+/reading
```

推荐网关上报 payload：

```json
{
  "meter_id": "FM001",
  "device_ts": "2026-05-20T10:15:00+08:00",
  "instant_flow": 12.34,
  "total_flow": 56789.01,
  "unit": "m3/h"
}
```

## API

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/meters/latest
curl "http://localhost:8000/api/intervals?meter_id=FM001&limit=96"
curl "http://localhost:8000/api/readings/recent?meter_id=FM001&limit=20"
curl -X POST "http://localhost:8000/api/intervals/rebuild?hours_back=24"
```

## 告警 Webhook

`.env` 中配置：

```env
ALERT_WEBHOOK_URL=
ALERT_WEBHOOK_TYPE=wechat
```

`ALERT_WEBHOOK_TYPE` 支持：

- `wechat`：企业微信群机器人
- `dingtalk`：钉钉群机器人

当前告警范围：

- 流量计离线
- 设备时间与服务器接收时间偏差超过阈值
- 最近 15 分钟结算窗口缺数据
- 累计流量回退

## 数据库备份测试

```bash
bash scripts/backup_postgres.sh
```

备份文件默认写入 `./backups`，可通过 `BACKUP_DIR` 指定输出目录。

## 当前测试重点

- MQTT 消息是否进入 `raw_readings`
- 设备时间偏差超过 2 分钟时是否标记为 `clock_skew`
- 15 分钟汇总是否进入 `interval_readings`
- 前端是否显示两台表的实时状态和历史汇总
- `/health` 是否能显示数据库和 MQTT 连接状态
- Webhook 配置后是否能收到离线/异常告警
- `docker compose down && docker compose up` 后 PostgreSQL 数据是否保留

## 生产部署前待补

- EMQX 禁止匿名访问，改成用户名密码
- Nginx Basic Auth
- PostgreSQL 每日本地备份和每周异地备份
- 云服务器安全组最小开放
- 真实网关 topic、payload、寄存器倍率与现场流量计确认
