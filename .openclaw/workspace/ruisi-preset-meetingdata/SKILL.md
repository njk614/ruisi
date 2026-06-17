---
name: ruisi-preset-meetingdata
description: 为 OpenClaw 中指定会议生成预置会议数据，包括客户画像、演示文稿、讲解脚本、脚本 JSON 以及音频资源规划。当用户提出“预置会议数据”“准备会议资料”“生成客户画像和讲解脚本”“生成演示脚本”等请求，或需要基于 SimulatedData 中的会议预定信息、KnowledgeBase 本地知识库和 DisplayResourceLibrary 展示资源库生成会议接待与讲解资料时使用。
---

# 预置会议数据生成

使用本 Skill 为 OpenClaw 中的指定会议准备客户画像、演示文稿、讲解脚本、脚本 JSON 和音频资源规划。

## 数据路径

默认数据根目录：

```text
/home/clawd/.openclaw/workspace/SimulatedData
```

数据根目录下的关键路径：

- `meetings.json`：会议预定信息。
- `KnowledgeBase/`：本地知识库文件。
- `DisplayResourceLibrary/resource_catalog.json`：展示资源库，包含 `templates` 标准模板和 `resources` 基础展示资源。
- `PresetMeetingData/`：生成后的会议预置数据目录。

如果在本地镜像环境中调试，调用脚本时传入 `--data-root <SimulatedData路径>`。

## 参考资料

按需读取以下参考文件：

- `references/requirements.md`：结构化流程和业务规则。
- `references/customer-profile-template.md`：客户画像 Markdown 结构。
- `references/presentation-template.md`：演示文稿结构。
- `references/presentation-script-template.md`：讲解脚本表格规则。
- `references/presentation-script-json-template.json`：目标 JSON 结构。

## 用户可见输出规范

本 Skill 的用户可见回复必须简洁、直接、只包含当前流程需要的信息。

强制规则：

- 触发 Skill 后，第一条用户可见回复只能展示会议列表和选择提示，不要输出“好的”“我来处理”“正在查询”等寒暄或过程说明。
- 不要向用户展示脚本命令、内部 JSON、检索日志、推理过程或无关说明，除非用户明确要求。
- 每一步只输出一个明确目标：列表、选择提示、信息收集表单、覆盖确认、生成摘要、确认提示或异常提示。
- 已通过脚本得到的内部结果，应转换为自然、简洁的中文业务输出后再展示给用户。
- 需要用户输入时，问题必须具体、可直接填写；不要附加无意义解释。
- 生成文件期间，如必须告知等待，只使用需求中指定的固定回复。

### 触发后的首条回复格式

当用户表达“预置会议数据”等触发意图后，直接展示：

```text
共检索到 N 个会议：
1. 会议主题 | 会议时间范围
2. 会议主题 | 会议时间范围
...
请回复序号选择需要预置数据的会议，继续查看下一页数据请回复 ‘0’
```

首条回复不得包含其他内容。

### 后续流程输出格式

目录已有核心文件时，只输出：

```text
该会议已存在预置数据：
- 相对路径1
- 相对路径2

请选择：继续补齐缺失文件 / 覆盖重新生成 / 取消操作
```

基础信息收集必须拆成 5 步交互式引导，每次只问当前一步。不要一次性输出完整大表单。

第 1 步只输出：

```text
请补充客户公司完整名称：
```

第 2 步只输出：

```text
请补充团队整体主要兴趣点（此次来访目的及基本诉求、感兴趣的行业领域、关注的产品及产品的行业应用等）：
```

第 3 步只输出：

```text
请补充来访人员详细信息（姓名、职务、亲切称呼、个人关注点、会议角色）：
```

第 4 步只输出：

```text
请补充历史合作（如果没有请回复“初次合作”，如果有，请补充具体的项目名称，涉密信息可以写成某某项目，并补充客户来访次数）：
```

第 5 步只输出：

```text
是否需要补充额外资料（指定产品的详细介绍、具体的行业案例介绍、具体的方案介绍等）：
```

5 步信息全部收集完成后，不要立即生成数据，必须先整理当前信息给用户确认：

```text
请确认以下信息：
- 当前会议：会议主题 | 会议时间范围
- 客户公司：客户公司完整名称
- 团队整体主要兴趣点：此次来访目的及基本诉求、感兴趣的行业领域、关注的产品及产品的行业应用等
- 来访人员详细信息：姓名、职务、亲切称呼、个人关注点、会议角色
- 历史合作：初次合作 / 项目信息及客户来访次数
- 额外资料需求：指定产品的详细介绍、具体的行业案例介绍、具体的方案介绍等

请选择：确认，开始生成数据 / 继续补充
```

