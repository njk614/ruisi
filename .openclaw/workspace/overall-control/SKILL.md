---
name: overall-control
description: 环境与设备控制协调器。处理用户对灯光、空调、孪易大屏的自然语言控制指令（开/关/调温/功能切换/层级切换/视野控制/图层图表/时间轴/环境控制/对象操作/主题生成与统计分析），以及根据环境传感器数据自动调节环境温度。当用户说"开灯"、"空调24度"、"切换大屏"、"下一层"、"聚焦XX对象"、"生成XX主题"、"统计一下园区情况"、"分析XX"或视频感知流程触发自动调节时使用此技能。
version: 1.0.0
author: 王杉杉
level: L1
allowed-tools:
  - read
  - write
  - exec
  - sessions_send
metadata:
  openclaw:
    emoji: '🔧'
    requires:
      bins:
        - curl
      config: []
      env: []
dependencies:
  - command: curl
    min_version: '7.0'
---

# 总体控制流程

## 触发条件

1. **用户指令模式**：用户直接发送自然语言控制指令，如"关灯"、"打开主场灯光"、"大会议室空调24度"、"关闭门厅空调"、"打开孪易大屏场景一"等。
2. **自动调节模式**：video-perception-flow 在检测到人员进入某区域、**且会议匹配成功（有访客）后**，在准备推送欢迎卡片的同时，主动调用本流程并传入 `trigger_type="auto"` 参数，触发环境自动调节。

   > **关键时序**：video-perception-flow 在匹配会议成功（有访客）后，**同时**做两件事：① 推送欢迎卡片；② 触发本流程的 auto 模式立即执行环境调节。设备调节完毕后，再推送设备控制反馈卡片。
   >
   > 用户手机上仅收到两条消息：**欢迎卡片 → 设备控制反馈卡片**。灯光空调在欢迎卡片推送的同时物理执行（不是消息，是实际设备动作）。

## 必须遵守的约定

- 所有底层设备操作（灯光、空调）通过 MQTT / HTTP API 调用外部接口完成，本 Skill 不直接操作硬件。
- **孪易大屏指令不在本 Skill 执行**：识别出孪易大屏 / 场景 / 对象 / 视频类指令后，将**用户原始输入**通过 IM 转发给 `ar01@im.tuguan.net`（部署了 ruisi-twinioc-command-skill 的 Agent），由其完成识别与下发。本 Skill 不维护孪易指令库，也不直连孪易接口。转发后仅回用户一句"孪易交互指令已转发给AR01"，不等待、不回传执行结果——物理大屏画面变化即为反馈。
- 自动调节模式中，环境数据查询失败或设备调用失败不应中断流程，仅发送提醒消息给 P01。
- 用户指令必须通过语义解析确认，不得直接执行未解析的原始文本。
- 留痕目录和 `manifest.json` 必须生成。
- **触发时序**：auto 模式由 video-perception-flow 在会议匹配成功（有访客）后**同时**触发（推送欢迎卡片 + 触发环境调节）。灯光空调在推送欢迎卡片的同时物理执行，设备控制反馈卡片在调节完成后推送。用户手机上仅收到两条消息：**欢迎卡片 → 设备控制反馈卡片**。

## 输入参数

| 参数名          | 类型    | 必填 | 说明                                                                                                                           |
| --------------- | ------- | ---- | ------------------------------------------------------------------------------------------------------------------------------ |
| `trigger_type`  | string  | 否   | `"user"`（用户指令，默认）或 `"auto"`（自动环境调节）                                                                          |
| `user_text`     | string  | 条件 | 当 `trigger_type="user"` 时必填，用户原始自然语言指令                                                                          |
| `zone`          | string  | 条件 | 当 `trigger_type="auto"` 时必填，需要调节的区域。当 `trigger_type="user"` 时可选（可从用户指令中提取，或从 current_zone 获取） |
| `visitor_count` | integer | 条件 | 当 `trigger_type="auto"` 时可选，来访人数。0 或未传时表示无访客，跳过自动调节                                                  |
| `business_task` | string  | 否   | 业务任务名，用于留痕目录组织。未提供则自动生成 `auto_<uuid>`                                                                   |

