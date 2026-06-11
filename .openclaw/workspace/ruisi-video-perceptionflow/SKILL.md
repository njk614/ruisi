---
name: ruisi-video-perceptionflow
description: 接收 ae01@im.tuguan.net 上报的人员检测事件（zone, timestamp, total_count），直接执行：查询会议信息 → 匹配客户画像 → 按人数生成欢迎卡片 → 推送至展示设备 → 并行触发环境自动调节（灯光/空调）。所有流程在此 Skill 内完成，不依赖 SubAgent。
version: 1.1.0
author: 王杉杉
level: L1
allowed-tools:
  - read_file
  - write_file
  - sessions_send
metadata:
  openclaw:
    emoji: '🎥'
    requires:
      bins: []
      config: []
      env: []
dependencies: []
---

# 视频感知流程（简化版）

> **设计说明**：本版本为简化版，所有业务逻辑（数据读取、会议匹配、模板渲染、设备推送）由主 Agent 直接执行，不依赖 SubAgent 分层。

## 触发条件

1. **接收人员检测事件**：Skill 接收到事件消息本身为 JSON 对象时自动触发。
   - **输入格式**：直接接收事件 JSON，不要求外层 `jid` / `from` / `body` 包裹。
   - **事件格式**：
     ```json
     {
       "event": "enter",
       "zone": "meeting_room",
       "timestamp": "2026-06-02T19:48:15+08:00",
       "total_count": 1
     }
     ```
   - **参数说明**：
     | 字段 | 说明 |
     |------|------|
     | `event` | 事件类型，当前按 `enter` 触发 |
     | `zone` | 检测区域标识 |
     | `timestamp` | 检测时间，ISO 8601 格式 |
     | `total_count` | 检测到的总人数，整数且 `>= 0` |

2. **严格触发判定（必须同时满足）**：

- 输入消息本身是合法 JSON 对象
- `event == "enter"`
- 包含 `zone`、`timestamp`、`total_count`
- `timestamp` 为 ISO 8601 格式，`total_count` 为整数且 `>= 0`

3. **不满足触发条件时的处理**：

- 不执行本 Skill 的后续步骤
- 记录一条 `ignored_event` 日志（原因：事件类型不匹配 / 字段缺失 / JSON 非法）

---

## 必须遵守的约定

- **主 Agent 直接执行所有操作**：数据读取、匹配逻辑、模板渲染、结果输出均由主 Agent 依次完成，不再委托 SubAgent。
- **必须生成 manifest.json**：每次执行结束时生成执行清单。
- **business_task 自动生成**：若输入参数未提供 business_task，自动生成默认值。
- **匹配不上不硬推**：无匹配会议或纯内部会议 → 状态 noop，不生成欢迎卡片。

---

## 输入参数

| 参数名        | 类型    | 必填 | 说明                                                                            |
| ------------- | ------- | ---- | ------------------------------------------------------------------------------- |
| event         | string  | 是   | 事件类型，当前仅处理 `enter`                                                    |
| business_task | string  | 否   | 业务任务名（推荐提供，如 `zhihuiyun-20260615`）；未提供则自动生成 `auto_<uuid>` |
| zone          | string  | 是   | 检测区域标识（如 `digital-twin-east` / `meeting-room-large` / `entrance`）      |
| timestamp     | string  | 是   | 检测时间，ISO 8601 含时区，如 `2026-06-15T14:01:00+08:00`                       |
| total_count   | integer | 是   | 检测到的总人数                                                                  |

**输入示例**：

```json
{
  "event": "enter",
  "zone": "digital-twin-east",
  "timestamp": "2026-06-15T14:01:00+08:00",
  "total_count": 6
}
```

---

## 输出参数

| 参数名        | 类型   | 说明                                           |
| ------------- | ------ | ---------------------------------------------- |
| status        | string | success / failed / partial / noop              |
| message       | string | 人类可读的结果描述                             |
| welcome_card  | object | **可选**。欢迎卡片内容（文本、目标设备、备注） |
| manifest_path | string | manifest.json 的绝对路径                       |

**status 取值**：

- `success` — 欢迎卡片已生成并推送
- `failed` — 不可恢复错误
- `partial` — 部分成功（如推送失败但卡片已生成）
- `noop` — 无需操作（内部会议 / 无匹配会议）

