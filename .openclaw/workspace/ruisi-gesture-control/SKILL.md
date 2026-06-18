---
name: ruisi-gesture-control
description: 接收 test-ae01@im.tuguan.net 转发的手势/姿势事件（event 为 gesture 或 posture，含 zone、timestamp、gesture_type），识别手势意图后执行两类动作：演示控制（转发 ruisi-explanation-service 的 send_message.py）+ 文本推送（HTTP API 推送提示文本到 niujunke@im.tuguan.net）。映射规则：gesture_type 为 "OK" → 开始演示，并推送"开始演示"；"X交叉手势" → 暂停，并推送"暂停演示"；"举手" → 暂停，并推送"您好，有什么可以帮助您的？"。本 Skill 仅做识别与映射/转发/推送，不直接跑演示，不直连内容展示器。它处理的是用户对"是否演示"询问的手势回应，与处理 enter 事件的 ruisi-video-perceptionflow 互斥（event 类型不同，不会相互误触发）。
version: 1.0.0
author: niujunke
level: L1
allowed-tools:
  - bash
  - python
metadata:
  openclaw:
    emoji: '🤙'
    requires:
      bins: []
      config: []
      env: []
dependencies: []
---

# 手势控制流程

> **设计说明**：本 Skill 是一层"识别 → 映射 → 转发/推送"的薄翻译层。它接收 AE01 转发的手势/姿势事件，按映射表执行两类动作：①演示控制——同 Agent 内直接调用 `ruisi-explanation-service` 的 `send_message.py` 执行真实演示控制（开始演示 / 暂停）；②文本推送——通过 HTTP API 把提示文本推送到 P01（`niujunke@im.tuguan.net`）。它不维护演示逻辑，也不直连内容展示器。

## 在整体链路中的位置

```
人员监测(AE01: event=enter) → ruisi-video-perceptionflow: 欢迎语 + 自动开灯 + 询问"是否演示"
        ↓ 用户用手势回应
手势/姿势(AE01: event=gesture/posture) → 【本 Skill】: OK → 开始演示 / X 交叉 → 暂停 / 举手 → 暂停+询问
        ↓ ①映射控制词直调脚本          ②推送提示文本到 P01
                                       → ruisi-explanation-service 执行演示控制
                                       → P01 设备显示提示文本
```

`ruisi-video-perceptionflow` 的职责到"询问是否演示"为止；用户的手势回应属于下一拍，由本 Skill 处理。两者通过 `event` 类型区分（`enter` vs `gesture/posture`），互不干扰。

---

## 触发条件

1. **接收手势/姿势事件**：Skill 接收到的消息本身为 JSON 对象时自动判定。
   - **输入格式**：直接接收事件 JSON，不要求外层 `jid` / `from` / `body` 包裹。
   - **事件格式**：
     ```json
     {
       "event": "gesture",
       "zone": "meeting-room-large",
       "timestamp": "2026-06-16T15:28:46+08:00",
       "gesture_type": "OK"
     }
     ```
   - **参数说明**：
     | 字段 | 说明 |
     |------|------|
     | `event` | 事件类型，取 `gesture` 或 `posture` 触发 |
     | `zone` | 检测区域标识 |
     | `timestamp` | 检测时间，ISO 8601 格式 |
     | `gesture_type` | 手势/姿势取值，如 `OK` / `X交叉手势`（兼容旧字段名 `gesture`） |

2. **严格触发判定（必须同时满足）**：

- 输入消息本身是合法 JSON 对象
- `event ∈ {"gesture", "posture"}`（**不是 `enter`**，因此不会与 ruisi-video-perceptionflow 抢触发）
- 包含 `zone`、`timestamp`、`gesture_type`（或兼容字段 `gesture`）且不为空

3. **不满足触发条件时的处理**：

- 不执行后续步骤
- 输出 `ignored` 状态，记录原因（事件类型不匹配 / 字段缺失 / JSON 非法）

---

## 手势映射表

手势取值统一转小写后匹配。AE01 实测上报字段为 `gesture_type`，取值 `"OK"` / `"X交叉手势"` / `"举手"`。若上报值有变，调整脚本内 `GESTURE_ACTIONS` 即可。

**组合手势择一**：`gesture_type` 可能是用 `、`（兼容 `,` `，` `/`）分隔的组合，如 `"OK、举手"` / `"OK、X交叉手势、举手"`。本 Skill **只识别其中一个**，按优先级择一：

```
举手 > X交叉手势 > OK
```

即组合中只要含"举手"就按举手处理；否则含"X交叉手势"就按暂停处理；否则才按 OK 处理。其余 token 忽略。

每条手势可同时触发两类动作：**演示控制**（转发讲解服务）与 **文本推送**（HTTP API 推送到 P01）。

