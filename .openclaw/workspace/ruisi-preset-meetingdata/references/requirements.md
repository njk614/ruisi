# 预置会议数据生成 Skill 结构化需求摘要

## 触发意图

- 我要预置会议数据
- 生成客户画像和讲解脚本
- 准备会议资料
- 预置数据生成
- 为某场会议生成客户资料、讲解内容、演示脚本

## 固定运行路径

```text
/home/clawd/.openclaw/workspace/SimulatedData
```

关键文件与目录：

- `meetings.json`：会议预定信息
- `KnowledgeBase/`：本地知识库
- `DisplayResourceLibrary/resource_catalog.json`：展示资源库
- `PresetMeetingData/`：预置会议数据输出目录

## 单场会议输出结构

```text
PresetMeetingData/
└── 当前会议ID/
    ├── customer_profile/
    │   └── CustomerProfile.md
    ├── audio/
    │   ├── audio_001_01.mp3
    │   └── ...
    ├── PresentationDocument.md
    ├── PresentationScript.md
    └── PresentationScript.json
```

## 目录已存在策略

- 目录不存在：直接创建并继续。
- 目录存在但没有核心文件：继续使用该目录。
- 目录存在且已有核心文件：提示用户选择“继续补齐缺失文件 / 覆盖重新生成 / 取消操作”。
- 核心文件包括 `customer_profile/CustomerProfile.md`、`PresentationDocument.md`、`PresentationScript.md`、`PresentationScript.json`。

## 生成流程

1. 读取 `meetings.json`，分页展示会议，每页默认 15 条。
2. 用户输入序号选择会议，回复 `0` 查看下一页。
3. 根据当前页码和用户选择序号，从 `meetings.json` 反查该会议的 `booking_id`。
4. 使用 `booking_id` 初始化会议目录，严禁使用会议主题名称作为目录名。
5. 用户选择会议后，分 5 步交互式收集客户公司、团队兴趣点、来访人员详细信息、历史合作、额外资料需求。
6. 检索 `KnowledgeBase/` 和公开网络资料，生成 `customer_profile/CustomerProfile.md`。
7. 检索知识库与 `resource_catalog.json`，生成不少于 1500 字的 `PresentationDocument.md`。
8. 基于演示文稿生成 `PresentationScript.md`。
9. 展示摘要，等待用户确认。
10. 用户确认后调用 TTS 流程生成音频，当前 TTS 为接口占位。
11. 获取音频时长并回填 `PresentationScript.md` 和 `PresentationScript.json`。
12. 将 `PresentationScript.md` 转换为 `PresentationScript.json`。
13. 预置完成后，将当前会议信息写入 `PresetMeetingData/meeting_index.json`。

## 用户可见输出要求

- 触发 Skill 后，第一条回复只能是会议列表和选择提示。
- 不输出寒暄、过程说明、脚本命令、内部 JSON 或检索日志。
- 每一步只输出当前必要内容：会议列表、信息收集、覆盖确认、生成摘要、确认提示或异常提示。
- 脚本输出属于内部结果，必须转换为简洁中文业务结果后再展示。
- 目录不存在或目录无核心文件时，不需要向用户解释目录状态，直接进入基础信息收集。
- 目录已有核心文件时，只列出已有关键文件，并让用户选择“继续补齐缺失文件 / 覆盖重新生成 / 取消操作”。
- 用户选择会议后，内部必须用 `booking_id` 创建和检查目录，不得使用会议主题名称。

## 5 步基础信息收集

用户选择会议后，基础信息必须拆成 5 步交互式引导，不能一次性输出完整大表单。

1. 询问客户公司完整名称。
2. 询问团队整体主要兴趣点，包括此次来访目的及基本诉求、感兴趣的行业领域、关注的产品及产品的行业应用等。
3. 询问来访人员详细信息，包括姓名、职务、亲切称呼、个人关注点、会议角色；如果会议预定信息中已有来访人员名单，应逐条列出姓名让用户补充。
4. 询问历史合作；如果没有请用户回复“初次合作”；如果有，请用户补充具体项目名称，涉密信息可以写成某某项目，并补充客户来访次数。
5. 询问是否需要补充额外资料，例如指定产品的详细介绍、具体的行业案例介绍、具体的方案介绍等。

