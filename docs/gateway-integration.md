# 主动采集型网关接入说明

## 推荐模式

优先使用支持本地 Modbus 主站轮询和 MQTT JSON 上报的网关，例如 USR-G770 轻边缘版这一类设备。

推荐链路：

```text
两台流量计 -> RS485/Modbus RTU -> 网关本地轮询 -> MQTT JSON 上报 -> EMQX -> 后端
```

服务器不主动下发查询指令，只负责接收和保存数据。

## 网关必须确认的能力

- 可作为 Modbus RTU 主站
- 可配置两个从站地址
- 可配置功能码、寄存器地址、数据类型和倍率
- 可配置采集周期，建议 30 秒或 60 秒
- 可上报到自建 MQTT Broker
- 可上报 JSON payload
- 支持 NTP 校时
- 支持断线重连

优先确认：

- 是否支持断线缓存补传
- 是否支持 TLS
- 是否支持配置导出和恢复

## 建议 topic

```text
meters/FM001/reading
meters/FM002/reading
```

也可以统一上报到：

```text
meters/{meter_id}/reading
```

后端默认订阅：

```text
meters/+/reading
```

## 建议 payload

```json
{
  "meter_id": "FM001",
  "device_ts": "2026-05-20T10:15:00+08:00",
  "instant_flow": 12.34,
  "total_flow": 56789.01,
  "unit": "m3/h"
}
```

字段说明：

- `meter_id`：流量计编号，例如 `FM001`、`FM002`
- `device_ts`：网关采集时间，必须带时区
- `instant_flow`：瞬时流量
- `total_flow`：累计流量
- `unit`：单位，默认 `m3/h`

## 两台流量计建议配置

| 流量计 | Modbus 从站地址 | MQTT meter_id |
|---|---:|---|
| 1号流量计 | 1 | FM001 |
| 2号流量计 | 2 | FM002 |

实际寄存器地址、数据类型和倍率需要以流量计说明书为准。

## 如果网关只能透传

如果设备只支持透传模式，不支持本地 Modbus 轮询和 JSON 上报，那么服务器端需要改成主动轮询：

```text
后端生成 Modbus 查询帧 -> MQTT 下发给网关 -> 网关透传到 RS485 -> 流量计响应 -> MQTT 回传 -> 后端解析
```

这种方式可行，但后端复杂度更高，需要处理：

- Modbus RTU CRC
- 请求/响应匹配
- 超时和重试
- 串行轮询
- 两台从站地址冲突
- 断线后补传困难

所以本项目优先选择主动采集型网关。
