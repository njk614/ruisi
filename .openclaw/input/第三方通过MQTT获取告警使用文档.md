# 第三方通过 MQTT 获取告警使用文档

本文面向第三方接入方，说明如何通过 MQTT 实时接收视频识别平台告警。

详细字段定义与平台配置见：`Output/第三方告警MQTT接入说明.md`。

## 1. 接入前提

1. 平台 `MqttPush.Enabled = true`。
2. 已部署并可访问 MQTT Broker。
3. 平台 `MqttPush.Server`、`Port`、`Topic` 指向正确 Broker。
4. 第三方订阅同一个 Topic，默认 `video/events`。

注意：视频识别平台不是 MQTT Broker。第三方必须连接 Broker，而不是直接连接视频识别 API 端口。

## 2. 推荐接入方式

1. 第三方从平台运维方获取 Broker 地址、端口、Topic、用户名、密码。
2. 使用 MQTT 客户端连接 Broker。
3. 订阅 Topic。
4. 解析收到的 JSON 消息。
5. 根据 `eventType`、`triggerReason`、`overlayPath` 进行业务处理。
6. 定期调用 `POST /webApi/events/query` 做历史补拉，避免 MQTT 网络异常期间漏处理。

## 3. 消息示例

```json
{
  "id": "3f4f2d20-8d96-4f6a-89d0-b8d2b79b7a21",
  "eventTime": "2026-06-01 14:35:12",
  "videoSourceId": "VS-000001",
  "videoSourceName": "前台",
  "spatialObjectId": "SO-000001",
  "spatialObjectName": "前台区域",
  "eventType": "enter_region",
  "countValue": 1,
  "overlayPath": "/data/overlays/20260601/3f4f2d208d964f6a89d0b8d2b79b7a21_143512123.jpg",
  "triggerReason": "检测到目标进入区域"
}
```

## 4. 关键字段

| 字段 | 说明 |
| --- | --- |
| `id` | 告警事件唯一标识 |
| `eventTime` | 北京时间，格式 `yyyy-MM-dd HH:mm:ss` |
| `videoSourceId` | 视频源业务编码，例如 `VS-000001` |
| `spatialObjectId` | 空间对象业务编码，例如 `SO-000001` |
| `eventType` | 告警类型编码 |
| `overlayPath` | 叠框图相对路径，可能为 `null` |

## 5. Python 示例

```python
import json
import paho.mqtt.client as mqtt

BROKER = "172.16.2.43"
PORT = 1883
TOPIC = "video/events"

def on_connect(client, userdata, flags, rc, properties=None):
    print("connected:", rc)
    client.subscribe(TOPIC)

def on_message(client, userdata, msg):
    event = json.loads(msg.payload.decode("utf-8"))
    print(event["eventTime"], event["videoSourceId"], event["eventType"])

client = mqtt.Client(client_id="third-party-receiver")
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_forever()
```

## 6. 常见问题

### 收不到消息

按顺序检查：

1. Broker 是否启动。
2. 平台 `MqttPush.Enabled` 是否为 `true`。
3. 平台配置的 `Server`、`Port`、`Topic` 是否与第三方订阅一致。
4. 用户名密码是否正确。
5. 平台是否实际产生了新告警。
6. 平台日志是否出现 MQTT 推送失败并进入退避期。

### 收到消息但图片打不开

`overlayPath` 是相对路径，需要拼接平台 HTTP 地址：

```text
http://<服务IP>:5224 + overlayPath
```

### MQTT 是否保证不丢

平台使用后台异步推送，失败不影响告警落库。第三方如果要求最终一致，应结合 `POST /webApi/events/query` 按时间窗口补拉。