## 输出参数

| 参数名       | 类型   | 说明                             |
| ------------ | ------ | -------------------------------- |
| status       | string | `success` / `failed` / `partial` |
| message      | string | 人类可读的结果描述               |
| output_files | array  | 留痕产物路径列表（可选）         |

## 执行步骤

**路由规则（避免歧义）**：

- 步骤 1 为通用初始化，所有触发类型都会执行。
- 当 `trigger_type="user"` 时，仅执行步骤 2A（用户指令分支），不执行步骤 2B。
- 当 `trigger_type="auto"` 时，仅执行步骤 2B（自动调节分支），不执行步骤 2A。
- 步骤 2A 与步骤 2B 互斥，不并行；分支结束后统一进入步骤 3（收尾）。

### 步骤 1：通用初始化

**1.1 生成 execution_id**
使用 UUID v4，格式如 `550e8400-e29b-41d4-a716-446655440000`。

**1.2 确定 business_task**

- 输入中已提供 → 直接使用
- 未提供 → 自动生成 `auto_<execution_id前8位>`（如 `auto_550e8400`）

**1.3 创建执行目录**

```
<workspace>/trace-workspace/<business_task>/<YYYYMMDD_HHMMSS>_<execution_id前8位>/
├── input/
├── artifacts/
└── output/
```

**1.4 保存输入**
若 `trigger_type="user"`，将 `user_text` 写入 `input/user_command.txt`。
若 `trigger_type="auto"`，将 zone 写入 `input/auto_trigger.json`。

**1.5 强制设置目标区域**

**当前版本固定使用大会议室**：

- 无论输入参数 `zone` 为何值，或后续解析/确认的结果如何，最终执行时统一使用 `meeting_room`
- 在步骤 2A/2B 中会正常进行区域解析和确认（保留完整逻辑），但在实际调用设备接口前会被强制覆盖为 `meeting_room`
- 此设置为临时方案，后期支持多区域时只需移除此覆盖逻辑

记录：

```
[<ISO时间>] 区域设置 | 当前版本强制使用: meeting_room（大会议室）
```

**1.6 初始化 execution.log**

```
[<ISO时间>] 总体控制流程启动 | execution_id: <id> | business_task: <task> | trigger_type: <type>
```

---

### 步骤 2A：用户指令模式（`trigger_type="user"`）

**2.1 语义解析**
利用 Agent 自身的语义理解能力解析 `user_text`，提取以下字段：

| 提取字段      | 说明                                                         | 示例             |
| ------------- | ------------------------------------------------------------ | ---------------- |
| `device_type` | 设备类型：`lighting` / `hvac` / `twinscreen`                 | `”lighting”`     |
| `action`      | 控制动作：`on`(开) / `off`(关) / `set_temperature`(设置温度) | `”on”`           |
| `value`       | 参数值（可选），如温度数值、设备ID、场景名称                 | `24`             |
| `zone`        | 区域（可选），从指令文本中提取                               | `”meeting_room”` |

**记录 execution.log**：

```
[<ISO时间>] LLM解析结果 | device_type: <type> | action: <action> | zone: <zone>
```

**解析失败处理**：
若无法解析 `device_type` 或 `action`，向 P01 返回错误提示：

> "抱歉，未能理解您的控制指令，请说明要控制什么设备（灯光/空调/大屏）以及什么操作（开/关/调温度等）。"

状态标记为 `failed`，跳至步骤 3。

**2.2 区域确认**

**2.2.1 读取 current_zone**
若用户指令中未提及区域（解析结果 zone 为空），读取 `<workspace>/trace-workspace/current_context.json`：

```json
// current_context.json 格式
{ "current_zone": "meeting_room" }
```

- 文件存在且含有效值 → 使用该值作为默认区域
- 文件不存在或值无效 → 进入 2.2.2 区域选择流程