| gesture_type 取值                                  | 优先级 | 演示控制                         | 推送文本 → P01                            |
| -------------------------------------------------- | :----: | -------------------------------- | ----------------------------------------- |
| `举手` / `raise_hand` / `hand_up`                  |   高   | `暂停`（调 send_message.py）     | `您好，有什么可以帮助您的？`              |
| `X交叉手势` / `X交叉` / `交叉手势` / `cross` / `x` |   中   | `暂停`（调 send_message.py）     | `暂停演示`                                |
| `OK` / `ok_sign` / `okay`                          |   低   | `开始演示`（调 send_message.py） | `开始演示`                                |
| 其他                                               |   —    | —                                | — （输出 `noop`，原因 `unknown_gesture`） |

---

## 文本推送（HTTP API）

提示文本通过 HTTP API 推送到 P01，格式对齐 `ruisi-free-qa`：

```
POST http://127.0.0.1:18900/send
Content-Type: application/json

{
  "jid": "niujunke@im.tuguan.net",
  "body": "（提示文本，如 开始演示 / 暂停演示 / 您好，有什么可以帮助您的？）",
  "from": "test-a01@im.tuguan.net"
}
```

推送带一次重试。地址 / JID / from 可用 `--push-url` / `--push-jid` / `--push-from` 或环境变量 `XMPP_SEND_API_URL` / `P01_JID` / `XMPP_FROM_ACCOUNT` 覆盖。

---

## 必须遵守的约定

- **映射 + 转发/推送**：识别手势 → 查映射表 → ①调 `ruisi-explanation-service/scripts/send_message.py` 执行演示控制 + ②通过 HTTP API 推送提示文本到 P01。本 Skill 不跑演示、不直连内容展示器、不生成卡片。
- **原样透传讲解服务输出**：讲解服务对"开始演示/暂停"等控制类指令成功时静默（stdout 为空），失败或查询类才返回 JSON。本 Skill 不对其输出二次加工。
- **不与 perceptionflow 混淆**：本 Skill 只处理 `gesture/posture`，`enter` 事件一律不接。

---

## 输入参数

| 参数名       | 类型   | 必填 | 说明                                           |
| ------------ | ------ | ---- | ---------------------------------------------- |
| event        | string | 是   | 事件类型，取 `gesture` 或 `posture`            |
| zone         | string | 是   | 检测区域标识                                   |
| timestamp    | string | 是   | 检测时间，ISO 8601 含时区                      |
| gesture_type | string | 是   | 手势取值，见手势映射表（兼容旧字段 `gesture`） |

**输入示例**：

```json
{
  "event": "gesture",
  "zone": "meeting-room-large",
  "timestamp": "2026-06-16T15:28:46+08:00",
  "gesture_type": "OK"
}
```

---

## 输出参数

| 参数名    | 类型   | 说明                                                           |
| --------- | ------ | -------------------------------------------------------------- |
| status    | string | success / failed / ignored / noop                              |
| message   | string | 人类可读的结果描述                                             |
| command   | string | **可选**。映射出的演示控制词（开始演示 / 暂停），举手类为 null |
| push_text | string | **可选**。推送到 P01 的提示文本                                |

**status 取值**：

- `success` — 已映射并成功执行（转发讲解服务 / 推送 P01，按映射表）
- `failed` — 转发或推送失败（脚本不存在 / 调用异常 / API 不可达 / 返回非零）
- `ignored` — 未通过触发判定（非法 JSON / 事件类型不匹配 / 字段缺失）
- `noop` — 触发条件通过，但手势无法识别（`unknown_gesture`）

> 转发成功后，讲解服务对控制类指令静默处理，本 Skill 的 stdout 也保持静默以对齐其约定；仅在出现失败时输出 `failed` JSON。

---

## 执行步骤

### 步骤 1：解析事件

读取消息体（stdin 或 `--payload`），解析为 JSON 对象。非法 JSON → 输出 `ignored`。

### 步骤 2：校验触发条件

校验 `event ∈ {gesture, posture}`，且 `zone` / `timestamp` / `gesture` 均存在且非空。不通过 → 输出 `ignored`。

### 步骤 3：映射手势

读取 `gesture_type`（缺失时回退 `gesture`）。若取值为 `、`（兼容 `,` `，` `/`）分隔的组合，按优先级 `举手 > X交叉手势 > OK` 择一，其余忽略。按手势映射表转为动作 `{command, push_text}`。无法识别 → 输出 `noop`（`unknown_gesture`）。

### 步骤 4：执行动作

按映射结果执行两类动作（任一存在即执行，互不依赖）：

1. **演示控制**（`command` 非空时）——同 Agent 内直接调用讲解服务入口脚本：

```bash
python <skills>/ruisi-explanation-service/scripts/send_message.py --payload "开始演示"
```

或 `--payload "暂停"`。脚本默认按相对位置定位讲解服务脚本（两个 skill 同级位于 `skills/` 下），可用 `--send-script` 覆盖。

