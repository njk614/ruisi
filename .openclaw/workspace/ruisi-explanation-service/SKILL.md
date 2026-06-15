---
name: ruisi-explanation-service
description: 在讲解/演示进行中或开始前，接收对自动讲解流程的播放控制指令——开始（开始演示/开始讲解/播放演示）、暂停（暂停/暂停演示/停一下/先停/别讲/别放）、继续（继续/继续演示/接着讲/接着放/恢复演示）、停止（停止演示/结束演示/关闭演示/退出演示）、跳转（跳转到第N章/切换到某章节/看看第N章/播放第N章）、查询状态（演示状态/讲到哪了/推送到哪了）。演示进行中用户只说“暂停”“继续”“停一下”“接着讲”等简短控制词也应触发本 Skill，不要求说完整短语；但“停止、结束、关闭、退出”语义必须按停止演示处理，绝不能当作暂停。被触发后自动读取 meeting_index.json 定位当前大会议室会议的 PresentationScript.json，并按 push_interval 定时向 P02 推送数字人模拟消息，同时通过 HTTP 调用真实内容展示器 /api/show；也支持单段 chapters/segments 数据块转发。Use when a user starts, pauses, resumes, stops, or jumps within an automated demo/presentation sequence (including short colloquial commands while it is running, where stop/end/close must map to stop rather than pause), sends digital-human messages to P02 through XMPP, and controls the content display over HTTP.
level: L1
allowed-tools:
  - bash
  - python
---

# 讲解服务控制 Skill

## 当前定位

当前睿司数字人接口尚未完全就绪，数字人消息仍通过 P02 模拟；内容展示器已改为真实 HTTP 对接。

核心能力：

- 自动演示：用户说“开始演示”时，入口脚本读取 `meeting_index.json`，筛选“大会议室”且当前时间落在 `time_range` 内的会议，提取 `booking_id` 和 `presentation_script_path`；后台脚本读取该会议的 `PresentationScript.json`，先调用内容展示器 `/api/playlist/load`，再按 `chapters -> segments` 顺序推进，每段发送后等待该段 `push_interval` 秒。
- 演示控制：用户说“暂停”“暂停演示”“继续”“继续演示”“停止演示”“跳转到第N章”时，入口脚本向后台推送脚本写入控制命令；演示运行中单独的“暂停”默认表示暂停当前讲解演示。
- 停止语义隔离：用户说“停止”“停止演示”“结束演示”“关闭演示”等，必须按停止演示处理，不能归到暂停演示。
- 控制优先：OpenClaw 收到任何消息时，若后台演示正在运行，入口脚本会先临时暂停后续推送，再解析消息语义并执行对应动作。
- 状态记录：后台脚本把当前发送到第几章第几段写入 `runtime/demo_state.json`。
- 强制暂停：入口脚本会写入 `runtime/demo_pause.flag`，后台脚本在发送前、两条消息之间、等待下一段时都会检查它。
- 单段转发：仍支持手动输入 `chapters -> segments` 数据块，立即向 P02 发送数字人消息，并向内容展示器调用 `/api/show`。

Skill 真实调用内容展示器 HTTP API；数字人仍通过 P02/XMPP 模拟。

## 触发条件

当用户在 OpenClaw 聊天界面输入以下任意内容时触发：

1. 演示/讲解控制类自然语言，按意图分组（演示进行中的简短、口语控制词同样触发，**不要求用户说完整短语**）：
   - 开始类：`开始演示`、`启动演示`、`开始讲解`、`启动讲解`、`播放演示`
   - 暂停类：`暂停演示`、`暂停讲解`、`暂停`、`先停`、`停一下`、`别讲`、`别放`
   - 继续类：`继续演示`、`继续讲解`、`继续`、`接着讲`、`接着放`、`恢复演示`、`恢复播放`
   - 停止类：`停止演示`、`停止讲解`、`结束演示`、`关闭演示`、`退出演示`、`停止`
   - 跳转类：`跳转到第N章`、`切换到〈章节标题〉`、`看看第N章`、`播放第N章`（支持中文数字，如“第七章”）
   - 状态类：`演示状态`、`当前演示`、`讲到哪`、`推送到哪`

   语义边界（务必区分暂停与停止）：演示运行中短指令 `暂停`、`先停`、`停一下`、`别讲`、`别放` 一律按暂停演示处理，可被 `继续` 恢复；而 `停止`、`停止演示`、`结束演示`、`关闭演示`、`退出演示` 等带有“停止/结束/关闭/退出”语义的表达必须按停止演示处理，触发清理退出并调用 `/api/stop`，绝不能归为暂停。