**2.2.2 推送区域选择卡片**
若 zone 仍为空，构造区域选择卡片，向 P01 推送：

> "请问针对哪个区域进行操作？"
> **1**=门厅　**2**=大会议室　**3**=主场

等待用户回复，收到后更新 `zone`。

记录到 execution.log：

```
[<ISO时间>] 区域确认 | 用户选择: <区域中文名>
```

**2.2.3 强制覆盖为大会议室**

**当前版本限制**：无论上述步骤解析或确认的 zone 是什么，强制设置为 `meeting_room`。

```
zone = "meeting_room"  // 强制覆盖
```

记录：

```
[<ISO时间>] 区域覆盖 | 原值: <原zone> | 强制设为: meeting_room
```

**2.3 构建设备控制请求**
根据 `device_type`、`action`、`value`、`zone`（此时已是 meeting_room），按以下规则构造请求体：

**照明控制（device_type="lighting"）**

调用 `mqtt_controller.py` 时的 JSON 格式：

| 用户意图       | JSON 参数                                                                                                    |
| -------------- | ------------------------------------------------------------------------------------------------------------ |
| 打开区域所有灯 | `{"device_type":"lighting", "zone":"meeting_room", "action":"on", "all":true}`                               |
| 打开指定设备   | `{"device_type":"lighting", "zone":"meeting_room", "action":"on", "device_ids":["light_001"], "all":false}`  |
| 关闭区域所有灯 | `{"device_type":"lighting", "zone":"meeting_room", "action":"off", "all":true}`                              |
| 关闭指定设备   | `{"device_type":"lighting", "zone":"meeting_room", "action":"off", "device_ids":["light_001"], "all":false}` |

**空调控制（device_type="hvac"）**

调用 `mqtt_controller.py` 时的 JSON 格式：

| 用户意图         | JSON 参数                                                                                                                           |
| ---------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 开空调（所有）   | `{"device_type":"hvac", "zone":"meeting_room", "action":"on", "all":true}`                                                          |
| 开空调（指定）   | `{"device_type":"hvac", "zone":"meeting_room", "action":"on", "device_ids":["ac_001"], "all":false}`                                |
| 关空调（所有）   | `{"device_type":"hvac", "zone":"meeting_room", "action":"off", "all":true}`                                                         |
| 关空调（指定）   | `{"device_type":"hvac", "zone":"meeting_room", "action":"off", "device_ids":["ac_001"], "all":false}`                               |
| 设置温度（所有） | `{"device_type":"hvac", "zone":"meeting_room", "action":"set_temperature", "temperature":24, "all":true}`                           |
| 设置温度（指定） | `{"device_type":"hvac", "zone":"meeting_room", "action":"set_temperature", "temperature":24, "device_ids":["ac_001"], "all":false}` |
| 空调24度（组合） | 先调用 `action:"on"` 打开空调，再调用 `action:"set_temperature", temperature:24` 设温度                                             |

**孪易大屏控制（device_type="twinscreen"）**

> **本类指令不在本 Skill 执行，转发给 ar01。**

识别到孪易大屏 / 场景 / 对象 / 视频类意图（关键词：大屏、场景、层级、楼层、下一层/上一层、视野、图层、图表、聚焦、选中、搜索对象、主题、**主题生成、生成、统计、创建、分析、报告/report**、告警、摄像头、视频、回放、云台等）时，**不做参数解析、不查本地接口**，直接把**用户原始输入**转发给 `ar01@im.tuguan.net`：

> **C02 主题生成（动词触发，内容为自由文本）**：当用户说"生成XX""统计XX""创建XX""分析XX"或英文 `generate / statistics / create / analyze / report` 时，属于孪易主题生成（C02）意图，**同样转发给 ar01**。要点：
> - **靠动词触发，不靠"主题"二字**——仅凭"主题"关键词会漏判。
> - **XX 是自由文本，不要求是具体设备对象**——如"统计一下园区情况""分析本月告警趋势""生成环境监测主题"都成立，"园区情况"这类宽泛短语正是 C02 该接的内容，**不可因为"找不到具体设备/对象"而判定无法处理或拦截**。C02 在 ar01 侧不做实体名校验。
> - 是否生成 C02 指令串、与 C01 的优先级判断（C02 > C01）全部由 ar01 的 ruisi-twinioc-command-skill 完成，本 Skill 只负责识别意图并原样转发。

