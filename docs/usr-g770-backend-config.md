# USR-G770 后端接入配置

USR-G770 轻边缘版在 Modbus 轮询结束后，可以把多个点位打包成一条 MQTT JSON 上报。后端按 `params.r_data[].name` 做点位映射，不要求平台主动下发查询指令。

## 典型上报格式

```json
{
  "params": {
    "dir": "up",
    "id": "02500524060700013275",
    "time": "2026-05-21 09:14:00",
    "r_data": [
      {"name": "FM001_instant", "value": "12.3", "err": "0"},
      {"name": "FM001_total", "value": "1000.5", "err": "0"},
      {"name": "FM002_instant", "value": "9.8", "err": "0"},
      {"name": "FM002_total", "value": "2000.7", "err": "0"}
    ]
  }
}
```

`err` 不为 `0` 的点位会被忽略。每块表至少要有一个 `instant_flow` 点位和一个 `total_flow` 点位，后端才会生成该表的一条读数。

## 1. 配置订阅主题

如果网关固定发布到 `/USR-G770/update`，在网关配置里新增一条启用配置：

```bash
curl -X POST http://localhost:8000/api/gateway-configs \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "USR-G770 JSON组包上报订阅",
    "enabled": true,
    "priority": 50,
    "topic_pattern": "/USR-G770/update",
    "meter_id_path": "params.id",
    "device_ts_path": "params.time",
    "instant_flow_path": "params.r_data[0].value",
    "total_flow_path": "params.r_data[1].value",
    "default_unit": "m3/h",
    "notes": "用于让后端订阅USR固定上报主题；批量r_data实际按点位映射解析。"
  }'
```

后端启动或重连 MQTT 时，会订阅 `.env` 的 `MQTT_TOPIC`，也会订阅所有启用网关配置的 `topic_pattern`。

## 2. 配置 r_data 点位映射

每个 `source_name` 对应网关上报里的一个 `r_data[].name`：

```bash
curl -X POST http://localhost:8000/api/usr-r-data-mappings \
  -H 'Content-Type: application/json' \
  -d '{"source_name":"FM001_instant","meter_id":"FM001","target_field":"instant_flow","scale":1,"unit":"m3/h"}'

curl -X POST http://localhost:8000/api/usr-r-data-mappings \
  -H 'Content-Type: application/json' \
  -d '{"source_name":"FM001_total","meter_id":"FM001","target_field":"total_flow","scale":1,"unit":"m3"}'
```

两台表通常配置四条映射：

| source_name | meter_id | target_field |
| --- | --- | --- |
| FM001_instant | FM001 | instant_flow |
| FM001_total | FM001 | total_flow |
| FM002_instant | FM002 | instant_flow |
| FM002_total | FM002 | total_flow |

现场真实配置时，把 `source_name` 换成 USR 配置软件里点表变量名即可。寄存器缩放可以放在网关侧，也可以放在这里的 `scale`。

## 3. 查询和维护

```bash
curl http://localhost:8000/api/usr-r-data-mappings
curl -X PUT http://localhost:8000/api/usr-r-data-mappings/1 -H 'Content-Type: application/json' -d '{...}'
curl -X DELETE http://localhost:8000/api/usr-r-data-mappings/1
```

拿到现场第一条真实 MQTT 报文后，先确认：

- 发布主题是否已经被后端订阅。
- `r_data[].name` 是否和映射里的 `source_name` 完全一致。
- 累计量单位和瞬时量单位是否已经按 `scale` 换算到系统口径。
- `params.time` 如果没有时区，后端按 `Asia/Shanghai` 解释；如果网关不上报时间，后端用服务器接收时间。