2. 合法 JSON，且包含 `chapters` 字段。
3. JSON 片段，形如 `"chapters": [...]`。

## 必须遵守的约定

- Skill 不直接执行转发逻辑；必须调用 `scripts/send_message.py`。
- Skill 只把用户原始输入传给脚本，并将脚本 stdout 原样作为最终回复。
- 最终回复用户时，只输出一个 JSON 对象；不要输出 Markdown 代码块、自然语言解释、日志、标题或额外空行。
- 脚本负责解析输入、识别意图、构造消息、调用 `/send`、重试和输出结果。
- 当前阶段数字人只做模拟转发；内容展示器真实调用 HTTP API。
- 自动演示后台脚本为 `scripts/run_demo_sequence.py`。
- 运行态文件写入 `runtime/`，部署包不包含运行态文件。
- 不生成 `manifest.json`，不写留痕目录。

## 执行步骤

1. 获取用户输入的原始字符串，不要自行改写字段。
2. 调用脚本，将原始输入作为 stdin 传入：

```bash
python .openclaw/workspace/skills/ruisi-explanation-service/scripts/send_message.py
```

3. 脚本按输入类型处理：
   - `开始演示`：启动 `scripts/run_demo_sequence.py` 后台进程。
   - `暂停` / `暂停演示` / `继续` / `继续演示` / `停止演示` / `跳转到第N章`：写入 `runtime/demo_command.json`，由后台脚本响应。
   - `演示状态`：读取 `runtime/demo_state.json` 并返回当前章/段状态。
   - `chapters` 数据块：给 P02 发送数字人消息，并调用内容展示器 `/api/show`。
   - 自然语言章节跳转：演示运行中写入 jump 命令，后台脚本定位目标章节第一段并继续推送。
   - 其他自然语言：无法识别时返回失败；若演示正在运行，会先临时暂停后续推送。
4. Skill 必须原样返回脚本 stdout。

## 输出

成功时只输出：

```json
{ "status": "success", "message": "讲解已推送" }
```

失败时只输出：

```json
{ "status": "failed", "message": "具体错误原因" }
```

查询演示状态时会返回：

```json
{ "status": "success", "message": "演示状态", "state": { "status": "running", "chapter_index": 0, "segment_index": 1 } }
```

> 注意：演示控制类指令（开始演示 / 暂停 / 继续 / 跳转 / 停止演示）**成功时暂不回显**——脚本静默处理，stdout 不输出任何内容，界面不向用户返回“演示已开始/已暂停/已恢复/正在跳转指定章节/演示已停止”等提示。控制相关的动作仍照常执行，只是不再返回成功提示文字。控制**失败**（如“当前没有正在运行的演示”）以及 `演示状态`、`讲解已推送` 等仍照常返回。

## 自动演示控制

### 开始演示

输入：

```text
开始演示
```

动作：

- 启动 `scripts/run_demo_sequence.py` 后台进程。
- 读取 `/home/clawd/.openclaw/workspace/SimulatedData/PresetMeetingData/meeting_index.json`。
- 筛选 `meeting_region == "大会议室"` 且当前时间落在 `time_range` 内的会议。
- 提取 `booking_id` 作为内容展示器 `playlist_id`。
- 读取该会议的 `presentation_script_path`，例如 `<booking_id>/PresentationScript.json`。
- 从第 1 章第 1 段开始推送。
- 每段向 P02 发送数字人消息、向内容展示器调用 `/api/show` 后，等待该段 `push_interval` 秒，再进入下一段。`push_interval` 为新版演示脚本必填字段，不能缺失；`duration` 只保留在数字人消息中，不再控制推送间隔。

返回：

成功时暂不回显（stdout 静默，不向界面返回“演示已开始”提示）；若启动失败则照常返回 `{ "status": "failed", "message": "..." }`。

该动作会立即触发，后台推送随后异步开始。

为避免 P02 推送先于 OpenClaw 回执出现，入口脚本会给后台推送附加一个短暂延迟，默认 2 秒。

### 暂停演示

输入示例：

```text
暂停
```

或：

```text
暂停演示
```

注意：`停止`、`停止演示`、`结束演示`、`关闭演示` 不属于暂停语义，必须走“停止演示”流程。