用户确认输入信息后，先输出：

```text
好的，正在生成客户画像、演示文档和讲解脚本，请稍等，任务完成后我会第一时间通知您。
```

此阶段只生成 `CustomerProfile.md`、`PresentationDocument.md`、`PresentationScript.md` 和 `PresentationScript.json`，不得生成音频、回填音频时长、发布 Presenter 共享目录或更新完成状态。

第一阶段生成完成后，只输出：

```text
客户画像、演示文档和讲解脚本已生成：
- 客户画像：简要摘要
- 演示文稿：章节数/重点内容
- 讲解脚本：章节数/段落数
- 会议目录：完整路径
- 客户画像路径：完整路径
- 演示文稿路径：完整路径
- 讲解脚本路径：完整路径
- 讲解脚本JSON路径：完整路径

请先审核讲解脚本文档。如果文档已审核通过，需要继续预生成音频文件，请回复“确认”。
```

## 工作流程

### 1. 展示会议列表

运行：

```bash
python scripts/list_meetings.py --data-root <SimulatedData> --page 1 --page-size 15
```

将返回的会议列表作为首条用户可见回复直接展示给用户。不得在会议列表前后增加寒暄、过程说明或脚本输出。

用户选择会议序号后，必须先运行解析脚本：

```bash
python scripts/resolve_meeting_selection.py <用户回复的序号> --data-root <SimulatedData> --page <当前页码> --page-size 15
```

使用解析结果中的 `booking_id` 作为当前会议 ID。后续所有目录检查、目录创建、文件生成、索引更新都必须使用该 `booking_id`。

严禁使用 `meeting_topic`、会议主题名称、会议室名称或用户可见列表文本作为会议目录名。

解析脚本返回的完整会议对象作为后续生成内容的会议上下文，但不要把内部 JSON 直接展示给用户。

### 2. 检查并初始化会议目录

运行：

```bash
python scripts/inspect_meeting_workspace.py <meeting_id> --data-root <SimulatedData>
```

这里的 `<meeting_id>` 必须是上一步解析出的 `booking_id`。

按返回结果处理：

- `missing_directory`：创建目录并继续。
- `directory_without_core_files`：继续使用该目录。
- `directory_with_core_files`：告知用户已有文件，并询问选择 `继续补齐缺失文件`、`覆盖重新生成` 或 `取消操作`。

如果目录不存在或目录存在但没有核心文件，不需要单独告诉用户目录状态，直接进入基础信息收集。

生成文件前运行初始化：

```bash
python scripts/init_meeting_workspace.py <meeting_id> --data-root <SimulatedData>
```

这里的 `<meeting_id>` 也必须是解析出的 `booking_id`。

### 3. 分 5 步收集用户基础信息

用户选择会议且完成目录检查后，进入 5 步交互式信息收集。每次只向用户询问一个步骤，不要一次性展示所有问题。

5 个步骤为：

1. 客户公司完整名称。
2. 团队整体主要兴趣点：此次来访目的及基本诉求、感兴趣的行业领域、关注的产品及产品的行业应用等。
3. 来访人员详细信息：姓名、职务、亲切称呼、个人关注点、会议角色。
4. 历史合作：如果没有请回复“初次合作”；如果有，请补充具体项目名称，涉密信息可以写成某某项目，并补充客户来访次数。
5. 是否需要补充额外资料：指定产品的详细介绍、具体的行业案例介绍、具体的方案介绍等。

如果 `meetings.json` 中已有 `customer_attendees`，第 3 步必须优先按名单逐条列出人员姓名，引导用户逐人补充。例如：

```text
请补充来访人员详细信息（姓名、职务、亲切称呼、个人关注点、会议角色）：
- 何霁：
- 李明：
```

第 5 步完成后，先整理已收集信息并让用户确认。用户可选择：

- `确认，开始生成数据`：进入后续检索和文档生成流程。
- `继续补充`：允许用户补充或修改上述任一信息，然后重新整理摘要并再次确认。

在用户明确选择 `确认，开始生成数据` 前，不得开始生成客户画像、演示文稿或讲解脚本。

用户确认开始生成数据后，必须先回复：

```text
好的，正在生成客户画像、演示文档和讲解脚本，请稍等，任务完成后我会第一时间通知您。
```

该确认只允许进入文档和脚本生成阶段，不得直接生成音频。

### 4. 检索本地知识库和公开网络

使用可能相关的关键词检索本地知识库：

```bash
python scripts/search_local_knowledge.py --data-root <SimulatedData> --query "<company>" --query "<meeting_topic>" --query "<interest>"
```

