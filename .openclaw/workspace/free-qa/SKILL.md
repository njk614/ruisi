---
name: free-qa
description: 强制优先触发的自由问答拦截 Skill，部署在任意 OpenClaw 实例中；只要用户发送表达询问、咨询、疑问、了解、解释、比较、推荐、产品提问（如产品介绍、产品功能、产品概念、产品区别）、知识问答或自由问答意图的语句，就必须优先使用本 Skill，不按来源设备、XMPP direct、AGENTS.md 角色定位或其他 Skill 路由过滤。即使产品知识库、PM、feishu、taskflow 等其他 Skill 也可能相关，提问形式内容仍先触发 free-qa。控制类语义应触发 explanation-service。其他提问先通知 explanation-service 执行暂停，再检查 SimulatedData 资料文件，由 Skill 调用 OpenClaw 大模型生成答案并推送 P02。Mandatory first-choice skill for any OpenClaw question-like input, inquiry, consultation, product question, product introduction, product explanation, product comparison, knowledge question, or question mark, including XMPP direct chat and cases where other skills may also match.
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

本 Skill 是提问形式内容的强制优先入口。只要用户消息是提问形式，就先选择 `free-qa`，不要因为以下情况绕过：

- 当前会话是 XMPP direct。
- 工作区存在 AGENTS.md 或产品经理、知识库、任务流等角色定位。
- 其他 Skill 如产品知识库、PM、feishu、taskflow 等也可能相关。
- 用户问题看起来可以由普通聊天、知识库查询或其他专用能力直接回答。
- 控制类语义应交给 explanation-service。

只有当用户明确点名调用其他 Skill，且消息不是自由问答提问时，才考虑不使用本 Skill。

将去除首尾空白后的消息按以下规则分类：

- 其他提问形式内容都视为用户提问或插话。无论问题内容是什么，都必须第一步触发 explanation-service 执行暂停，然后再检查资料、生成答案、向 P02 推送完整回答。

提问形式的判定要从宽处理，包括但不限于：

- 包含 `?` 或 `？` 的文本。
- 包含“什么、为什么、怎么、如何、哪里、哪个、多少、能否、可以吗、可不可以、有没有、是什么、怎么样”等疑问词或疑问短语。
- 用户表达咨询、询问、了解、介绍、解释、比较、推荐、优势、区别等自由问答意图。
- 用户在讲解中途插话提出产品、项目、方案、能力、价格、案例、流程、优势等相关问题。

## 必须遵守的约定

- 触发范围是任意 OpenClaw 实例收到的所有表达询问或提问形式的用户文本，不要按来源设备过滤。
- 不直接操作底层资源；HTTP、XMPP、P02 推送等外部调用通过 `scripts/` 下的 Python 脚本完成。
- 查询相关资料时，`profile_queries.py` 和 `knowledge_retriever.py` 只负责检查指定文件是否存在；读取文件内容、组织资料、调用大模型生成答案由 Skill 编排层直接完成。
- 会议信息文件路径使用 `config.yaml` 中 `meetings.file_path`（默认 `/home/clawd/.openclaw/workspace/SimulatedData/meetings.json`）；编排层需读取其中 `time_range` 与 `meeting_topic` 字段参与匹配。
- 编排层内部返回结果必须是纯 JSON 对象，不包含额外自然语言解释，不包 Markdown 代码块；该内部结果不得直接透传到用户会话界面。
- 对于任何提问语义的消息，先执行 `python scripts/pause_explanation.py`，通知 explanation-service 执行暂停，再做任何资料检查、模型调用或答案推送。
- 用户提问后的最终回答内容必须推送给 P02。
- 生成回答必须使用 OpenClaw 内置大模型服务在 Skill 编排层完成，不要通过 Python 脚本生成答案。
- 画像与知识库必须从 OpenClaw 的 SimulatedData 指定文件读取。
- 对客回答口吻必须为“本公司虚拟助理第一人称视角”：使用“我/我们”代表公司回答客户问题，禁止第三人称旁白口吻（如“该公司为您提供...”）。
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
2. 立即调用 `python scripts/pause_explanation.py`，必须先通知 explanation-service 执行暂停。不要等待画像检查、知识库检查或答案生成完成后再触发暂停。
3. 读取客户名：优先使用 OpenClaw 会话上下文传入的客户名；若没有，则使用 `config.yaml` 的 `customer.default_name`。
4. 调用 `python scripts/profile_queries.py --customer-name "<name>"` 检查 `customer.profile_file` 是否存在。该脚本只返回 `{"exists":true,"path":"..."}`，不得解析画像内容。
5. 检查 `meetings.file_path` 是否已配置，并校验该文件是否存在；不存在则返回 failed（`会议信息文件检查失败`）。
6. 调用 `python scripts/knowledge_retriever.py --query "<question>"` 检查 `knowledge.file_path` 是否存在。该脚本只返回 `{"exists":true,"path":"..."}`，不得检索或解析知识库内容。
7. Skill 编排层读取三个文件内容：`profile_queries.py` 返回的 profile_file、`meetings.file_path` 指向的 meetings.json、`knowledge_retriever.py` 返回的 knowledge file_path。
8. 从 meetings.json 提取当前问题对应会议的 `time_range` 和 `meeting_topic`，并与用户画像中的“会议时间”“会议主题”进行匹配，得到 `meeting_match=true/false`。
9. 在调用模型前执行问题归一化：识别同义问法并映射到统一意图（如“是什么/介绍一下”→产品定义与介绍），确定回答详细度级别（精简/标准/详细；默认标准）。
10. 若 `meeting_match=true`：将“归一化后的问题意图 + 用户问题原文 + 匹配到的画像相关信息 + 知识库内容”交给 OpenClaw 内置大模型服务生成答案。
11. 若 `meeting_match=false`：将“归一化后的问题意图 + 用户问题原文 + 知识库内容”交给 OpenClaw 内置大模型服务生成答案。
12. 对于产品介绍类问题（含“是什么/介绍一下/做什么的”），默认按固定骨架输出：`一句话定义`、`核心能力`、`适用场景`、`下一步建议`，确保不同问法的一致性。
13. 答案生成时强制使用“本公司虚拟助理第一人称视角”输出：优先使用“我/我们”，语气专业、礼貌、简洁，不暴露内部匹配过程与字段名。
14. 调用 `python scripts/send_to_device.py --message-kind answer --message "<answer>"`，将完整答案推送给 P02。
15. 可选留痕到 `trace-workspace/free-qa/<date>/<session_id>.json`，建议记录 `meeting_match`、匹配到的时间/主题（若有）、归一化意图与详细度级别。
16. 在编排层内部记录执行结果（如 success/failed、message、answer 摘要、meeting_match），不要将内部 JSON 结果直接回显到用户会话。