---

## 执行步骤

### 步骤 1：初始化

**1.1 生成 execution_id**
使用 UUID v4，格式如 `550e8400-e29b-41d4-a716-446655440000`。

**1.2 确定 business_task**

- 输入中已提供 → 直接使用
- 未提供 → 自动生成 `auto_<execution_id前8位>`（如 `auto_550e8400`）

**1.3 创建执行目录**

```
workspace/trace-workspace/<business_task>/<YYYYMMDD_HHMMSS>_<execution_id前8位>/
├── input/
├── artifacts/
└── output/
```

初始化 `execution.log`，记录启动时间。

**1.4 保存输入**
将完整事件 JSON 写入 `input/event.json`。

---

### 步骤 2：读取并匹配会议

**2.1 读取会议数据**
每次触发本 Skill 时，均重新读取 `~/.openclaw/workspace/SimulatedData/meetings.json`，解析为 JSON 数组；不使用跨次触发缓存。匹配到会议后必须保留会议记录中的 `booking_id`，用于步骤 4 定位已预置的客户画像。

**2.2 按 zone + timestamp 匹配**

- 按 `zone` 精确匹配
- 从 `time_range`（如 `"2026-06-15 14:00~15:30"`）解析日期和起止时间
- **开始时间提前 30 分钟**作为有效匹配窗口起点（以防客户提前到达）。即将 `time_range` 起始时间减去 30 分钟后，判定 event timestamp 是否落在 `[开始时间 - 30min, 结束时间]` 范围内

**结果判断**：

- ✅ 匹配成功 → 记录会议信息，提取并保存 `booking_id`（建议保存为 `matched_booking_id`）供步骤 4 使用，进入步骤 3
- ❌ 无匹配 → 写入 `artifacts/noop_reason.json`（reason: `no_matching_meeting`），跳至步骤 6

---

### 步骤 3：校验场景

**3.1 人数校验**
比较 `total_count` 与 `internal_staff + visitor_count`：

- 若 `total_count < 预期` → 记录警告："检测{total_count}人，预期{预期}人，部分人未到齐"，**不阻断流程**
- 若 `total_count > 预期` → 记录警告："检测{total_count}人，预期{预期}人，可能临时加人入会"，**不阻断流程**

**3.2 判断是否需要欢迎语**

- `visitor_count == 0` → 纯内部会议 → 写入 `artifacts/noop_reason.json`（reason: `internal_meeting`），跳至步骤 6
- `visitor_count > 0` → 继续步骤 4

---

### 步骤 4：查询客户画像并生成欢迎卡片

**4.1 读取客户画像**
客户画像统一从 `~/.openclaw/workspace/SimulatedData/PresetMeetingData/` 下按 `booking_id` 定位，不再从 `profiles/` 目录按 `customer_company` 模糊匹配。流程如下：

1. 使用步骤 2 已保存的 `matched_booking_id`（即匹配会议记录中的 `booking_id`）。若匹配会议记录没有 `booking_id`，按“客户画像文件不存在”处理。
2. 读取并解析 `~/.openclaw/workspace/SimulatedData/PresetMeetingData/meeting_index.json`。该文件结构固定为：
   ```json
   {
     "version": "1.0",
     "description": "已预置会议数据的索引文件，用于快速定位指定会议的客户画像与演示脚本",
     "meetings": [
       {
         "booking_id": "M20260613_002",
         "meeting_topic": "孪易案例测试",
         "time_range": "2026-06-13 14:00~15:00",
         "meeting_region": "大会议室",
         "customer_profile_path": "./M20260613_002/customer_profile/CustomerProfile.md",
         "presentation_script_path": "./M20260613_002/PresentationScript.json"
       }
     ]
   }
   ```
3. 在 `meeting_index.json` 的 `meetings` 数组中按 `booking_id == matched_booking_id` 精确匹配会议索引记录。
4. 若 `meeting_index.json` 不存在、格式错误、`meetings` 不是数组，或没有匹配到 `booking_id`，均按“客户画像文件不存在”处理。
5. 若匹配到 `booking_id`，进入固定目录：`~/.openclaw/workspace/SimulatedData/PresetMeetingData/<booking_id>/`。
6. 在该目录下查找固定文件：`customer_profile/CustomerProfile.md`。
7. 若找到该文件，按“客户画像文件存在”处理；若未找到，按“客户画像文件不存在”处理。

