# 云服务器试运行部署

本文档用于公网 IP 方式的 v1 试运行。v1 暂不强制 HTTPS 和 MQTT TLS，但必须启用强密码、MQTT 账号认证、Web Basic Auth、最小端口开放和数据库备份。

## 1. 准备服务器

建议从 `2核4G / 80GB SSD / 3-5M 带宽` 起步。

安全组只开放：

- `80/tcp`：前端页面和 API 代理入口
- `1883/tcp`：现场网关连接 MQTT
- `22/tcp`：SSH，建议限制来源 IP

不要开放：

- `5432/tcp` PostgreSQL
- `8000/tcp` Backend
- `18083/tcp` EMQX Dashboard

生产 Compose 已将 EMQX Dashboard 绑定到 `127.0.0.1:18083`，需要查看时用 SSH 隧道：

```bash
ssh -L 18083:127.0.0.1:18083 user@server-ip
```

## 2. 配置环境变量

```bash
cp .env.example .env
```

必须修改：

- `POSTGRES_PASSWORD`
- `EMQX_DASHBOARD_PASSWORD`
- `MQTT_PASSWORD`
- `MQTT_GATEWAY_PASSWORD`
- `CORS_ORIGINS=http://服务器公网IP`

`MQTT_USERNAME` 是后端订阅 MQTT 使用的账号；`MQTT_GATEWAY_USERNAME` 是现场网关上报使用的账号。

## 3. 生成 Nginx Basic Auth

```bash
bash scripts/generate_htpasswd.sh admin
```

脚本会写入 `deploy/nginx/.htpasswd`。该文件被 `.gitignore` 忽略，不要提交。

## 4. 生成 EMQX MQTT 用户

根据 `.env` 自动生成 EMQX 用户文件：

```bash
bash scripts/generate_emqx_auth_bootstrap.sh
```

脚本会写入 `deploy/emqx/auth-built-in-db-bootstrap.csv`，内容来自 `.env` 的 `MQTT_USERNAME`、`MQTT_PASSWORD`、`MQTT_GATEWAY_USERNAME`、`MQTT_GATEWAY_PASSWORD`。

该文件只在 EMQX 内置认证器创建时导入一次。后续新增账号可在 EMQX Dashboard 的 `Access Control -> Authentication` 中维护。

## 5. 上云前自检

```bash
bash scripts/check_prod_ready.sh
```

自检会确认：

- `.env` 关键密码不是示例值
- `CORS_ORIGINS` 不是 `*`
- Basic Auth 和 EMQX 用户文件已生成
- 生产 Compose 不暴露 PostgreSQL 和 Backend 端口
- Nginx 生产配置可通过语法检查
- EMQX 认证配置可通过静态检查

## 6. 启动生产试运行

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

检查状态：

```bash
docker compose -f docker-compose.prod.yml ps
curl -u admin:你的BasicAuth密码 http://localhost/health
```

打开：

```text
http://服务器公网IP
```

## 7. 现场网关配置

网关 MQTT 连接：

- Host：服务器公网 IP
- Port：`1883`
- Username：`.env` 的 `MQTT_GATEWAY_USERNAME`
- Password：`.env` 的 `MQTT_GATEWAY_PASSWORD`
- Topic：如果现场可配置，建议 `meters/FM001/reading`、`meters/FM002/reading`；如果 USR-G770 已固定为 `/USR-G770/update`，就在后台新增该 topic 的网关配置。

如果 payload 字段不是推荐格式，进入页面 `网关配置`，维护 JSON 路径、倍率和样例 payload，先点击 `测试解析`，确认能转成标准读数后再启用。

USR-G770 轻边缘版通常由网关本地轮询 Modbus，再把多个点位一次性放进 `params.r_data` 上报。平台侧不需要主动发起查询。现场拿到第一条真实报文后，在 `网关配置 -> USR-G770 r_data 点位映射` 里维护：

- `r_data 点位名`：网关报文中的 `params.r_data[].name`
- `系统表号`：例如 `FM001`、`FM002`
- `目标字段`：`瞬时流量` 或 `累计流量`
- `倍率 scale`：寄存器原始值到系统口径的换算倍率

两台流量计至少需要 4 条映射：1 号表瞬时、1 号表累计、2 号表瞬时、2 号表累计。详细示例见 [USR-G770 后端接入配置](usr-g770-backend-config.md)。

同一页面还需要确认数据处理规则：

- 采集周期 60 秒时，`15分钟最少样本数` 可先设为 `10`
- 采集周期 30 秒时，可按现场稳定性设为 `20` 到 `25`
- `时钟偏差阈值 秒` 建议先保持 `120`
- `离线判定阈值 秒` 建议大于 2 到 3 个采集周期

## 8. 备份

先验证手动备份：

```bash
bash scripts/backup_postgres.sh
```

默认保留最近 30 天备份，可通过 `RETENTION_DAYS` 调整：

```bash
BACKUP_DIR=/opt/mqtt-flow/backups RETENTION_DAYS=30 bash scripts/backup_postgres.sh
```

安装每日备份 cron：

```bash
crontab deploy/cron/flow-monitor-backup.cron.example
```

每周异地备份可先用 `scp` 或对象存储客户端同步 `backups/` 目录。试运行阶段至少每周手动抽查一次备份文件是否能生成。
