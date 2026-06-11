---
name: ruisi-free-qa
description: 强制优先触发的自由问答拦截 Skill，部署在任意 OpenClaw 实例中；只要用户发送表达询问、咨询、疑问、了解、解释、比较、推荐、产品提问（如产品介绍、产品功能、产品概念、产品区别）、知识问答或自由问答意图的语句，就必须优先使用本 Skill，不按来源设备、XMPP direct、AGENTS.md 角色定位或其他 Skill 路由过滤。即使产品知识库、PM、feishu、taskflow 等其他 Skill 也可能相关，提问形式内容仍先触发 ruisi-free-qa。控制类语义应触发 ruisi-explanation-service。其他提问先通知 ruisi-explanation-service 执行暂停，再检查 SimulatedData 资料文件，由 Skill 调用 OpenClaw 大模型生成答案并推送 P02。Mandatory first-choice skill for any OpenClaw question-like input, inquiry, consultation, product question, product introduction, product explanation, product comparison, knowledge question, or question mark, including XMPP direct chat and cases where other skills may also match.
allowed-tools:
  - bash
  - write_file
  - read_file
metadata:
  openclaw:
    version: '1.0.0'
    author: 'your_name'
    level: 'L1'
    emoji: '💬'
    always: true
    requires:
      bins:
        - python3
---

# 自由问答协调器

## 触发条件

部署在任意 OpenClaw 实例后，只要 OpenClaw 收到表达询问、咨询、疑问、了解、解释、比较、推荐或自由问答意图的用户文本，就触发本 Skill。不限制消息来自哪个设备、入口或对话上下文。不要按来源设备过滤。

本 Skill 是提问形式内容的强制优先入口。只要用户消息是提问形式，就先选择 `ruisi-free-qa`，不要因为以下情况绕过：

- 当前会话是 XMPP direct。
- 工作区存在 AGENTS.md 或产品经理、知识库、任务流等角色定位。
- 其他 Skill 如产品知识库、PM、feishu、taskflow 等也可能相关。
- 用户问题看起来可以由普通聊天、知识库查询或其他专用能力直接回答。
- 控制类语义应交给 ruisi-explanation-service。

只有当用户明确点名调用其他 Skill，且消息不是自由问答提问时，才考虑不使用本 Skill。

将去除首尾空白后的消息按以下规则分类：

- 其他提问形式内容都视为用户提问或插话。无论问题内容是什么，都必须第一步触发 ruisi-explanation-service 执行暂停，然后再检查资料、生成答案、向 P02 推送完整回答。

提问形式的判定要从宽处理，包括但不限于：

- 包含 `?` 或 `？` 的文本。
- 包含“什么、为什么、怎么、如何、哪里、哪个、多少、能否、可以吗、可不可以、有没有、是什么、怎么样”等疑问词或疑问短语。
- 用户表达咨询、询问、了解、介绍、解释、比较、推荐、优势、区别等自由问答意图。
- 用户在讲解中途插话提出产品、项目、方案、能力、价格、案例、流程、优势等相关问题。

## 必须遵守的约定