- 客户画像文件存在 → 解析每位访客的职位(title)、历史来访次数(visit_count)、特殊接待需求(special)
- 客户画像文件不存在 → 记录警告，跳过个性化信息，仅用会议数据生成通用欢迎语（状态标记 partial）

**4.2 确定亲切称呼（称呼生成规则）**

对每位访客按以下优先级确定亲切称呼：

1. **优先取画像中"亲切称呼"字段**（如"张伟总""李敏总监"）
2. 若不存在则自动生成：取姓氏 + 按职位映射简称

| 职位关键词       |   简称    | 示例          |
| ---------------- | :-------: | ------------- |
| 副总裁、副总经理 |    总     | 张伟→"张总"   |
| 总监             |   总监    | 李敏→"李总监" |
| 经理             |   经理    | 王磊→"王经理" |
| 工程师           |    工     | 郑雪→"郑工"   |
| 其他             | 先生/女士 | 或保留原职位  |

**4.3 选择欢迎模板**
按 `visitor_count` 选择：
| 人数 | 模板 | 说明 |
|:----:|:----:|------|
| 1 | 1 人模板 | 含 {亲切称呼}{再次}{第N次}{会议主题} |
| 2 | 2 人模板 | 含 {亲切称呼1}{亲切称呼2}{会议主题} |
| ≥3 | 3 人+模板 | 含 {公司名称}{会议主题} |

模板内容见 `~/.openclaw/workspace/SimulatedData/templates/welcome-template.md`。

**4.4 填充动态变量**

**1 人模板变量**：

```
{亲切称呼}          = 访客的亲切称呼（优先取画像字段，否则自动生成）
{再次}              = visit_count > 1 时显示"再次"，否则为空
{这是您第N次来访}   = visit_count > 1 时显示"这是您第N次来访"，否则为空
{会议主题}          = 当前会议主题（meeting_topic）
```

**2 人模板变量**：

```
{亲切称呼1}         = 第一位访客的亲切称呼
{亲切称呼2}         = 第二位访客的亲切称呼
{会议主题}          = 当前会议主题
```

**3 人+模板变量**：

```
{公司名称}          = 客户公司完整名称（含括号，如"智云科技（北京）有限公司"）
{会议主题}          = 当前会议主题
```

**降级兜底**：若画像中无对应访客信息，使用"尊敬的客人"作为兜底。

**4.4 确定目标设备**
按 zone 查询区域-设备映射表：

| zone               | 设备 | 说明             |
| ------------------ | :--: | ---------------- |
| digital-twin-east  | P02  | 数字孪生大屏     |
| digital-twin-west  | P02  | 数字孪生大屏     |
| meeting-room-large | P02  | 大会议室大屏     |
| meeting-room-small | P01  | 手持 Pad         |
| entrance           | P01  | 手持 Pad         |
| main-hall          | P03  | 主场屏           |
| **其他**           | P01  | 兜底（记录警告） |

> **测试阶段**：无论 zone 映射结果如何，推送目标地址统一为 `niujunke@im.tuguan.net`（通过 HTTP API `/send` 发送）。设备标识（P01/P02/P03）仍保留在卡片元数据中供后续生产环境使用。

**4.5 整理备注信息**
检查所有访客的特殊接待需求（如"需要翻译"），汇总写入 `notes` 字段。

**4.6 写入产物**
将欢迎卡片写入 `artifacts/welcome_card.json`：

```json
{
  "text": "（渲染后的欢迎文本）",
  "target_device": "P02",
  "device_name": "数字孪生大屏",
  "notes": "王磊（产品经理）：客户只会英语，需要安排翻译"
}
```

---

### 步骤 5：推送欢迎卡片

将欢迎卡片内容（`welcome_card.text` 中的文本）发送至指定 JID。

**测试阶段推送地址**：统一推送至 `niujunke@im.tuguan.net`

**推送方式**：通过 HTTP API 发送

