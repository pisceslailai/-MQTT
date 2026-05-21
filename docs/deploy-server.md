# 服务器从零部署步骤

本文档是公网试运行的命令清单。安全策略和现场配置说明见 [cloud-trial-run.md](cloud-trial-run.md)。

## 1. 安装基础软件

Ubuntu 服务器示例：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git openssl
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc >/dev/null
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"
```

重新登录 SSH 后确认：

```bash
docker version
docker compose version
```

如果服务器访问 Docker Hub 不稳定，先按云厂商推荐配置 Docker 镜像加速，再执行后续步骤。

## 2. 拉取代码

```bash
sudo mkdir -p /opt/flow-monitor
sudo chown "$USER":"$USER" /opt/flow-monitor
git clone https://github.com/pisceslailai/-MQTT.git /opt/flow-monitor
cd /opt/flow-monitor
```

## 3. 配置密钥

```bash
cp .env.example .env
nano .env
```

必须修改：

- `POSTGRES_PASSWORD`
- `EMQX_DASHBOARD_PASSWORD`
- `MQTT_PASSWORD`
- `MQTT_GATEWAY_PASSWORD`
- `CORS_ORIGINS=http://服务器公网IP`

## 4. 生成认证文件

```bash
bash scripts/generate_htpasswd.sh admin
bash scripts/generate_emqx_auth_bootstrap.sh
bash scripts/check_prod_ready.sh
```

`generate_htpasswd.sh` 输入的是网页 Basic Auth 密码；现场网关 MQTT 密码来自 `.env` 的 `MQTT_GATEWAY_PASSWORD`。

## 5. 启动服务

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
curl -u admin:网页BasicAuth密码 http://localhost/health
```

访问：

```text
http://服务器公网IP
```

EMQX 后台默认不暴露公网，查看时使用 SSH 隧道：

```bash
ssh -L 18083:127.0.0.1:18083 user@服务器公网IP
```

然后打开 `http://localhost:18083`。

## 6. 配置 USR-G770

1. 网关 MQTT 指向服务器公网 IP、端口 `1883`。
2. 网关使用 `.env` 的 `MQTT_GATEWAY_USERNAME` 和 `MQTT_GATEWAY_PASSWORD`。
3. 后台 `网关配置` 新增真实 topic，例如 `/USR-G770/update`。
4. 拿到第一条真实报文后，在 `USR-G770 r_data 点位映射` 中配置四条基础映射。
5. 查看 `运行看板`，确认 FM001 和 FM002 更新时间、瞬时流量、累计量正常。

## 7. 备份

先手动验证：

```bash
bash scripts/backup_postgres.sh
```

再安装每日备份：

```bash
crontab deploy/cron/flow-monitor-backup.cron.example
crontab -l
```

试运行阶段至少每周把 `backups/` 目录同步到另一台机器或对象存储。