- 触发范围是任意 OpenClaw 实例收到的所有表达询问或提问形式的用户文本，不要按来源设备过滤。
- 不直接操作底层资源；HTTP、XMPP、P02 推送等外部调用通过 `scripts/` 下的 Python 脚本完成。
- 查询相关资料时，`profile_queries.py` 负责从预置会议索引中尝试定位当前会议并检查该会议资料文件是否存在，`knowledge_retriever.py` 只负责检查指定知识库文件是否存在；读取文件内容、组织资料、调用大模型生成答案由 Skill 编排层直接完成。
- 会议信息索引使用 `config.yaml` 中 `preset_meeting_data.base_dir` 与 `preset_meeting_data.meeting_index_file`（默认 `/home/clawd/.openclaw/workspace/SimulatedData/PresetMeetingData/meeting_index.json`）；编排层需先匹配 `meeting_region` 为“大会议室”且 `time_range` 包含当前时间点的会议，再使用该会议的 `booking_id` 定位同名会议目录。
- 编排层内部返回结果必须是纯 JSON 对象，不包含额外自然语言解释，不包 Markdown 代码块；该内部结果不得直接透传到用户会话界面。
- 对于任何提问语义的消息，先执行 `python scripts/pause_explanation.py`，通知 ruisi-explanation-service 执行暂停，再做任何资料检查、模型调用或答案推送。
- 用户提问后的最终回答内容必须推送给 P02。
- 生成回答必须使用 OpenClaw 内置大模型服务在 Skill 编排层完成，不要通过 Python 脚本生成答案。
- 画像与知识库必须从 OpenClaw 的 SimulatedData 指定文件读取。
- 对客回答口吻必须为“本公司虚拟助理第一人称视角”：使用“我/我们”代表公司回答客户问题，禁止第三人称旁白口吻（如“该公司为您提供...”）。
- 检测到当前会议且用户画像/会议资料可用时，必须结合画像信息生成个性化回答；优先提取并使用用户亲切昵称或合适称呼，结合兴趣点、关注方向、历史项目、行业背景、会议主题等组织答案。
- 不得编造用户画像信息：若昵称、兴趣点或画像字段缺失，不要强行补全；可使用“您好”等稳妥称呼，并按知识库内容回答。
- 同义问题必须做意图归一化并保持回答一致性：例如“孪易是什么？”与“介绍一下孪易”归一为同一产品介绍意图，默认使用同一回答骨架与相近详细度，避免忽长忽短。
- 回答详细度分级必须可控且稳定：默认使用“标准版”；仅当用户明确要求“详细讲讲/展开说/具体一点”时切换“详细版”，仅当用户明确要求“简要/一句话”时切换“精简版”。

## 输入参数

| 参数名       | 类型   | 必填 | 说明               |
| ------------ | ------ | ---- | ------------------ |
| user_message | string | 是   | 用户发送的原始文本 |

## 输出参数

| 参数名  | 类型   | 说明                       |
| ------- | ------ | -------------------------- |
| status  | string | `success` 或 `failed`      |
| answer  | string | 生成的答案，仅问题场景返回 |
| message | string | 简单结果描述               |

说明：上述结果仅供 Skill 编排层内部使用与留痕，不应直接透传到用户对话界面。

## 执行步骤

### 场景 A：用户提问