### 脚本级验证

OpenClaw 内置大模型调用由 Skill 编排层完成，因此本 Skill 不再提供端到端回答生成脚本。部署前可单独验证外部动作脚本：

```bash
python scripts/pause_explanation.py --dry-run
python scripts/profile_queries.py --customer-name "张三"
python scripts/knowledge_retriever.py --query "这个产品有什么优点？"
python scripts/send_to_device.py --message-kind answer --message "测试回答" --dry-run
```

## 脚本清单

| 脚本                             | 作用                                                        |
| -------------------------------- | ----------------------------------------------------------- |
| `scripts/profile_queries.py`     | 只检查指定 OpenClaw `CustomerProfile.md` 是否存在并返回路径 |
| `scripts/knowledge_retriever.py` | 只检查指定 OpenClaw `DH初始知识库.txt` 是否存在并返回路径   |
| `scripts/pause_explanation.py`   | 调用 explanation-service 的消息入口，触发暂停讲解           |
| `scripts/send_to_device.py`      | 按指定 body 格式向 P02 推送答案消息                         |

## explanation-service 触发格式

暂停触发消息：

```text
暂停讲解
```

free-qa 默认通过 `scripts/pause_explanation.py` 调用 explanation-service 的消息入口脚本，并传入上面的暂停消息。

## P02 消息格式

回答用户问题 body：

```text
（完整答案内容）
```

## 错误处理

| 错误场景                         | 处理动作     | 返回 JSON                                                                |
| -------------------------------- | ------------ | ------------------------------------------------------------------------ |
| explanation-service 暂停触发失败 | 终止问答流程 | `{"status":"failed","message":"暂停触发 explanation-service 失败：..."}` |
| 客户画像文件不存在               | 终止问答流程 | `{"status":"failed","message":"用户画像文件检查失败：..."}`              |
| 会议信息文件不存在               | 终止问答流程 | `{"status":"failed","message":"会议信息文件检查失败：..."}`              |
| 知识库文件不存在                 | 终止问答流程 | `{"status":"failed","message":"知识库文件检查失败：..."}`                |
| 会议字段未匹配（time/topic）     | 回退检索流程 | `{"status":"success","message":"会议未匹配，已按通用知识库回答"}`        |
| OpenClaw 大模型服务调用失败      | 终止问答流程 | `{"status":"failed","message":"大模型服务错误：..."}`                    |
| 答案推送 P02 失败                | 终止问答流程 | `{"status":"failed","message":"答案推送P02失败：..."}`                   |
| 留痕写入失败                     | 不影响主流程 | 主流程结果照常返回                                                       |

## 安全与权限

- 需要读取本地 `config.yaml`，以及 OpenClaw SimulatedData 下的 `CustomerProfile.md`、`DH初始知识库.txt` 和 `meetings.json`。
- explanation-service 消息入口、真实 P02 发送 API 和 OpenClaw 大模型服务调用需要相应权限。

## 留痕要求

每次端到端问答可写入：

`trace-workspace/free-qa/<date>/<session_id>.json`

留痕内容包含用户问题、答案、画像文件路径、会议信息文件路径、知识库文件路径、`meeting_match` 标记和时间戳。

## 示例

用户输入：`这个产品有什么优点？`

系统行为：先触发 explanation-service 暂停讲解，再读取会议信息并尝试与画像中的会议时间/主题匹配；匹配成功则结合匹配画像信息与知识库回答，未匹配则直接基于知识库回答；最终将完整答案推送给 P02，内部结果仅用于编排层记录。

## 部署与测试

1. 将 `skills/free-qa/` 放入 OpenClaw 工作区的 `skills/` 目录。
2. 根据现场环境修改 `config.yaml`：将 `customer.profile_file`、`knowledge.file_path`、`meetings.file_path` 设为现场可访问路径（例如 `/home/clawd/.openclaw/workspace/SimulatedData/meetings.json`），将 `explanation_service.message_service_script` 设为 `/home/clawd/.openclaw/workspace_a01/skills/explanation-service/scripts/explanation_message_service.py`，并配置 P02 发送 API。
3. 运行 `openclaw skills list` 确认 Skill 已加载。
4. 确认 `CustomerProfile.md`、`DH初始知识库.txt`、`meetings.json` 三个 SimulatedData 文件均存在后，再运行 `profile_queries.py` 和 `knowledge_retriever.py` 验证路径检查。
5. 用 `pause_explanation.py --dry-run` 验证暂停触发 explanation-service；用 `send_to_device.py --message-kind answer --dry-run` 验证答案推送 P02。