```bash
curl -sX POST http://127.0.0.1:18900/send \
  -H "Content-Type: application/json" \
  -d '{"jid":"ar01@im.tuguan.net","body":"<用户原始输入>","from":"a01@im.tuguan.net"}'
```

- `body` 为用户原话（如"切换到楼层20并聚焦环境传感器1"），**不要**改写成编码指令串——识别与生成由 ar01 完成。
- `from` 固定 `a01@im.tuguan.net`；ar01 依据此 JID 直接执行、免确认、不回传。
- **不传孪易 token**：a01 不持有孪易场景 token，转发消息里也不带 token。下发所需的场景 token 由 ar01 侧**预先绑定**（当前方案）。若 ar01 未绑定 token，指令不会下发——需先给 ar01 绑定 token。
- 转发成功后，仅向用户回一句固定反馈：`孪易交互指令已转发给AR01`。
- 转发是孪易分支的**终点**：不等待 ar01 回复、不解析执行结果，物理大屏即反馈。随后进入步骤 2.6 留痕。

若 `curl` 调用本身失败（连接 `/send` 失败），重试 1 次；仍失败标记 `partial` 并提示用户"转发失败，请稍后重试"。

**2.4 调用设备接口**
使用 `exec` + Python 脚本发送 MQTT 控制指令。**本步骤仅适用于 lighting / hvac**；twinscreen 已在 2.3 转发给 ar01，不进入本步骤。

**MQTT Broker**：`60.204.215.30:1883`（需要认证：twinioc/hefgwGkuzPdEhmo2）

**接口协议**：

| 设备类型 | Topic                          | 消息格式                                 | 说明     |
| -------- | ------------------------------ | ---------------------------------------- | -------- |
| 灯光     | `office/control/light`         | `{"devsId":"设备ID", "status":"on/off"}` | 开关灯   |
| 空调开关 | `office/control/wkq`           | `{"devsId":"设备ID", "status":"on/off"}` | 开关空调 |
| 空调温度 | `office/control/{设备ID}/temp` | 温度值（字符串）                         | 设置温度 |

**调用示例**：

```bash
# 开灯
python scripts/mqtt_controller.py '{ "device_type":"lighting", "zone":"meeting_room", "action":"on", "all":true }'

# 开空调
python scripts/mqtt_controller.py '{ "device_type":"hvac", "zone":"meeting_room", "action":"on", "all":true }'

# 设置温度
python scripts/mqtt_controller.py '{ "device_type":"hvac", "zone":"meeting_room", "action":"set_temperature", "temperature":24, "all":true }'
```

**超时**：5 秒。**重试**：失败后重试 1 次。

记录 execution.log：

```
[<ISO时间>] 设备调用 | type: <device_type> | zone: meeting_room | action: <action> | status: success
```

**2.4 等待并解析响应**

- HTTP 状态 200 且 `success: true` → 继续
- 连接失败或超时 → 重试一次；仍失败则标记 `partial`，继续到步骤 2.5

**2.5 用户反馈**

当前版本固定使用大会议室，反馈目标为：**P01（手持Pad） + P02（大会议室大屏）**

通过 HTTP POST 到 `http://127.0.0.1:18900/send` 发送消息：

- HTTP 方法: `POST`
- Content-Type: `application/json`
- 请求体: `{"jid": "<设备JID>", "body": "<反馈文本>", "from": "a01@im.tuguan.net"}`
- 测试阶段：所有推送统一发送至 `niujunke@im.tuguan.net`

**反馈消息模板**：