2. **文本推送**（`push_text` 非空时）——通过 HTTP API 推送到 P01：

```
POST http://127.0.0.1:18900/send
{"jid":"niujunke@im.tuguan.net","body":"<push_text>","from":"test-a01@im.tuguan.net"}
```

任一动作失败 → 输出 `failed`；全部成功 → 静默。

---

## 调用方式

```bash
# 从 stdin 接收事件
echo '{"event":"gesture","zone":"meeting-room-large","timestamp":"2026-06-16T15:28:46+08:00","gesture_type":"OK"}' \
  | python scripts/dispatch_gesture.py

# 或显式传入
python scripts/dispatch_gesture.py --payload '{"event":"gesture","zone":"meeting-room-large","timestamp":"2026-06-16T15:28:46+08:00","gesture_type":"X交叉手势"}'

# 只验证映射，不实际转发
python scripts/dispatch_gesture.py --dry-run --payload '{"event":"gesture","zone":"x","timestamp":"t","gesture_type":"OK"}'
```

---

## 错误处理

| 场景                             | 处理方式                     | status  |
| -------------------------------- | ---------------------------- | :-----: |
| 事件非法 JSON / 非对象           | 记录原因，不执行             | ignored |
| 事件类型非 gesture/posture       | 记录原因，不执行             | ignored |
| 缺少 zone/timestamp/gesture_type | 记录原因，不执行             | ignored |
| 手势无法识别                     | 记录 unknown_gesture，不执行 |  noop   |
| 讲解服务脚本不存在 / 调用异常    | 返回失败原因                 | failed  |
| P01 推送 API 不可达 / 返回失败   | 重试一次后返回失败原因       | failed  |

---

## 安全与权限

- **消息接收**：来自 `test-ae01@im.tuguan.net` 的手势/姿势事件
- **下游调用**：①同 Agent 下 `ruisi-explanation-service/scripts/send_message.py` 执行演示控制；②本地 HTTP API `http://127.0.0.1:18900/send` 推送提示文本到 `niujunke@im.tuguan.net`
- **不持久化**：本 Skill 不写留痕目录、不生成 manifest（与讲解服务一致，控制类为轻量转发）

---

## 示例

### 示例 1：OK 手势 → 开始演示

**输入**：

```json
{
  "event": "gesture",
  "zone": "meeting-room-large",
  "timestamp": "2026-06-16T15:28:46+08:00",
  "gesture_type": "OK"
}
```

**动作**：映射为 `开始演示`，①调 `send_message.py --payload "开始演示"` 启动后台演示；②HTTP 推送 `开始演示` 到 P01。全部成功时静默。

### 示例 2：X 交叉手势 → 暂停

**输入**：

```json
{
  "event": "gesture",
  "zone": "meeting-room-large",
  "timestamp": "2026-06-16T15:30:00+08:00",
  "gesture_type": "X交叉手势"
}
```

**动作**：映射为 `暂停`，①调 `send_message.py --payload "暂停"` 暂停当前演示；②HTTP 推送 `暂停演示` 到 P01。全部成功时静默。

### 示例 3：举手 → 暂停 + 询问

**输入**：

```json
{
  "event": "gesture",
  "zone": "meeting-room-large",
  "timestamp": "2026-06-16T15:32:00+08:00",
  "gesture_type": "举手"
}
```

**动作**：映射为 `暂停`，①调 `send_message.py --payload "暂停"` 暂停当前演示；②HTTP 推送 `您好，有什么可以帮助您的？` 到 P01。全部成功时静默。

### 示例 4：组合手势 → 按优先级择一

**输入**：

```json
{
  "event": "gesture",
  "zone": "meeting-room-large",
  "timestamp": "2026-06-16T15:33:00+08:00",
  "gesture_type": "OK、X交叉手势、举手"
}
```

**动作**：组合中含"举手"，优先级最高，按举手处理——①调 `send_message.py --payload "暂停"` 暂停；②HTTP 推送 `您好，有什么可以帮助您的？` 到 P01，忽略 OK 与 X交叉手势。

### 示例 5：无法识别的手势

**输入**：

```json
{
  "event": "gesture",
  "zone": "meeting-room-large",
  "timestamp": "2026-06-16T15:31:00+08:00",
  "gesture_type": "挥手"
}
```

**输出**：

```json
{ "status": "noop", "message": "无法识别的手势：挥手", "reason": "unknown_gesture" }
```

### 示例 6：enter 事件（不属于本 Skill）

**输入**：

```json
{ "event": "enter", "zone": "meeting-room-large", "timestamp": "2026-06-16T14:01:00+08:00", "total_count": 3 }
```

**输出**：

```json
{ "status": "ignored", "message": "事件类型不匹配（需为 gesture / posture）", "reason": "ignored_event" }
```