将检索片段作为公司、产品和方案内容的生成依据。

网络可用时，检索客户公司的公开背景、行业领域、主营业务，以及与会议主题相关的公开信息。生成内容时区分公开客户信息和内部知识库信息，不编造无依据事实。

### 5. 生成 CustomerProfile.md

读取 `references/customer-profile-template.md`。

生成：

```text
PresetMeetingData/<meeting_id>/customer_profile/CustomerProfile.md
```

保持模板结构。讲解脚本关联路径填写为：

```text
../PresentationScript.json
```

### 6. 推荐标准模板与展示资源

运行：

```bash
python scripts/rank_display_resources.py --data-root <SimulatedData> --query "<meeting_topic>" --query "<company>" --query "<interest>" --limit 12
```

该脚本会读取 `resource_catalog.json` 中的 `templates` 和 `resources`：

- 先根据客户画像、会议主题、公司名称、团队兴趣点、额外资料需求等上下文，匹配 `templates` 中的 `description` 和 `triggers`。
- 如果匹配到模板，必须优先使用模板，按模板 `file_path` 读取 Markdown 内容。
- 模板 `file_path` 使用相对路径时，按 `resource_catalog.json` 所在目录解析；模板文件不存在时不得声称已使用该模板。
- 模板的 `position` 表示模板整体在演示流程中的位置：`opening` 放在开头，`closing` 放在结尾，`middle` 可放在中间合适位置。
- `position` 只约束模板整体位置；模板内所有章节顺序、展示资源和讲解内容不得调整。
- 当模板标记 `immutable: true` 时，模板内容必须原样并入 `PresentationDocument.md`，不得改写、摘要化、增删章节或替换资源路径。
- `total_chapters` 用于校验模板包含的章节数量；并入时应保持完整章节。
- 模板处理完成后，再使用 `resources` 中真实存在的基础展示资源，补充生成客户定制、产品、方案、案例等动态章节。

只使用 `resource_catalog.json` 中真实存在的模板和资源。基础展示资源优先选择分数更高且描述与章节内容匹配的资源。

资源路径强制规则：

- 演示文稿、讲解脚本 Markdown、讲解脚本 JSON 中使用到的每个展示资源，`资源URL` / `resource.url` 必须原样使用 `resource_catalog.json` 中对应资源的 `file_path` 字段。
- 标准模板中已经写好的展示资源路径也必须原样保留，不得用 `resources` 中的其他资源替换。
- 如果 `file_path` 是完整网络地址，例如 `http://172.16.1.138:8089/DisplayResourceLibrary/images/xxx.png`，必须完整写入，不得改写为 `/images/xxx.png`、相对路径或本地路径。
- 不得编造资源路径，也不得根据文件名自行拼接路径。

### 7. 讲解主体身份强制规则

生成 `PresentationDocument.md`、`PresentationScript.md` 和 `PresentationScript.json` 时，必须遵守以下讲解主体规则：

- 讲解主体固定为“数字冰雹AI助理”或“数字冰雹AI接待助理”。
- 口播中的第一人称“我”只代表 AI 助理，不代表任何人类员工。
- `booker_name` 和 `internal_attendees` 只能作为会议预约人、我方参会人员、陪同人员或后续答疑支持人员使用，严禁作为第一人称讲解人、汇报人或联合汇报人。
- 不得出现“我是来自数字冰雹的某某”“我是数字冰雹的某某”“接下来由我和我的同事某某为大家汇报”“由某某和某某为大家汇报”等把我方参会人员写成讲解主体的表达。
- 推荐开场口径：`尊敬的各位领导、专家，大家好！我是数字冰雹AI助理，接下来由我为大家介绍数字冰雹在数字孪生领域的技术积累与产品体系。`

### 8. 生成 PresentationDocument.md

读取 `references/presentation-template.md`。

生成：

```text
PresetMeetingData/<meeting_id>/PresentationDocument.md
```

要求：

- 按中文业务需求不少于 1500 字。
- 结合当前会议主题和已生成的客户画像。
- 产品和方案描述应基于本地知识库。
- 生成演示文稿前必须先处理 `resource_catalog.json.templates`，命中标准模板时优先将模板整体原样并入，再结合 `resource_catalog.json.resources` 生成其余动态章节。
- 使用 `resource_catalog.json` 中的展示资源，并原样保留每个资源的 `file_path` 完整地址。
- 已并入的标准模板章节不得被模型重写、压缩、换序或拆散；动态章节不得重复生成模板已经覆盖的公司介绍内容。
- 章节结构应便于后续转换成讲解脚本。
- 必须遵守“讲解主体身份强制规则”，不得把我方参会人员写成口播讲解人。