| 场景         | 消息模板                                                 |
| ------------ | -------------------------------------------------------- |
| 开灯成功     | `"已为您打开大会议室的灯光。"`                           |
| 关灯成功     | `"已为您关闭大会议室的灯光。"`                           |
| 调温成功     | `"已将大会议室空调设置为{value}℃。"`                     |
| 孪易指令转发 | `"孪易交互指令已转发给AR01"`                             |
| 执行失败     | `"抱歉，大会议室{设备名}控制指令执行失败，请稍后重试。"` |

**2.6 记录留痕**
将执行结果写入 `artifacts/control_result.json`：

```json
{
  "mode": "user",
  "user_text": "大会议室关灯",
  "parsed": {
    "device_type": "lighting",
    "action": "turn_off",
    "value": null,
    "zone": "meeting_room"
  },
  "api_requests": [
    {
      "url": "http://127.0.0.1:18900/api/lighting/control",
      "body": { "zone": "meeting_room", "all": true, "action": "turn_off", "params": {} },
      "response": { "success": true, "message": "指令已执行" }
    }
  ],
  "feedback_sent_to": ["P01", "P02"],
  "feedback_messages": ["已为您关闭大会议室灯光。"]
}
```

---

### 步骤 2B：自动调节模式（`trigger_type="auto"`）

**3.0 会议校验**
检查 `visitor_count` 参数：

- 若 `visitor_count` 为 0 或未提供 → 判定为无访客或内部人员路过，**跳过自动调节**，记录日志：
  ```
  [<ISO时间>] 会议校验 | 无访客，跳过自动调节
  ```
  标记为 `noop`，跳至步骤 3。
- 若 `visitor_count > 0` → 有访客到访，继续执行自动调节。

记录：

```
[<ISO时间>] 会议校验 | visitor_count: <N> | 有<来访人数>人到访，执行自动调节
```

**3.0.1 强制覆盖为大会议室**

**当前版本限制**：无论输入参数 `zone` 是什么，强制设置为 `meeting_room`。

```
zone = "meeting_room"  // 强制覆盖
```

记录：

```
[<ISO时间>] 区域覆盖 | 原值: <原zone> | 强制设为: meeting_room
```

**3.1 执行固定调节动作**

自动调节模式触发后，固定执行以下操作（不再查询环境数据或判断温度阈值）：

1. **开启灯光**：打开大会议室的所有灯光
2. **开启空调并设置温度**：打开大会议室空调并设置为 24°C

**zone 固定使用 `meeting_room`**（大会议室）。

**3.2 调用设备接口**

按顺序调用以下设备接口（使用真实 MQTT 接口，与步骤 2.2 相同）：

**① 开启灯光**

```bash
python scripts/mqtt_controller.py '{"device_type":"lighting","zone":"meeting_room","action":"on","all":true}'
```

记录：

```
[<ISO时间>] 设备调用 | type: lighting | zone: meeting_room | action: on | status: success
```

**② 开启空调**

```bash
python scripts/mqtt_controller.py '{"device_type":"hvac","zone":"meeting_room","action":"on","all":true}'
```

记录：

```
[<ISO时间>] 设备调用 | type: hvac | zone: meeting_room | action: on | status: success
```

**③ 设置空调温度为 24°C**

```bash
python scripts/mqtt_controller.py '{"device_type":"hvac","zone":"meeting_room","action":"set_temperature","temperature":24,"all":true}'
```

记录：

```
[<ISO时间>] 设备调用 | type: hvac | zone: meeting_room | action: set_temperature | temperature: 24 | status: success
```

**超时与重试**：

- 每个接口调用超时 5 秒
- 失败后重试 1 次
- 若某设备调用失败，记录警告但继续执行后续操作
- 全部失败则标记为 `partial`

**3.3 用户反馈**
**P01（移动端）始终发送反馈消息**。同时，根据 zone 向对应大屏设备发送（规则同步骤 2.6）。

**消息模板**：

```
"已为您开启{区域中文名}的灯光和空调（24℃）。如需调整，可随时告诉我。"
```