```
POST http://127.0.0.1:18900/send
Content-Type: application/json

{
  "jid": "niujunke@im.tuguan.net",
  "body": "（欢迎卡片文本内容）",
  "from": "a01@im.tuguan.net"
}
```

- 推送成功 → 记录日志
- 推送失败 → 卡片保留在 output/ 目录，状态标记为 partial

将 `artifacts/` 产物移动至 `output/`。

---

### 步骤 5.5：触发环境自动调节（并行）

在推送欢迎卡片的同时，触发总体控制流程（ruisi-overall-control）的自动调节模式。

**触发条件**：仅当 `visitor_count > 0` 时执行（非内部会议）。

**调用方式**：调用总体控制流程，传入 auto 模式参数：

```json
{
  "trigger_type": "auto",
  "zone": "<当前zone>",
  "visitor_count": <visitor_count>,
  "business_task": "<继承父级business_task>"
}
```

**时序说明**：

- 本步骤与步骤 5（推送欢迎卡片）同时触发
- 用户手机上仅收到两条消息：**①欢迎卡片 → ②设备控制反馈卡片**
- 灯光空调在①的同时物理执行（不是一条消息，是实际设备动作）
- 环境调节和设备控制反馈由 ruisi-overall-control 独立完成，本流程不等待其执行结果

**日志记录**：

```
[<ISO时间>] 触发环境自动调节 | zone: <zone> | visitor_count: <N>
```

---

### 步骤 6：生成 manifest.json

写入执行目录根路径，结构如下：

```json
{
  "execution_id": "550e8400-e29b-41d4-a716-446655440000",
  "business_task": "auto_550e8400",
  "skill_name": "ruisi-video-perceptionflow",
  "version": "1.1.0",
  "start_time": "2026-06-15T14:01:00+08:00",
  "end_time": "2026-06-15T14:01:05+08:00",
  "status": "success",
  "input": {
    "zone": "digital-twin-east",
    "timestamp": "2026-06-15T14:01:00+08:00",
    "total_count": 6
  },
  "output_files": [{ "path": "output/welcome_card.json", "size_bytes": 512 }],
  "error": null
}
```

---

### 步骤 7：返回结果

返回 `{"status", "message", "welcome_card", "manifest_path"}`。

---

## 错误处理

| 场景                             | 处理方式                                   |  status  |
| -------------------------------- | ------------------------------------------ | :------: |
| `meetings.json` 不存在或格式错误 | 记录错误日志，终止                         |  failed  |
| 客户画像文件缺失                 | 用会议数据生成通用欢迎语，记录警告         | partial  |
| 目标设备推送不可达               | 卡片仅保存不推送，记录原因                 | partial  |
| 执行目录无法创建                 | 立即终止                                   |  failed  |
| 模板文件缺失                     | 使用硬编码的默认模板文本（见下方兜底模板） | partial  |
| business_task 含非法字符         | 自动过滤（小写字母+数字+连字符）           | 继续执行 |

**兜底模板（模板文件缺失时使用）：**

- **1 人**：`尊敬的{亲切称呼}您好，欢迎{再次}来到数字冰雹！{这是您第N次来访}今天的「{会议主题}」即将开始。祝您本次会谈顺利！`
- **2 人**：`尊敬的{亲切称呼1}、{亲切称呼2}您好，欢迎来到数字冰雹！今天的「{会议主题}」即将开始。祝您二位会谈顺利！`
- **3 人+**：`尊敬的{公司名称}各位来宾，欢迎来到数字冰雹！今天的「{会议主题}」即将开始。祝本次会谈顺利！`

---

## 安全与权限

- **数据读取**：仅限于 `~/.openclaw/workspace/SimulatedData/` 目录下的预置文件
- **数据写入**：仅限于 `trace-workspace/<business_task>/` 目录
- **消息接收**：来自 ae01@im.tuguan.net 的事件消息，通过 `POST http://127.0.0.1:18900/send` 接收
- **设备推送**：测试阶段通过 `POST http://127.0.0.1:18900/send` 推送至 `niujunke@im.tuguan.net`，from 为 `a01@im.tuguan.net`
- **敏感信息**：访客个人信息仅用于欢迎卡片，不持久化到 trace 目录外

---

## 留痕要求