### 9. 生成 PresentationScript.md

读取 `references/presentation-script-template.md`。

生成：

```text
PresetMeetingData/<meeting_id>/PresentationScript.md
```

规则：

- 使用规定的 Markdown 表格列。
- 一个独立展示资源实例对应一个章节。
- 每个段落文本不少于 30 字，且不超过 90 字。
- 初次生成时 `时长(s)` 必须填 `-`，不得填写模拟时长。
- 每个章节第一行必须填写资源类型、URL、参数和描述。
- 同一章节后续行的资源字段填 `-`。
- 资源 URL 必须原样来自 `resource_catalog.json.file_path`，完整网络地址不能截短。
- 音频文件必须填写完整 HTTP 地址，格式为 `http://172.16.1.138:8089/PresetMeetingData/<meeting_id>/audio/audio_001_01.mp3`。
- `<meeting_id>` 必须使用当前会议真实 `booking_id`，不得使用会议主题、会议室名称或其他文本。
- 音频字段中的完整 HTTP 地址仅用于数字人、内容展示器等外部设备访问音频；TTS 生成和音频时长回填必须只取其中的文件名，并映射到本地 `<meeting_dir>/audio/<音频文件名>` 读写。
- 表演素材码只能使用模板中的合法值；不需要表演时填 `-`。
- `表演素材码` 后必须填写 `素材时长(s)` 字段；使用表演素材时填写对应素材秒数，不使用表演素材时填 `-`。
- 当前仅启用动作素材 `wave`、`point`、`nod`、`shake_head`，素材时长均为 4 秒。
- 当前仅启用表情素材 `smile` 5 秒、`laugh` 3 秒、`cover_mouth_laugh` 4 秒。
- 暂未启用的其他动作或表情素材不得生成到讲解脚本中。
- 初次生成时 `推送间隔(s)` 必须填 `-`。
- 真实音频生成后，读取音频文件实际时长并向上取整回填 `时长(s)`；例如 1.1 秒、1.9 秒都回填为 2 秒。
- 回填后，`推送间隔(s)` 必须等于 `时长(s)` 加 `素材时长(s)`；不使用表演素材时，`素材时长(s)` 按 0 计算，即 `推送间隔(s)` 等于 `时长(s)`。
- 必须遵守“讲解主体身份强制规则”，开场和后续第一人称均代表数字冰雹AI助理。

校验：

```bash
python scripts/validate_presentation_script_md.py <PresentationScript.md> --meeting-id <meeting_id>
```

继续前必须修复除真实音频时长外的全部校验问题。音频生成并回填后，还必须运行强校验：

```bash
python scripts/validate_presentation_script_md.py <PresentationScript.md> --meeting-id <meeting_id> --require-durations
```

### 10. 将脚本 Markdown 转换为 JSON

运行：

```bash
python scripts/script_md_to_json.py <PresentationScript.md> --output <PresentationScript.json> --title "<meeting_topic>"
```

JSON 必须与 Markdown 脚本内容保持一致。初始 JSON 中 `duration` 和 `push_interval` 可以保持为 `null`，等待音频生成后回填。

### 11. 汇总脚本并等待用户审核确认

运行：

```bash
python scripts/summarize_outputs.py <meeting_id> --data-root <SimulatedData>
```

向用户展示：

- 客户画像摘要。
- 讲解脚本摘要。
- 会议数据目录。
- `CustomerProfile.md`、`PresentationDocument.md`、`PresentationScript.md`、`PresentationScript.json` 的完整路径。

必须明确提示用户先审核 `PresentationScript.md`，审核通过后再回复确认继续生成音频。若用户提出修改意见，更新相关文档，重新校验，并重新生成 `PresentationScript.json`。

对用户输出必须包含 `PresentationScript.md` 的完整路径，并使用类似话术：

```text
请先审核讲解脚本文档。如果文档已审核通过，需要继续预生成音频文件，请回复“确认”。
```

### 12. 生成音频

用户确认脚本文档审核通过后，先回复：

```text
好的，正在生成音频文件，请稍等，任务完成后我会第一时间通知您。
```

然后运行 TTS 生成脚本：

```bash
python scripts/tts_generate_audio.py <PresentationScript.json> --meeting-dir <PresetMeetingData/meeting_id> --request
```

脚本默认使用 OpenAI-compatible TTS endpoint `https://api-tts.tuguan.net/v1/audio/speech` 和内置 token；音色固定为 `Timbre1`。脚本也支持页面代理 `/api/tts` 模式：