**推送方式**：通过 HTTP POST 到 `http://127.0.0.1:18900/send` 发送消息（与步骤 2.6 相同）。

**3.4 记录留痕**
将调节动作写入 `artifacts/auto_adjustment.json`：

```json
{
  "mode": "auto",
  "zone": "meeting_room",
  "visitor_count": 3,
  "actions": [
    { "device_type": "lighting", "action": "on", "status": "success" },
    { "device_type": "hvac", "action": "on", "status": "success" },
    { "device_type": "hvac", "action": "set_temperature", "temperature": 24, "status": "success" }
  ],
  "feedback_sent_to": ["P01", "P02"],
  "feedback_message": "已为您开启大会议室的灯光和空调（24℃）。如需调整，可随时告诉我。"
}
```

---

### 步骤 3：生成 manifest.json

写入执行目录根路径：

```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "business_task": "auto_550e8400",
  "skill_name": "overall-control",
  "version": "1.0.0",
  "start_time": "2026-06-04T14:00:00+08:00",
  "end_time": "2026-06-04T14:00:03+08:00",
  "status": "success",
  "trigger_type": "user",
  "input": {
    "user_text": "大会议室关灯"
  },
  "output_files": [{ "path": "output/control_result.json", "size_bytes": 512 }],
  "error": null
}
```

### 步骤 4：将 artifacts 移动至 output 目录

---

### 步骤 5：返回结果

返回 `{"status": <status>, "message": <message>, "output_files": [...]}`。

---

## 错误处理

| 错误场景                     | 处理方式                               |  status  |
| ---------------------------- | -------------------------------------- | :------: |
| LLM 无法解析用户指令         | 向 P01 返回错误提示                    |  failed  |
| 设备接口连接失败             | 重试 1 次，仍失败标记                  | partial  |
| 执行目录创建失败             | 立即终止                               |  failed  |
| business_task 含非法字符     | 自动过滤（仅保留小写字母+数字+连字符） | 继续执行 |
| 设备类型不支持的操作         | 提示用户该设备不支持此操作             |  failed  |
| 反馈推送失败                 | 记录日志，不影响主流程 status          | 继续执行 |
| 自动调节模式设备全部调用失败 | 发送提醒，标记为 partial               | partial  |

---

## 安全与权限

- **数据读取**：仅限于 `<workspace>/trace-workspace/` 目录下的上下文文件（`current_context.json`）
- **数据写入**：仅限于 `<workspace>/trace-workspace/<business_task>/` 目录
- **设备控制**：仅通过 HTTP API 调用外部接口，不直接操作硬件
- **区域映射**：从引用文档 `references/zone-device-mapping.md` 读取
- **推送目标**：测试阶段统一通过 HTTP API 发送至 `niujunke@im.tuguan.net`，使用标识 `from: a01@im.tuguan.net`
- **敏感操作**：灯光/空调/大屏控制均为可逆操作，不涉及数据销毁

---

## 留痕要求

| 文件/目录                        | 必选 | 说明                                 |
| -------------------------------- | :--: | ------------------------------------ |
| `manifest.json`                  |  ✅  | 执行元数据                           |
| `execution.log`                  |  ✅  | 文本日志，`[ISO时间] 事件` 格式      |
| `input/user_command.txt`         |  ⚠️  | 用户指令模式，保存原始 user_text     |
| `input/auto_trigger.json`        |  ⚠️  | 自动调节模式，保存 zone              |
| `artifacts/control_result.json`  |  ⚠️  | 用户指令模式，保存解析结果与反馈记录 |
| `artifacts/auto_adjustment.json` |  ⚠️  | 自动调节模式，保存环境数据与调节记录 |
| `output/`                        |  ✅  | 最终产物（从 artifacts 移动）        |

---

## 交互模式

### 交互点 1：区域确认（选择型）

- **触发时机**：用户指令模式中，zone 无法从指令或 current_zone 确定
- **提示语模板**：
  > "请问针对哪个区域进行操作？"
  > **1**=门厅　**2**=大会议室　**3**=主场