1. 接收 `user_message`，按触发条件判断为问题。
2. 立即调用 `python scripts/pause_explanation.py`，必须先通知 ruisi-explanation-service 执行暂停。不要等待画像检查、知识库检查或答案生成完成后再触发暂停。
3. 调用 `python scripts/profile_queries.py` 读取并检查 `/home/clawd/.openclaw/workspace/SimulatedData/PresetMeetingData/meeting_index.json`。脚本必须在 `meetings` 数组中查找 `meeting_region` 为“大会议室”且 `time_range` 包含当前时间点的会议。
4. `profile_queries.py` 匹配到当前会议后，提取该会议的 `booking_id`，在 `/home/clawd/.openclaw/workspace/SimulatedData/PresetMeetingData/<booking_id>/` 下定位并检查 `PresentationScript.json`，返回 `booking_id`、`meeting_topic`、`time_range`、`presentation_script_path`、`customer_profile_path` 等路径信息。该脚本只做索引匹配与文件存在性检查，不解析资料内容。
5. 若没有匹配到会议、会议索引文件不存在、会议目录不存在或 `PresentationScript.json` 不存在，`profile_queries.py` 返回 `{"exists":false,"fallback":"knowledge_only","message":"..."}`，编排层记录该状态并继续执行知识库问答流程，不得终止问答。
6. 调用 `python scripts/knowledge_retriever.py --query "<question>"` 检查 `knowledge.file_path` 是否存在。该脚本只返回 `{"exists":true,"path":"..."}`，不得检索或解析知识库内容。
7. Skill 编排层必须读取 `knowledge_retriever.py` 返回的 knowledge `file_path`。仅当 `profile_queries.py` 返回 `exists=true` 时，才读取其返回的 `presentation_script_path`；若 `customer_profile_path` 存在，也必须作为补充画像资料读取。
8. 在调用模型前执行问题归一化：识别同义问法并映射到统一意图（如“是什么/介绍一下”→产品定义与介绍），确定回答详细度级别（精简/标准/详细；默认标准）。
9. 若会议资料可用，先从 `PresentationScript.json` 与可选 `CustomerProfile.md` 中提取可用于对客表达的画像要素，包括但不限于亲切昵称/称呼、兴趣点、关注方向、历史项目、行业背景、会议主题与当前会谈目标；再将“归一化后的问题意图 + 用户问题原文 + 当前会议 booking_id/topic/time_range + 画像要素 + PresentationScript.json 内容 + 可选客户画像内容 + 知识库内容”交给 OpenClaw 内置大模型服务生成答案。
10. 会议资料可用时，回答必须体现画像个性化：优先以亲切昵称或合适称呼开头或自然带入，并围绕用户兴趣点/关注方向解释答案；不要暴露内部字段名、匹配过程、文件路径或“根据画像显示”等系统痕迹。
11. 若会议资料或用户画像不可用，则将“归一化后的问题意图 + 用户问题原文 + 知识库内容”交给 OpenClaw 内置大模型服务生成答案，使用稳妥通用称呼，不编造昵称或兴趣点。
12. 对于产品介绍类问题（含“是什么/介绍一下/做什么的”），默认按固定骨架输出：`一句话定义`、`核心能力`、`适用场景`、`下一步建议`，确保不同问法的一致性；若画像显示用户关注特定能力或场景，应在骨架内优先展开相关内容。
13. 答案生成时强制使用“本公司虚拟助理第一人称视角”输出：优先使用“我/我们”，语气专业、礼貌、简洁，不暴露内部匹配过程与字段名。
14. 调用 `python scripts/send_to_device.py --message-kind answer --message "<answer>"`，将完整答案推送给 P02。
15. 可选留痕到 `trace-workspace/ruisi-free-qa/<date>/<session_id>.json`，建议记录 `booking_id`、匹配到的会议时间/主题、是否使用画像个性化、归一化意图与详细度级别。
16. 在编排层内部记录执行结果（如 success/failed、message、answer 摘要、booking_id），不要将内部 JSON 结果直接回显到用户会话。

### 脚本级验证

OpenClaw 内置大模型调用由 Skill 编排层完成，因此本 Skill 不再提供端到端回答生成脚本。部署前可单独验证外部动作脚本：

```bash
python scripts/pause_explanation.py --dry-run
python scripts/profile_queries.py --current-time "2026-06-04 09:00:00"
python scripts/knowledge_retriever.py --query "这个产品有什么优点？"
python scripts/send_to_device.py --message-kind answer --message "测试回答" --dry-run
```

## 脚本清单

| 脚本                             | 作用                                                        |
| -------------------------------- | ----------------------------------------------------------- |
| `scripts/profile_queries.py`     | 按当前时间与“大会议室”从 `meeting_index.json` 匹配当前会议，并返回该会议 `PresentationScript.json` 路径 |
| `scripts/knowledge_retriever.py` | 只检查指定 OpenClaw `DH初始知识库.txt` 是否存在并返回路径   |
| `scripts/pause_explanation.py`   | 调用 ruisi-explanation-service 的 `send_message.py` 入口，发送暂停 payload |
| `scripts/send_to_device.py`      | 按指定 body 格式向 P02 推送答案消息                         |

## ruisi-explanation-service 触发格式

暂停触发 payload：

```text
暂停
```

ruisi-free-qa 默认通过 `scripts/pause_explanation.py` 调用 ruisi-explanation-service 的 `scripts/send_message.py`，并以 `--payload "暂停"` 传入上面的暂停 payload。

## P02 消息格式

