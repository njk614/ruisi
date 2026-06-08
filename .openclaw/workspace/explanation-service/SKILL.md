---
name: explanation-service
description: 讲解控制 Skill。接收客户端控制消息（语义文本为主），按内容分流为开始讲解、暂停讲解、继续讲解三类，并调用对应 Python 接口。free-qa 在问答前通过 pause_explanation.py 调用本 Skill 触发暂停。兼容历史 free-qa 固定结构控制消息。Use when the explanation agent needs to react to start/pause/resume control intents from client messages.
allowed-tools:
  - bash
  - read_file
  - write_file
metadata:
  openclaw:
    version: '1.0.0'
    author: 'your_name'
    level: 'L1'
    emoji: '🎛️'
    requires:
      bins:
        - python3
---

# 讲解控制服务

## 触发条件

- 处理来自客户端的讲解控制消息。
- 当消息语义命中开始讲解、暂停讲解、继续讲解时，进入本 Skill。
- 当收到 free-qa 通过 `pause_explanation.py` 转发的暂停消息（默认“暂停讲解”）时，进入本 Skill。
- 兼容历史 free-qa 固定结构控制消息（暂停/恢复结构体）。
- 不依赖发送方账号做拦截，按消息内容识别并触发。

## 消息分类

### 继续讲解

出现以下任意词语或短句即判定为继续讲解：

- 继续演示
- 继续讲解
- 继续播放
- 继续推送
- 恢复演示
- 恢复讲解
- 恢复播放
- 接着演示
- 接着讲解
- 可以继续
- 继续吧
- 继续
- 接着
- 恢复
- 继续一下
- 继续说
- 接着说
- 恢复一下

### 暂停讲解

出现以下任意词语或短句即判定为暂停讲解：

- 暂停
- 暂停讲解
- 暂停演示
- 先暂停
- 停一下
- 稍等
- 等一下
- 不要讲了
- 先别讲
- 停止讲解
- 暂停播放

free-qa 默认会发送以下语义暂停消息：

- 暂停讲解

兼容历史 free-qa 固定结构暂停消息：

- 【说明：当前消息最终发送给“讲解程序”，用于暂停当前讲解及讲解内容的推送】
- {"status":"pause"}

### 开始讲解

出现以下任意词语或短句即判定为开始讲解：

- 开始讲解
- 开始演示
- 开始播放
- 开始推送
- 开讲
- 开始吧
- 现在开始
- 讲解开始

## 固定结构消息识别（历史兼容）

- 若消息包含 free-qa 的讲解程序说明文本，并且状态体是 {"status":"pause"}，按暂停讲解处理。
- 若消息包含 free-qa 的讲解程序说明文本，并且状态体是 {"status":"resume"}，按继续讲解处理。

## 编排步骤

1. 接收输入参数：sender_jid、message、message_id(建议必传)、session_id(可选)。
2. 根据消息内容分类：start/pause/resume。
3. 调用对应 Python 接口：

- start -> 调用开始讲解接口
- pause -> 调用暂停讲解接口
- resume -> 调用继续讲解接口

4. 输出标准 JSON：status、action、message、session_id。

## 状态与定时发送机制

- 本 Skill 采用"控制命令 + 常驻发送进程"架构。
- `start`：加载本地数据文件，设置 mode=running，启动定时发送守护进程；守护进程拿到讲解内容后立即发送第一页，不额外等待。
- `pause`：将 mode 设为 paused，守护进程停止推进发送游标。
- `resume`：将 mode 恢复为 running，守护进程按保存的 index 立即继续发送，不等待上一段时长倒计时补完。
- 发送进度 index、当前模式 mode、数据文件路径和发送间隔会写入本地状态文件：`runtime/explanation_state.json`。
- 因为状态是落盘的，不依赖一次 Skill 触发内存，所以可以跨多次触发保持状态。
- 每页时长计时从该页内容发出后才开始，仅在未被 pause/resume 等控制指令打断时按时长自然推进。
- 全部页码发送完成后仅切换为 paused，不追加任何结束致谢文案。

## 数据文件

- 默认讲解数据文件优先：`~/.openclaw/workspace/SimulatedData/PresentationScript.md`
- 若默认优先路径不存在，自动回退到：`data/PresentationScript.md`
- 可通过 `EXPLAIN_DATA_FILE` 显式覆盖路径。

## 运行脚本

- 控制器：`scripts/explain_controller.py`
- 守护进程：`scripts/explanation_dispatch_daemon.py`
- 消息路由入口：`scripts/explanation_message_service.py`

## 环境变量

- `EXPLAIN_DATA_FILE`：讲解数据文件路径。
- `EXPLAIN_INTERVAL_SECONDS`：默认发送间隔秒数。
- `EXPLAIN_TARGET_JID`：目标 Agent JID。
- `EXPLAIN_FROM_ACCOUNT`：发送方账号。
- `EXPLAIN_SEND_API_URL`：消息发送接口 URL；未配置时走本地 mock 发送（仅日志）。
- `EXPLAIN_SEND_API_TOKEN`：发送接口鉴权 Token（可选）。

## 输入参数

| 参数名     | 类型   | 必填 | 说明                               |
| ---------- | ------ | ---- | ---------------------------------- |
| sender_jid | string | 否   | 发送方账号（可选，仅用于留痕透传） |
| message    | string | 是   | 接收到的文本消息                   |
| message_id | string | 否   | 上游消息唯一标识；传入后可启用去重 |
| session_id | string | 否   | 会话唯一标识，用于追踪             |

## 输出参数

| 参数名     | 类型   | 说明                              |
| ---------- | ------ | --------------------------------- |
| status     | string | success 或 ignored 或 failed      |
| action     | string | start 或 pause 或 resume 或 none  |
| message    | string | 执行结果描述                      |
| message_id | string | 回传上游消息 ID（仅在传入时返回） |
| sender_jid | string | 回传发送方账号（仅在传入时返回）  |
| session_id | string | 会话标识                          |

## Python 服务入口

```bash
python scripts/explanation_message_service.py --sender-jid "a01@im.tuguan.net" --message "继续讲解"
```

## 处理约束

- 最终输出必须是纯 JSON，不要输出额外文本。
- 若消息未匹配三类意图，返回 ignored，不做任何接口调用。
- 若接口调用失败，返回 failed 并包含错误信息。
- 支持 dry-run 模式用于联调验证，不触发真实接口。
- 若 message_id 重复，返回 ignored 并跳过接口调用，防止同一上游消息重复触发。

## 错误处理

| 场景           | 处理 | 返回                                                              |
| -------------- | ---- | ----------------------------------------------------------------- |
| message 为空   | 失败 | {"status":"failed","action":"none","message":"消息为空"}          |
| 未匹配任何意图 | 忽略 | {"status":"ignored","action":"none","message":"未匹配到控制意图"} |
| 接口调用异常   | 失败 | {"status":"failed","action":"<action>","message":"调用失败：..."} |

## 建议接入方式

- 将本 Skill 部署到 explanation-service。
- free-qa 提问场景在生成答案前，调用 `python scripts/pause_explanation.py` 触发本 Skill 执行暂停。
- 让消息事件回调在收到文本后调用上述 Python 入口。
- 用环境变量配置实际接口命令，避免硬编码。