- **有效选项**：`1` / `2` / `3`
- **默认值**：无（必须选择）
- **无效输入处理**：重新提示选项列表
- **反馈接收设备**：P01（手持 Pad）

### 交互点 2：孪易大屏指令（无本地交互，转发 ar01）

- **触发时机**：用户指令涉及孪易大屏 / 场景 / 对象 / 视频类操作，**含主题生成类（生成/统计/创建/分析/report 等动词触发的 C02 意图）**。
- **处理方式**：本 Skill **不在本地解析参数、不向用户追问**，直接把用户原始输入转发给 `ar01@im.tuguan.net`（见步骤 2.3）。参数缺失、实体名匹配、缺参追问等全部由 ar01 的 ruisi-twinioc-command-skill 处理。
- **用户反馈**：转发成功后仅回一句 `孪易交互指令已转发给AR01`。

---

## 参考文件

| 文件              | 路径                                                               |
| ----------------- | ------------------------------------------------------------------ |
| 区域-设备映射表   | `references/zone-device-mapping.md`                                |
| 设备控制 API 约定 | `references/device-control-api.md`                                 |
| 环境数据模拟格式  | `references/environment-data-format.md`                            |
| 当前上下文        | `../../trace-workspace/current_context.json`（由视频感知流程维护） |

---

## 示例

### 示例 1：用户指令"大会议室关灯"

**输入**：

```json
{
  "trigger_type": "user",
  "user_text": "大会议室关灯"
}
```

**处理流程**：

1. 语义解析 → `{device_type: "lighting", action: "turn_off", zone: "meeting_room"}`
2. zone 已确定，跳过区域确认
3. 调用 `/api/lighting/control`：`{"zone":"meeting_room","all":true,"action":"turn_off","params":{}}`
4. 向 P01 + P02 发送：`"已为您关闭大会议室灯光。"`

**输出**：

```json
{
  "status": "success",
  "message": "已为您关闭大会议室灯光。"
}
```

### 示例 2：自动调节（大会议室，有访客）

**输入**：

```json
{
  "trigger_type": "auto",
  "zone": "meeting_room",
  "visitor_count": 3,
  "business_task": "visit-zhihuiyun"
}
```

**处理流程**：

1. 会议校验：visitor_count=3 > 0，执行自动调节
2. 开启灯光：调用 lighting 接口，action=on
3. 开启空调：调用 hvac 接口，action=on
4. 设置温度：调用 hvac 接口，set_temperature=24
5. 向 P01 + P02 发送：`"已为您开启大会议室的灯光和空调（24℃）。如需调整，可随时告诉我。"`

**输出**：

```json
{
  "status": "success",
  "message": "环境已自动调节"
}
```

### 示例 3：用户指令"关灯"（未指定区域）

**输入**：

```json
{
  "trigger_type": "user",
  "user_text": "关灯"
}
```

**处理流程**：

1. 语义解析 → `{device_type: "lighting", action: "turn_off", zone: null}`
2. 读取 `current_context.json` → 无有效值
3. 向 P01 推送区域选择卡片："1=门厅 2=大会议室 3=主场"
4. 用户选择"2"
5. 调用接口 + 向 P01+P02 发送反馈

**输出**：

```json
{
  "status": "success",
  "message": "已为您关闭大会议室灯光。"
}
```

### 示例 4：自动调节（主场，有访客）

**输入**：

```json
{
  "trigger_type": "auto",
  "zone": "main_hall",
  "visitor_count": 5
}
```

**处理流程**：

1. 会议校验：visitor_count=5 > 0，执行自动调节
2. 开启灯光：调用 lighting 接口，action=on
3. 开启空调：调用 hvac 接口，action=on
4. 设置温度：调用 hvac 接口，set_temperature=24
5. 向 P01 + P03 发送：`"已为您开启主场的灯光和空调（24℃）。如需调整，可随时告诉我。"`

**输出**：

```json
{
  "status": "success",
  "message": "环境已自动调节"
}
```
