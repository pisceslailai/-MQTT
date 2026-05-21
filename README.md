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
curl http://localhost:8000/api/gateway-configs
curl http://localhost:8000/api/runtime-settings
curl "http://localhost:8000/api/readings/payloads?limit=5"
```

## 网关 JSON 解析配置

前端进入 `网关配置` 页面，可以维护 MQTT payload 到标准读数的映射，不需要改代码适配不同网关字段名。

同一页面也可以维护数据处理规则：

- `时钟偏差阈值 秒`：设备时间与服务器接收时间超过该阈值时标记为 `clock_skew`
- `离线判定阈值 秒`：超过该时间未收到数据时标记为离线
- `15分钟最少样本数`：低于该数量的结算窗口标记为 `gap`

每条配置包含：

- `Topic 匹配`：支持 MQTT 通配符 `+` 和 `#`，例如 `meters/+/reading`
- `表号 JSON 路径`：例如 `meter_id`、`data.meterNo`
- `表号 Topic 段序号`：当 payload 没有表号时，可从 topic 中取值；`meters/FM001/reading` 的 `FM001` 序号为 `1`
- `设备时间路径`：支持 ISO 时间字符串，必须带时区；也支持秒或毫秒时间戳
- `瞬时流量路径`、`累计流量路径`
- `单位路径` 和 `默认单位`
- `瞬时流量倍率`、`累计流量倍率`：用于寄存器原始值换算
- `样例 Payload JSON`：页面可直接测试解析结果
- `最近原始 Payload`：从数据库读取最近 MQTT 原始报文，可一键套用到样例 JSON

字段路径支持点号和数组下标：

```text
data.flow
data.total
channels[0].value
```

测试解析接口：

```bash
curl -X POST http://localhost:8000/api/gateway-configs/test \
  -H 'Content-Type: application/json' \
  -d '{
    "topic": "gateway/site-a/data",
    "config": {
      "name": "嵌套网关",
      "topic_pattern": "gateway/+/data",
      "meter_id_path": "meta.meter",
      "device_ts_path": "time.ts",
      "instant_flow_path": "values.flow_raw",
      "total_flow_path": "values.total_raw",
      "default_unit": "m3/h",
      "instant_flow_scale": 0.1,
      "total_flow_scale": 0.001
    },
    "payload": {
      "meta": {"meter": "FM002"},
      "time": {"ts": "2026-05-20T10:15:00+08:00"},
      "values": {"flow_raw": 123, "total_raw": 567890}
    }
  }'
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
默认清理 30 天以前的 dump，可通过 `RETENTION_DAYS` 调整。

## 云服务器试运行

生产试运行使用独立 Compose 文件：

```bash
bash scripts/generate_htpasswd.sh admin
bash scripts/generate_emqx_auth_bootstrap.sh
bash scripts/check_prod_ready.sh
docker compose -f docker-compose.prod.yml up -d --build
```

生产版默认：

- 只公开 `80/tcp` 和 `1883/tcp`
- PostgreSQL 和 Backend 不直接暴露公网端口
- EMQX Dashboard 只绑定 `127.0.0.1:18083`
- 前端入口启用 Nginx Basic Auth
- EMQX 禁止匿名 MQTT，使用 `deploy/emqx/auth-built-in-db-bootstrap.csv` 初始化账号

详细步骤见 [docs/cloud-trial-run.md](docs/cloud-trial-run.md)。服务器从零部署命令清单见 [docs/deploy-server.md](docs/deploy-server.md)。

## 当前测试重点

- MQTT 消息是否进入 `raw_readings`
- 设备时间偏差超过 2 分钟时是否标记为 `clock_skew`
- 15 分钟汇总是否进入 `interval_readings`
- 前端是否显示两台表的实时状态和历史汇总
- `/health` 是否能显示数据库和 MQTT 连接状态
- Webhook 配置后是否能收到离线/异常告警
- `docker compose down && docker compose up` 后 PostgreSQL 数据是否保留

## 生产部署前待补

- 每周异地备份落地到对象存储或另一台机器
- 真实网关 topic、payload、寄存器倍率与现场流量计确认
- `.env` 中将 `CORS_ORIGINS=*` 改为实际访问地址，例如 `http://服务器公网IP`