成功时暂不回显（stdout 静默，不向界面返回“演示已暂停”提示）；失败时照常返回失败 JSON。

动作：

- 写入 `runtime/demo_command.json`：

```json
{ "command": "pause" }
```

- 写入 `runtime/demo_pause.flag`，后台脚本会在下一次检查点立即停止后续推送。
- 后台脚本停止进入后续段落，状态变为 `paused`。

### 继续演示

输入：

```text
继续演示
```

成功时暂不回显（stdout 静默，不向界面返回“演示已恢复”提示）；失败时照常返回失败 JSON。

动作：

- 写入 `resume` 命令。
- 后台脚本从暂停位置继续。

### 跳转章节

输入：

```text
跳转到第7章
```

成功时暂不回显（stdout 静默，不向界面返回“正在跳转指定章节”提示）；若目标章节不存在等失败情况照常返回失败 JSON。

动作：

- 写入 `jump` 命令。
- 后台脚本定位到第 7 章第 1 段，从那里继续推送。
- 如果上一轮演示已经完整播放到 `completed`，但未执行“停止演示”，入口脚本会重新启动后台推送脚本，并从第 7 章第 1 段开始继续往后推送。
- completed 后跳转会严格校验目标章节；如果章节不存在，直接返回失败，不允许回退到第一章。

### 查询状态

输入：

```text
演示状态
```

返回当前后台脚本状态，例如：

```json
{
  "status": "success",
  "message": "演示状态",
  "state": { "status": "running", "chapter_index": 6, "segment_index": 0, "chapter_id": 7, "segment_id": 1, "chapter_topic": "华为战略升级-图片1" }
}
```

### 停止演示

输入：

```text
停止演示
```

成功时暂不回显（stdout 静默，不向界面返回“演示已停止”提示）；失败时照常返回失败 JSON。

动作：

- 写入 `stop` 命令。
- 等待后台脚本优雅退出；如果短时间内仍未退出，入口脚本会根据 `runtime/demo_state.json` 中记录的 PID 主动关闭后台进程。
- 调用内容展示器 `POST /api/stop`，停止当前显示并回到未加载/待机状态。
- 清理 `runtime/demo_command.json`、`runtime/demo_pause.flag`、`runtime/demo.pid`，保留 `runtime/demo_state.json` 记录最终停止状态。

## A01 提取数据块

输入可以是完整 JSON：

```json
{
  "chapters": [
    {
      "chapter_id": 1,
      "segments": [
        {
          "segment_id": 1,
          "text": "尊敬的华为各位领导、专家，大家好！我是公司产品的AI接待助理。",
          "duration": 6,
          "push_interval": 10,
          "audio": "audio/audio_001_01.mp3",
          "performance_code": "bow",
          "performance_duration": 4,
          "performance_desc": "动作-鞠躬"
        }
      ]
    }
  ]
}
```

也可以是 JSON 片段：

```json
"chapters": [
  {
    "chapter_id": 1,
    "segments": [
      {
        "segment_id": 1,
        "text": "尊敬的华为各位领导、专家，大家好！我是公司产品的AI接待助理。",
        "duration": 6,
        "push_interval": 10,
        "audio": "audio/audio_001_01.mp3",
        "performance_code": "bow",
        "performance_duration": 4,
        "performance_desc": "动作-鞠躬"
      }
    ]
  }
]
```

脚本会执行两类动作。

数字人消息 body：

```json
{
  "messagetype": "bot",
  "data": {
    "messageId": "section-1-1",
    "text": "[action:bow]尊敬的华为各位领导、专家，大家好！我是公司产品的AI接待助理。",
    "duration": 6,
    "audioUrl": "http://192.168.1.254:8888/PresetMeetingData/audio/audio_001_01.mp3"
  }
}
```

内容展示器 HTTP 请求：

```http
POST http://172.16.1.138:8088/api/show
```

请求体：

```json
{ "chapter_index": 0, "segment_index": 0, "show_subtitle": true }
```

数字人消息从第一个 `segment` 抽取并转换：

- `messageId`：`section-章节ID-段落ID`
- `text`：`[action:表演动作指令]` + 完整段落文本；若 `performance_code` 为空，则不添加 action 前缀
- `duration`：段落播报时长，只用于发给数字人的消息
- `push_interval`：推送间隔，后台脚本按这个值等待后再推送下一段
- `audioUrl`：音频完整路径，默认前缀为 `http://192.168.1.254:8888/PresetMeetingData/`