```bash
python scripts/tts_generate_audio.py <PresentationScript.json> --meeting-dir <PresetMeetingData/meeting_id> --mode proxy --endpoint http://127.0.0.1:5174/api/tts --request
```

默认不加 `--request` 时只做 dry-run 并输出待生成音频清单，不会请求 TTS 服务。即使 `PresentationScript.json` 中的 `audio` 是完整 HTTP 地址，脚本也必须只取音频文件名，并写入本地 `<meeting_dir>/audio/` 目录。只有脚本返回 `status: generated` 且音频文件已写入本地 `<meeting_dir>/audio/` 目录后，才能声称真实音频已生成。

### 13. 回填音频时长

真实 MP3 文件生成后，必须回填音频时长：

```bash
python scripts/fill_audio_durations.py <PresentationScript.json> --meeting-dir <PresetMeetingData/meeting_id> --script-md <PresentationScript.md>
```

该脚本会逐个读取音频文件实际时长，向上取整后回写 `PresentationScript.md` 的 `时长(s)` 和 `推送间隔(s)`，并同步更新 `PresentationScript.json` 的 `duration` 和 `push_interval`。即使脚本中的 `audio` 是完整 HTTP 地址，也必须只取音频文件名，并从本地 `<meeting_dir>/audio/` 目录读取 MP3，不得通过 HTTP 地址读取时长。

回填后运行：

```bash
python scripts/validate_presentation_script_md.py <PresentationScript.md> --meeting-id <meeting_id> --require-durations
```

### 14. 发布讲解脚本 JSON 到 Presenter 共享目录

音频时长回填并通过强校验后，必须将 `PresentationScript.json` 发布到 Windows 共享目录：

```text
\\172.16.1.138\SharedResources\PresetMeetingData
```

运行：

```bash
python scripts/publish_presenter_data.py <meeting_id> --data-root <SimulatedData>
```

发布结果必须为共享目录下的同名会议文件夹，且该文件夹中只包含 `PresentationScript.json`。例如：

```text
\\172.16.1.138\SharedResources\PresetMeetingData\M20260611_001\PresentationScript.json
```

脚本默认使用账号 `digihail`、密码 `frontfree` 访问共享目录。如需测试路径但不执行拷贝，可加 `--dry-run`。

### 15. 更新会议索引

预置会议数据生成完成后，必须更新：

```text
PresetMeetingData/meeting_index.json
```

该文件用于快速定位指定会议的客户画像与演示脚本 JSON。最终产物就绪后运行：

```bash
python scripts/update_meeting_index.py <booking_id> --data-root <SimulatedData> --meeting-topic "<meeting_topic>" --time-range "<time_range>" --meeting-region "<room_name>"
```

这里的 `<booking_id>` 必须继续使用同一个会议 `booking_id`。如果索引中已经存在相同 `booking_id`，应更新旧记录，不重复追加。

写入结构必须与 `meeting_index.json` 模板保持一致：

```json
{
  "booking_id": "M20260604_001",
  "meeting_topic": "会议主题",
  "time_range": "会议时间范围",
  "meeting_region": "会议区域",
  "customer_profile_path": "./M20260604_001/customer_profile/CustomerProfile.md",
  "presentation_script_path": "./M20260604_001/PresentationScript.json"
}
```

更新索引完成后，必须向用户输出最终完成消息，包含当前会议数据目录完整路径，并明确说明 `<meeting_topic>` 会议预置数据已经生成完毕。例如：

```text
音频文件已生成，脚本时长已回填，Presenter 数据已发布。

当前会议数据完整路径：<PresetMeetingData/meeting_id>
<meeting_topic> 会议预置数据已经生成完毕。
```

## 核心输出文件

```text
PresetMeetingData/<meeting_id>/customer_profile/CustomerProfile.md
PresetMeetingData/<meeting_id>/PresentationDocument.md
PresetMeetingData/<meeting_id>/PresentationScript.md
PresetMeetingData/<meeting_id>/PresentationScript.json
PresetMeetingData/<meeting_id>/audio/
```

## 异常处理

- 如果 `meetings.json` 缺失，只输出：`会议预定文件不存在：<期望路径>`。
- 如果没有会议数据，只输出：`当前没有可预置数据的会议。`
- 如果用户输入序号无效，只输出：`序号无效，请重新输入会议序号，或回复 ‘0’ 查看下一页。`
- 如果本地知识库没有命中，继续基于用户输入和公开网络信息生成，不需要单独告知用户。
- 如果展示资源缺失或无匹配资源，不要编造资源路径；最终摘要中可简要提示：`展示资源不足，已使用文本脚本占位。`
- 如果 TTS 不可用，保留音频路径规划并让时长保持为空，不要声称已生成真实音频。