5 步全部完成后，必须先整理当前信息给用户确认，内容包括当前会议、客户公司、团队兴趣点、来访人员详细信息、历史合作、额外资料需求。

用户可选择：

- `确认，开始生成数据`：进入客户画像、演示文稿、讲解脚本生成流程。
- `继续补充`：允许用户继续补充或修改信息，然后再次整理摘要并确认。

在用户明确选择 `确认，开始生成数据` 前，不得开始生成客户画像、演示文稿或讲解脚本。

## 讲解主体身份规则

- 讲解主体固定为“数字冰雹AI助理”或“数字冰雹AI接待助理”。
- 口播中的第一人称“我”只代表 AI 助理，不代表任何人类员工。
- `booker_name` 和 `internal_attendees` 只能作为会议预约人、我方参会人员、陪同人员或后续答疑支持人员使用，严禁作为第一人称讲解人、汇报人或联合汇报人。
- 不得出现“我是来自数字冰雹的某某”“我是数字冰雹的某某”“接下来由我和我的同事某某为大家汇报”“由某某和某某为大家汇报”等把我方参会人员写成讲解主体的表达。
- 推荐开场口径：`尊敬的各位领导、专家，大家好！我是数字冰雹AI助理，接下来由我为大家介绍数字冰雹在数字孪生领域的技术积累与产品体系。`

## 讲解脚本规则

- 每个独立展示资源实例对应一个章节。
- PPT 每页是一个章节。
- 视频每个时间片段是一个章节。
- 图片、网页各自为独立章节。
- 每个段落文本不超过 60 字。
- 初始生成时 `时长(s)` 不再留空，必须根据段落文本长度自动生成模拟时长。
- 模拟时长范围为 8 到 25 秒。
- 推荐估算规则：去除空白后的文本长度除以 4 后向上取整，再加 2 秒，最终限制在 8 到 25 秒之间。
- 音频路径格式为 `audio/audio_章节ID三位_段落ID两位.mp3`。
- 同一章节第一段填写完整资源字段，后续段落资源字段填 `-`。
- 讲解脚本中使用到的展示资源 URL 必须原样使用 `resource_catalog.json` 中对应资源的 `file_path` 字段。
- 如果 `file_path` 是完整网络地址，必须完整写入演示文稿、`PresentationScript.md` 和 `PresentationScript.json`，不得改写为相对路径或本地路径。

## 当前统一口径

- 会议文件名为 `meetings.json`。
- 产品名称统一为“孪易”。
- 客户画像路径为 `当前会议ID/customer_profile/CustomerProfile.md`。
- JSON 模板使用 `脚本json模板.json`。
- 脚本段落长度不超过 60 字。

## meeting_index.json 写入要求

预置会议数据完成后，必须更新：

```text
/home/clawd/.openclaw/workspace/SimulatedData/PresetMeetingData/meeting_index.json
```

索引文件结构：

```json
{
  "version": "1.0",
  "description": "已预置会议数据的索引文件，用于快速定位指定会议的客户画像与演示脚本",
  "meetings": [
    {
      "booking_id": "M20260604_001",
      "meeting_topic": "华为2026年园区基线解决方案亮点讨论会",
      "time_range": "2026-06-04 08:00~12:00",
      "meeting_region": "大会议室",
      "customer_profile_path": "./M20260604_001/customer_profile/CustomerProfile.md",
      "presentation_script_path": "./M20260604_001/PresentationScript.json"
    }
  ]
}
```

写入规则：

- 使用 `booking_id` 作为唯一主键。
- 如果已存在相同 `booking_id`，更新旧记录，不重复追加。
- `meeting_topic`、`time_range`、`meeting_region` 来自用户选择的会议对象。
- `customer_profile_path` 固定为 `./<booking_id>/customer_profile/CustomerProfile.md`。
- `presentation_script_path` 固定为 `./<booking_id>/PresentationScript.json`。