内容展示器消息中，`chapter_index` 由 `chapter_id - 1` 得到，`segment_index` 由 `segment_id - 1` 得到。

## 自然语言章节跳转

当演示正在运行，用户表达“跳转/切换/播放/看看某个章节”时，入口脚本会写入 jump 命令，后台脚本定位目标章节的第一个 `segment`，发送数字人消息并调用内容展示器 `/api/show`。

示例输入：

```text
跳转到第2章
```

数字人消息 body：

```json
{
  "messagetype": "bot",
  "data": {
    "messageId": "section-2-1",
    "text": "[action:serious]我们在数字孪生领域深耕近二十年，积累了上千个落地项目经验，也早已深度融入华为的生态体系。",
    "duration": 10,
    "audioUrl": "http://192.168.1.254:8888/PresetMeetingData/audio/audio_002_01.mp3"
  }
}
```

内容展示器 HTTP 请求：

```http
POST http://172.16.1.138:8088/api/show
```

请求体：

```json
{ "chapter_index": 1, "segment_index": 0, "show_subtitle": true }
```

也支持用章节标题关键词匹配，例如：

```text
切换到华为战略升级
```

## XMPP /send 请求格式

数字人模拟消息会调用：

```text
http://127.0.0.1:18900/send
```

请求体：

```json
{ "jid": "niujunke@im.tuguan.net", "body": "<JSON消息>", "from": "a01@im.tuguan.net" }
```

## 内容展示器 HTTP 对接

脚本会调用内容展示器：

```text
http://172.16.1.138:8088
```

开始演示时先加载 playlist，`playlist_id` 来自当前会议的 `booking_id`：

```http
POST /api/playlist/load
```

请求体：

```json
{ "playlist_id": "<booking_id>" }
```

每段显示时调用：

```http
POST /api/show
```

请求体：

```json
{ "chapter_index": 0, "segment_index": 0, "show_subtitle": true }
```

默认配置：

| 配置          | 值                            |
| ------------- | ----------------------------- |
| API           | `http://127.0.0.1:18900/send` |
| 接收方 `jid`  | `niujunke@im.tuguan.net`      |
| 发送方 `from` | `a01@im.tuguan.net`           |

环境变量覆盖：

| 环境变量                       | 默认值                                                            |
| ------------------------------ | ----------------------------------------------------------------- |
| `XMPP_SEND_API_URL`            | `http://127.0.0.1:18900/send`                                     |
| `P02_JID`                      | `niujunke@im.tuguan.net`                                          |
| `XMPP_FROM_ACCOUNT`            | `a01@im.tuguan.net`                                               |
| `XMPP_SEND_API_TOKEN`          | 空                                                                |
| `CONTENT_DISPLAY_BASE_URL`     | `http://172.16.1.138:8088`                                        |
| `PRESET_MEETING_DATA_DIR`      | `/home/clawd/.openclaw/workspace/SimulatedData/PresetMeetingData` |
| `MEETING_INDEX_PATH`           | `<PRESET_MEETING_DATA_DIR>/meeting_index.json`                    |
| `MEETING_ROOM_NAME`            | `大会议室`                                                        |
| `SIM_CURRENT_TIME`             | 空；非空时用于本地测试当前时间，格式 `YYYY-MM-DD HH:MM`           |
| `DIGITAL_HUMAN_AUDIO_BASE_URL` | `http://192.168.1.254:8888/PresetMeetingData/`                    |
| `DEMO_ACK_DELAY_SECONDS`       | `2.0`                                                             |

## 错误处理

| 错误场景                        | 输出 JSON                                                |
| ------------------------------- | -------------------------------------------------------- |
| 输入为空                        | `{"status":"failed","message":"无效的指令内容"}`         |
| JSON 结构无法识别               | `{"status":"failed","message":"无法识别 JSON 指令结构"}` |
| 自然语言无法识别                | `{"status":"failed","message":"无法识别控制意图"}`       |
| XMPP 或内容展示器 HTTP 发送失败 | `{"status":"failed","message":"消息发送失败"}`           |

## 测试方法

本地 dry-run 测试不会真实发送到 P02，也不会真实调用内容展示器。JSON 输入建议通过 stdin 传给脚本，避免 PowerShell 命令行参数吞掉 JSON 双引号：

```bash
python .openclaw/workspace/skills/ruisi-explanation-service/scripts/send_message.py --dry-run --payload "我想看看下一章"
```