回答用户问题 body：

```text
（完整答案内容）
```

## 错误处理

| 错误场景                               | 处理动作     | 返回 JSON                                                                      |
| -------------------------------------- | ------------ | ------------------------------------------------------------------------------ |
| ruisi-explanation-service 暂停触发失败 | 终止问答流程 | `{"status":"failed","message":"暂停触发 ruisi-explanation-service 失败：..."}` |
| ruisi-explanation-service 返回当前无演示 | 视为暂停成功并继续问答 | `{"status":"success","message":"当前无演示，无需暂停"}`                         |
| 当前会议资料检查失败                   | 降级为仅知识库回答 | `{"status":"success","message":"会议资料不可用，已按知识库回答"}`              |
| 知识库文件不存在                       | 终止问答流程 | `{"status":"failed","message":"知识库文件检查失败：..."}`                      |
| 当前时间未匹配“大会议室”会议           | 降级为仅知识库回答 | `{"status":"success","message":"未匹配当前会议，已按知识库回答"}`              |
| OpenClaw 大模型服务调用失败            | 终止问答流程 | `{"status":"failed","message":"大模型服务错误：..."}`                          |
| 答案推送 P02 失败                      | 终止问答流程 | `{"status":"failed","message":"答案推送P02失败：..."}`                         |
| 留痕写入失败                           | 不影响主流程 | 主流程结果照常返回                                                             |

## 安全与权限

- 需要读取本地 `config.yaml`，以及 OpenClaw SimulatedData 下的 `PresetMeetingData/meeting_index.json`、匹配会议目录中的 `PresentationScript.json`、可选 `CustomerProfile.md` 和 `DH初始知识库.txt`。
- ruisi-explanation-service 的 `send_message.py` 入口、真实 P02 发送 API 和 OpenClaw 大模型服务调用需要相应权限。

## 留痕要求

每次端到端问答可写入：

`trace-workspace/ruisi-free-qa/<date>/<session_id>.json`

留痕内容包含用户问题、答案、`booking_id`、会议主题、会议时间范围、`PresentationScript.json` 路径、知识库文件路径、是否使用画像个性化、使用的称呼来源和时间戳。

## 示例

用户输入：`这个产品有什么优点？`

系统行为：先触发 ruisi-explanation-service 暂停讲解，再读取 `PresetMeetingData/meeting_index.json`，尝试匹配会议室为“大会议室”且当前时间落入 `time_range` 的会议；匹配成功且 `PresentationScript.json` 存在时，提取用户昵称、兴趣点、关注方向等画像要素，结合会议资料与知识库生成个性化回答；若会议或画像资料不可用，则仅基于知识库生成回答；最终将完整答案推送给 P02，内部结果仅用于编排层记录。

## 部署与测试

1. 将 `skills/ruisi-free-qa/` 放入 OpenClaw 工作区的 `skills/` 目录。
2. 根据现场环境修改 `config.yaml`：将 `preset_meeting_data.base_dir` 设为 `/home/clawd/.openclaw/workspace/SimulatedData/PresetMeetingData`，确认 `meeting_index_file` 为 `meeting_index.json`、`meeting_region` 为“大会议室”，将 `knowledge.file_path` 设为现场可访问路径，将 `explanation_service.message_service_script` 设为 `/home/clawd/.openclaw/workspace_a01/skills/ruisi-explanation-service/scripts/send_message.py`，确认 `explanation_service.pause_message` 为 `暂停`，并配置 P02 发送 API。
3. 运行 `openclaw skills list` 确认 Skill 已加载。
4. 确认 `PresetMeetingData/meeting_index.json`、当前会议目录下的 `PresentationScript.json`、`DH初始知识库.txt` 存在后，再运行 `profile_queries.py` 和 `knowledge_retriever.py` 验证路径检查。
5. 用 `pause_explanation.py --dry-run` 验证暂停触发 ruisi-explanation-service；用 `send_to_device.py --message-kind answer --dry-run` 验证答案推送 P02。