| 文件/目录                     | 必选 | 说明                                              |
| ----------------------------- | :--: | ------------------------------------------------- |
| `manifest.json`               |  ✅  | 执行元数据                                        |
| `execution.log`               |  ✅  | 文本日志，`[时间] 事件` 格式                      |
| `input/event.json`            |  ✅  | 原始输入                                          |
| `artifacts/`                  |  ✅  | 中间产物（welcome_card.json 或 noop_reason.json） |
| `artifacts/auto_trigger.json` |  ⚠️  | 当有访客时，记录触发总体控制流程 auto 模式的参数  |
| `output/`                     |  ✅  | 最终产物                                          |

---

## 交互模式

### 交互点：推送确认（确认型）

- **触发时机**：仅在手动调试模式下，欢迎卡片生成后、推送前
- **提示语模板**：
  > 检测到访客到达 **{zone}**，已生成欢迎卡片。是否推送至 **{target_device}**？
  > **Y** 推送　**N** 取消　**P** 仅保存
- **默认值**：关闭（自动触发场景不等待人工确认）
- **说明**：
  - 自动触发（来自 `ae01@im.tuguan.net`）时，直接执行步骤 5 的推送逻辑。
  - 仅当显式开启手动调试模式时，才启用 Y/N/P 交互确认。

---

## 参考文件

| 文件          | 路径                                                                                                     |
| ------------- | -------------------------------------------------------------------------------------------------------- |
| 会议预订数据  | `~/.openclaw/workspace/SimulatedData/meetings.json`                                                      |
| 会议索引      | `~/.openclaw/workspace/SimulatedData/PresetMeetingData/meeting_index.json`                               |
| 欢迎模板      | `~/.openclaw/workspace/SimulatedData/templates/welcome-template.md`                                      |
| 客户画像      | `~/.openclaw/workspace/SimulatedData/PresetMeetingData/<booking_id>/customer_profile/CustomerProfile.md` |

---

## 示例

### 示例 1：智云科技 4 人到访（3 人+模板）

**输入**：

```json
{
  "zone": "digital-twin-east",
  "timestamp": "2026-06-15T14:01:00+08:00",
  "total_count": 6
}
```

**欢迎语输出**：

```json
{
  "status": "success",
  "message": "欢迎卡片已推送至 P02（数字孪生大屏）",
  "welcome_card": {
    "text": "尊敬的智云科技（北京）有限公司各位来宾，欢迎来到数字冰雹！今天的「数字孪生平台演示与技术交流」即将开始。祝本次会谈顺利！我是你们的智能助手宝宝，有任何需要随时呼我~ [查看会议议程]",
    "target_device": "P02",
    "device_name": "数字孪生大屏",
    "notes": "王磊（产品经理）仅会英语，请安排翻译陪同参观"
  }
}
```

---

### 示例 2：天启科技 1 人到访（1 人模板，第 3 次来访）

**输入**：

```json
{
  "zone": "digital-twin-west",
  "timestamp": "2026-06-10T10:05:00+08:00",
  "total_count": 2
}
```

**欢迎语输出**：

```json
{
  "status": "success",
  "message": "欢迎卡片已推送至 P02（数字孪生大屏）",
  "welcome_card": {
    "text": "尊敬的陈浩总您好，欢迎再次来到数字冰雹！这是您第3次来访。今天的「边缘计算与数字孪生融合方案交流」即将开始。祝您本次会谈顺利！我是您的智能助手宝宝，有任何需要随时呼我~ [查看会议议程]",
    "target_device": "P02",
    "device_name": "数字孪生大屏",
    "notes": ""
  }
}
```

---

### 示例 3：内部会议（不生成）

**输入**：

```json
{
  "zone": "meeting-room-small",
  "timestamp": "2026-06-05T14:00:00+08:00",
  "total_count": 3
}
```

**输出**：

```json
{
  "status": "noop",
  "message": "纯内部会议（OPP项目评审会），无需生成欢迎语"
}
```

---

### 示例 4：未匹配到会议

**输入**：

```json
{
  "zone": "entrance",
  "timestamp": "2026-06-05T10:00:00+08:00",
  "total_count": 2
}
```

**输出**：

```json
{
  "status": "noop",
  "message": "在 entrance 区域未匹配到任何会议"
}
```
