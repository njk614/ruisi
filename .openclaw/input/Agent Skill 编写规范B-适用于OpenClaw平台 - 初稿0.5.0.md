# Agent Skill 编写规范（适用于 OpenClaw 平台）

**版本**：0.5.0  
**发布日期**：2026年5月29日  
**适用平台**：OpenClaw  
**制定依据**：《AI Agent 系统设计模式调研报告：Skill-SubAgent 三层架构》（2026年5月）、OpenClaw 官方开发文档及社区最佳实践（2026年5月）

---

## 目录

1. [范围与术语](#1-范围与术语)
2. [工程目录](#2-工程目录)
3. [Skill 与 SubAgent 文件规范](#3-skill-与-subagent-文件规范)
4. [三层架构中 Skill、SubAgent 的职责](#4-三层架构中-skillsubagent-的职责)
5. [留痕规范（产物与过程记录）](#5-留痕规范产物与过程记录)
6. [通用原则](#6-通用原则)
7. [交互模式要求（缰绳编程）](#7-交互模式要求缰绳编程)
8. [部署验证与故障排查](#8-部署验证与故障排查)
9. [规范遵守检查清单](#9-规范遵守检查清单)
10. [附录](#10-附录)

---

## 1. 范围与术语

### 1.1 适用范围

本规范适用于所有基于 **OpenClaw** 框架开发的智能体技能（Skill）与智能体（Agent）。团队内所有成员在编写面向 OpenClaw 的组件时必须遵循本规范，以确保组件的可读性、可维护性、可审计性和跨项目兼容性。

### 1.2 术语定义

#### 基础概念

| 术语 | 定义 |
|------|------|
| **Skill** | 一个标准化的知识/流程文档（`SKILL.md` 文件），描述 Agent 如何完成特定任务。Skill 不独立运行，由主 Agent 阅读并遵循。每个 Skill 是一个包含 `SKILL.md` 的目录。 |
| **SubAgent** | 一个拥有独立工作区、记忆和会话的 AI 实例，通过 `openclaw agents add` 命令创建，用于执行子任务。SubAgent 可并行、可持久化，执行结果返回给主 Agent。 |

#### 三层架构中的角色分类

| 角色 | 载体 | 说明 |
|------|------|------|
| **L1 协调器** | Skill | 由**主 Agent** 读取的宏观 Skill，描述整体流程：分解任务、指定调用哪些 SubAgent、定义异常处理。L1 Skill 不直接操作底层资源，只负责编排。 |
| **L2 执行器** | SubAgent | 被主 Agent 调用的 **SubAgent 实例**，负责边界清晰的独立子任务，可调用 L3 Skill。L2 SubAgent 可被并行调用。 |
| **L3 原子操作** | Skill | 不可再分的最小操作单元 **Skill**，无副作用或严格幂等，可被主 Agent 或 SubAgent 直接调用。 |

#### 其他术语

| 术语 | 定义 |
|------|------|
| **留痕** | 执行 Skill 时保存过程产生的实质性产物（如文档、报表、转换后的数据等），以及关键过程的元数据（执行清单）和简易日志，用于审计和问题追溯。 |
| **缰绳编程** | 通过提供有限的、明确的选项（而非开放式问题）来约束 AI 自由度的交互设计模式。 |
| **业务任务** | 一个完整的业务场景，如“产品需求文档生成”、“收入确认自动化”，对应 `<workspace>/trace-workspace/` 下的一级目录。业务任务名 `business_task` 用于组织留痕目录。**推荐由顶层调用者（如主 Agent）根据用户意图生成语义化名称**；若调用者未提供，L1 Skill 必须自动生成一个默认值（格式 `auto_<uuid>`）。嵌套调用时，子 L1 必须继承父 L1 的 `business_task`，不得重新生成。 |

### 1.3 三层架构关系

```text
┌─────────────────────────────────────────────────────────────┐
│                      主 Agent（默认）                        │
│  ┌─────────────────────────────────────────────────────┐    │
│  │           L1 协调器 Skill（SKILL.md）                │    │
│  │  步骤1: 调用 SubAgent A 或 L3 Skill（适用条件下）     │    │
│  │  步骤2: 并行调用 SubAgent B 和 C                     │    │
│  │  步骤3: 汇总结果                                     │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              │ Routing bindings（消息路由）
                              ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ L2 SubAgent A   │ │ L2 SubAgent B   │ │ L2 SubAgent C   │
│ (独立工作区)     │ │ (独立工作区)     │ │ (独立工作区)     │
│ 可调用 L3 Skill │ │ 可调用 L3 Skill │ │ 可调用 L3 Skill │
└─────────────────┘ └─────────────────┘ └─────────────────┘
                              │
                              ▼
              ┌─────────────────────────────┐
              │     L3 原子 Skill 库         │
              │  (file-md5, convert-csv…)   │
              └─────────────────────────────┘
```

---

## 2. 工程目录

OpenClaw 平台的 Skill 和 SubAgent 工程分为**开发态**（项目级）和**部署态**（全局级），两者目录结构相同，但留痕目录位置不同。

OpenClaw 平台默认采用**工作区（Workspace）** 作为核心目录。本规范统一采用如下部署方案：

- **L1/L3 Skill** 统一存放在 **工作区 Skills 目录**（`<workspace>/skills/`），优先级最高，供当前工作区的主 Agent 和所有 SubAgent 共用。

- **L2 SubAgent** 统一存放在 **全局 Agents 目录**（`~/.openclaw/agents/`），每个 SubAgent 独立管理。

  > **附加说明**：OpenClaw 按以下顺序从高到低加载 Skills：

  |  优先级   | 来源               | 路径                         |
  | :-------: | ------------------ | ---------------------------- |
  | 1（最高） | 工作区 Skills      | `<workspace>/skills`         |
  |     2     | 项目智能体 Skills  | `<workspace>/.agents/skills` |
  |     3     | 个人智能体 Skills  | `~/.agents/skills`           |
  |     4     | 托管/本地 Skills   | `~/.openclaw/skills`         |
  |     5     | 内置 Skills        | 随安装包提供                 |
  |     6     | 额外 Skills 文件夹 | `skills.load.extraDirs` 配置 |

  > **说明**：本规范将 L1/L3 Skill 放在 `<workspace>/skills/` 下，正是利用了**最高优先级**，确保这些技能可以被当前工作区的主 Agent 和所有 SubAgent 优先使用。

### 2.1 开发态目录

开发态用于在项目仓库中编写、调试 Skill 和 SubAgent。除“留痕目录”外所有文件纳入 Git 版本管理。

#### 工作区根目录

- **说明**：OpenClaw 默认工作区，存放 Skills、留痕产物及运行时数据。
- **完整路径示例**：
  - Windows：`C:\my-project\.openclaw\workspace\`
  - Linux/macOS：`/home/username/my-project/.openclaw/workspace/`

#### SubAgent 存储目录

- **说明**：每个 SubAgent 有独立的子目录，包含专属的 `agent/AGENTS.md`、`MEMORY.md`、`sessions/` 等。
- **完整路径示例**：
  - Windows：`C:\my-project\.openclaw\agents\`
  - Linux/macOS：`/home/username/my-project/.openclaw/agents/`

#### 完整目录结构示例

```
your-project/                           # 项目根目录
└── .openclaw/                          # OpenClaw 配置根目录
    ├── config/                         # 全局配置
    │   └── openclaw.json               # 主配置文件（包含 bindings 路由配置）
    ├── workspace/                      # 主工作区（核心目录）
    │   ├── skills/                     # ⭐ L1 & L3 Skill 存放位置
    │   │   ├── prd-generator/          # L1 协调器 Skill
    │   │   │   ├── SKILL.md
    │   │   │   ├── references/
    │   │   │   │   └── prd_template.md
    │   │   │   └── tests/
    │   │   │       └── test_prd.md
    │   │   ├── web-fetcher/            # L3 原子 Skill
    │   │   │   ├── SKILL.md
    │   │   │   └── scripts/
    │   │   │       └── fetch.py
    │   │   ├── html-parser/            # L3 原子 Skill
    │   │   │   └── SKILL.md
    │   │   └── report-writer/          # L3 原子 Skill
    │   │       └── SKILL.md
    │   ├── trace-workspace/            # 留痕输出根目录（自动创建）
    │   │   └── <business_task>/        # 业务任务名
    │   │       └── YYYYMMDD_HHMMSS_<execution_id>/
    │   │           ├── manifest.json
    │   │           ├── execution.log
    │   │           ├── input/
    │   │           ├── artifacts/
    │   │           └── output/
    ├── agents/                         # ⭐ L2 SubAgent 存放位置
    │   ├── competitor-worker/          # 竞品调研 SubAgent
    │   │   ├── agent/
    │   │   │   ├── AGENTS.md           # 该 SubAgent 的行为定义
    │   │   │   ├── SOUL.md             # 人格定义（可选）
    │   │   │   └── MEMORY.md           # 专属记忆（可选）
    │   │   └── sessions/               # 会话历史
    │   ├── prd-writer/                 # PRD 撰写 SubAgent
    │   │   └── agent/
    │   │       └── AGENTS.md
    │   └── code-reviewer/              # 代码审查 SubAgent
    │       └── agent/
    │           └── AGENTS.md
```

### 2.2 部署态目录

部署态用于将 Skill 安装到openclaw全局环境，供所有项目使用。

#### 工作区根目录

- **说明**：全局部署的 Skill 存放根目录。
- **完整路径示例**：
  - Windows：`C:\Users\username\.openclaw\workspace\`
  - Linux/macOS：`/home/username/.openclaw/workspace/`

#### SubAgent 存储目录

- **说明**：全局部署的 SubAgent 存放根目录，包含专属的 `agent/AGENTS.md`、`MEMORY.md`、`sessions/` 等。
- **完整路径示例**：
  - Windows：`C:\Users\username\.openclaw\agents\`
  - Linux/macOS：`/home/username/.openclaw/agents/`

#### 完整目录结构示例

```
/home/username                          
└── .openclaw/                          # OpenClaw 配置根目录
    ├── config/                         # 全局配置
    │   └── openclaw.json               # 主配置文件（包含 bindings 路由配置）
    ├── workspace/                      # 主工作区（核心目录）
    │   ├── skills/                     # ⭐ L1 & L3 Skill 存放位置
    │   │   ├── prd-generator/          # L1 协调器 Skill
    │   │   │   ├── SKILL.md
    │   │   │   ├── references/
    │   │   │   │   └── prd_template.md
    │   │   │   └── tests/
    │   │   │       └── test_prd.md
    │   │   ├── web-fetcher/            # L3 原子 Skill
    │   │   │   ├── SKILL.md
    │   │   │   └── scripts/
    │   │   │       └── fetch.py
    │   │   ├── html-parser/            # L3 原子 Skill
    │   │   │   └── SKILL.md
    │   │   └── report-writer/          # L3 原子 Skill
    │   │       └── SKILL.md
    │   ├── trace-workspace/            # 留痕输出根目录（自动创建）
    │   │   └── <business_task>/        # 业务任务名
    │   │       └── YYYYMMDD_HHMMSS_<execution_id>/
    │   │           ├── manifest.json
    │   │           ├── execution.log
    │   │           ├── input/
    │   │           ├── artifacts/
    │   │           └── output/
    ├── agents/                         # ⭐ L2 SubAgent 存放位置
    │   ├── competitor-worker/          # 竞品调研 SubAgent
    │   │   ├── agent/
    │   │   │   ├── AGENTS.md           # 该 SubAgent 的行为定义
    │   │   │   ├── SOUL.md             # 人格定义（可选）
    │   │   │   └── MEMORY.md           # 专属记忆（可选）
    │   │   └── sessions/               # 会话历史
    │   ├── prd-writer/                 # PRD 撰写 SubAgent
    │   │   └── agent/
    │   │       └── AGENTS.md
    │   └── code-reviewer/              # 代码审查 SubAgent
    │       └── agent/
    │           └── AGENTS.md
```
### 2.3 运行时留痕目录

运行时留痕目录位于工作区的 `trace-workspace/` 下，内部结构保持一致。

| 环境 | 留痕根目录 | 完整路径示例（Linux） | 完整路径示例（Windows） |
|------|-----------|---------------------|---------------------|
| 开发态/部署态 | `<workspace>/trace-workspace/` | `/home/username/.openclaw/workspace/trace-workspace/` | `C:\Users\username\.openclaw\workspace\trace-workspace\` |

**单次执行目录示例**：

```
~/.openclaw/workspace/trace-workspace/prd/20260529_100000_abc12345/
├── manifest.json
├── execution.log
├── input/
├── artifacts/
└── output/
```

---

## 3. Skill 与 SubAgent 文件规范

### 3.1 Skill 文件规范（SKILL.md）

每个 Skill 的 `SKILL.md` 文件采用 **YAML Frontmatter + Markdown 正文章节** 的格式。

#### 3.1.1 Frontmatter 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | Skill 名称，与目录名一致，正则 `^[a-z0-9]+(-[a-z0-9]+)*$`，长度 1–64 |
| `description` | string | ✅ | 一句话描述功能和触发场景，不超过 200 字符。**重要**：OpenClaw 根据此字段判断是否调用该 Skill |
| `version` | string | 推荐 | 语义化版本，如 `1.0.0` |
| `author` | string | 推荐 | 负责人姓名或团队名称 |
| `level` | string | ✅ | 必须为 `L1` 或 `L3`，标识 Skill 类型 |
| `allowed-tools` | array | 推荐 | 本 Skill 会调用的工具列表，如 `["read_file", "write_file", "bash"]` |
| `dependencies` | array | 可选 | 依赖的外部命令或 Python 包（用于开发安装） |
| `metadata` | object | 推荐 | OpenClaw 扩展元数据，包含 `openclaw` 字段 |

**metadata.openclaw 字段说明**：

| 子字段 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `requires.bins` | array | 推荐 | 依赖的二进制可执行文件列表，如 `["curl", "ffmpeg"]`。若缺失，该 Skill 会被过滤，不会出现在 Agent 的系统提示词中 |
| `requires.config` | array | 可选 | 依赖的配置键列表 |
| `requires.env` | array | 可选 | 依赖的环境变量列表 |
| `os` | array | 可选 | 操作系统过滤器，如 `["darwin"]`、`["linux"]` |
| `emoji` | string | 可选 | 技能显示用的表情符号 |

**示例**：
```yaml
---
name: web-fetcher
description: 从指定 URL 获取网页内容并保存到文件
version: 1.0.0
author: 基础架构组
level: L3
allowed-tools:
  - http_request
  - write_file
metadata:
  openclaw:
    emoji: "🌐"
    requires:
      bins:
        - curl
        - wget
      env:
        - HTTP_PROXY
dependencies:
  - command: "curl"
    min_version: "7.68"
---
```

#### 3.1.2 正文章节要求

| 序号 | 章节名称 | L1 要求 | L3 要求 |
|------|----------|---------|---------|
| 1 | 触发条件 | ✅ 必填 | ✅ 必填（可一句话） |
| 2 | 必须遵守的约定 | ✅ 必填 | ⚠️ 可省略 |
| 3 | 输入参数 | ✅ 必填（见下方说明） | ✅ 必填（简洁表格） |
| 4 | 输出参数 | ✅ 必填 | ✅ 必填（至少 status, message） |
| 5 | 执行步骤 | ✅ 必填 | ✅ 必填（简洁列表） |
| 6 | 错误处理 | ✅ 必填 | ⚠️ 可简化 |
| 7 | 安全与权限 | ✅ 必填 | ⚠️ 可简化 |
| 8 | 留痕要求 | ✅ 必填 | ✅ 必填 |
| 9 | 交互模式 | ✅ 必填 | ⚠️ 可省略 |
| 10 | 示例 | ✅ 必填 | ✅ 必填（至少一个） |

**输入参数特别说明（L1 Skill）**：

- 输入参数中**应包含** `business_task`（string，推荐）。顶级调用者（如主 Agent）应尽可能提供语义化名称（如 `prd-generation`）。
- 若调用者未提供 `business_task`，L1 Skill 必须在执行步骤中自动生成一个默认值（格式：`auto_<uuid>`，例如 `auto_550e8400-e29b-41d4-a716-446655440000`）。
- **嵌套调用规则**：当 L1 Skill 调用另一个 L1 Skill 时，调用者必须显式传递父级的 `business_task`，子 L1 不得自行生成新值，以保证所有产物归属于同一业务任务。

各章节详细内容要求如下（简要说明）：

- **触发条件**：明确列举哪些场景下 Agent 应调用此 Skill。
- **必须遵守的约定**：列出不可违背的约束。L1 必须声明“不直接操作底层资源”。
- **输入参数**：使用表格。L1 应包含 `business_task`（非必填，但强烈推荐）。
- **输出参数**：至少包含 `status` 和 `message`。
- **执行步骤**：有序列表。L1 必须包含创建执行目录、保存输入、调用 SubAgent、生成 `manifest.json` 等。若 `business_task` 未提供，必须增加自动生成逻辑。**重要**：L1 中应描述需要调用的 SubAgent 名称，实际的底层消息路由由 `openclaw.json` 中的 bindings 配置完成（详见第 4.8.5 节）。
- **错误处理**：列出异常及处理策略。
- **安全与权限**：声明敏感资源访问。
- **留痕要求**：统一按第 5 章要求。
- **交互模式**：按第 7 章要求设计。
- **示例**：至少一个调用示例。

#### 3.1.3 完整示例

**L1 协调器 Skill 示例**：`<workspace>/skills/prd-generator/SKILL.md`

```markdown
---
name: prd-generator
description: 根据用户需求生成产品需求文档（PRD）。当用户要求生成 PRD、产品需求文档、需求规格说明书等时使用此技能。
version: 1.0.0
author: 产品团队
level: L1
allowed-tools:
  - read_file
  - write_file
metadata:
  openclaw:
    emoji: "📄"
    requires: {}
---

# PRD 生成协调器

## 触发条件
用户要求生成 PRD、产品需求文档、需求规格说明书等。

## 必须遵守的约定
- 不直接操作底层资源，所有文档撰写由 SubAgent 完成
- 必须生成 `manifest.json`

## 输入参数
| 参数名 | 类型 | 必填 | 说明 |
|-------|------|-----|------|
| business_task | string | 否 | 业务任务名，推荐提供语义化值（如 `problem-diagnosis-tool`）；若未提供则自动生成 `auto_<uuid>` |
| requirement | string | 是 | 用户原始需求描述 |

## 输出参数
| 参数名 | 类型 | 说明 |
|-------|------|------|
| status | string | success/failed/partial |
| prd_path | string | 生成的 PRD 文件路径 |

## 执行步骤
1. 生成 execution_id（UUID）。
2. 确定 business_task：
   - 如果输入参数中已提供 `business_task`，则使用该值；
   - 否则自动生成 `auto_<uuid>`，并记录到 `execution.log`。
3. 创建执行目录：
   - 路径：`<workspace>/trace-workspace/<business_task>/<timestamp>_<execution_id前8位>/`
4. 保存用户输入到 `input/requirement.txt`
5. 调用 SubAgent `prd-writer`（需在 `openclaw.json` 的 bindings 中配置路由），传递 `business_task`, `execution_dir_path`, `requirement`
6. 等待 SubAgent 完成，将产物从 `artifacts/` 移动到 `output/`
7. 生成 `manifest.json`
8. 返回 `{"status": "success", "prd_path": "output/prd.md"}`

## 错误处理
| 错误场景 | 处理动作 |
|----------|----------|
| SubAgent 超时 | 重试一次，仍失败则状态 failed |
| 输出目录不可写 | 终止并报错 |

## 安全与权限
- 仅写入 workspace 目录
- 不执行网络请求

## 留痕要求
按本规范第 5 章要求，创建执行目录，保存输入到 `input/`，产物到 `output/`，生成 `manifest.json`。

## 交互模式
### 交互点 1：需求确认（确认型）
- **触发时机**：接收到用户需求后
- **提示语模板**："收到需求：{requirement}。是否开始生成 PRD？回复 **Y** 继续，**N** 取消。"
- **有效选项**：Y / N
- **无效输入处理**：重新提示

## 示例
输入：`{"business_task": "problem-diagnosis-tool", "requirement": "需要一个用于诊断网络问题的 CLI 工具"}`
输出：`{"status": "success", "prd_path": "output/prd.md"}`
```

**L3 原子 Skill 示例**：`<workspace>/skills/web-fetcher/SKILL.md`

```markdown
---
name: web-fetcher
description: 从指定 URL 获取网页内容并保存到文件。当用户需要下载网页、抓取 HTML 内容时使用此技能。
version: 1.0.0
author: 基础架构组
level: L3
allowed-tools:
  - http_request
  - write_file
metadata:
  openclaw:
    emoji: "🌐"
    requires:
      bins:
        - curl
dependencies:
  - command: "curl"
    min_version: "7.68"
---

# 网页获取器

## 触发条件
需要下载网页内容、抓取 HTML 时。

## 输入参数
| 参数名 | 类型 | 必填 | 说明 |
|-------|------|-----|------|
| url | string | 是 | 目标 URL |
| trace-workspace_path | string | 是 | 保存路径（绝对路径，应位于 `<workspace>/trace-workspace/` 或 `<workspace>/data/` 下） |
| timeout | integer | 否 | 超时秒数，默认 30 |

## 输出参数
| 参数名 | 类型 | 说明 |
|-------|------|------|
| status | string | success/failed |
| file_size | int | 文件大小（字节） |

## 执行步骤
1. 使用 `http_request` 或 `curl` 获取 `url` 内容
2. 将内容写入 `trace-workspace_path`
3. 返回文件大小

## 错误处理
- 网络超时：重试一次，仍失败则 status=failed
- HTTP 状态码非 200：记录错误，返回 failed

## 安全与权限
- 仅允许 HTTP/HTTPS 协议
- 禁止访问内网地址（127.0.0.1, 10.0.0.0/8 等）

## 留痕要求
按本规范第 5.9 节要求，将获取的内容保存到指定路径（调用者负责目录管理）。

## 示例
输入：`{"url": "https://example.com", "trace-workspace_path": "~/.openclaw/workspace/trace-workspace/task/artifacts/page.html"}`
输出：`{"status": "success", "file_size": 1250}`
```

### 3.2 SubAgent 文件规范（AGENTS.md）

OpenClaw 中的 **L2 执行器（SubAgent）** 通过 `openclaw agents add <name>` 命令创建，每个 SubAgent 的配置位于 `~/.openclaw/agents/<agentId>/agent/AGENTS.md`。

#### 3.2.1 文件格式

AGENTS.md 是 OpenClaw 中用于统一声明智能体身份、能力、目标、工作流、约束与输出格式的核心配置文件。核心字段如下：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `# Agent:` | string | ✅ | SubAgent 名称，唯一标识 |
| `## 目的` | string | ✅ | 详细描述 SubAgent 的职责 |
| `## 职责` | list | 推荐 | 具体职责列表 |
| `## 可用技能` | list | 推荐 | 可调用的 L3 Skill 名称列表 |
| `## 约束` | list | 可选 | 约束条件 |
| `## 输出格式` | object | 推荐 | 输出格式规范 |

#### 3.2.2 完整示例

文件：`~/.openclaw/agents/competitor-worker/agent/AGENTS.md`

```markdown
# Agent: competitor-worker

## 目的
根据竞品名称生成对比报告。

## 职责
- 针对给定的本产品名称和竞品列表，从公开渠道获取信息
- 生成结构化对比报告

## 可用技能
- web-fetcher（L3）
- html-parser（L3）
- report-writer（L3）

## 约束
- 必须遵守 robots.txt
- 请求间隔至少 1 秒

## 输出格式
- 格式：markdown
- 语言：zh-CN
```

#### 3.2.3 创建与调用

```bash
# 创建 SubAgent（交互式）
openclaw agents add competitor-worker

# 查看已创建的 SubAgent
openclaw agents list
```

主 Agent 或 L1 Skill 通过 SubAgent 名称调用（具体调用方式依赖于 `openclaw.json` 中的 bindings 配置）。

#### 3.2.4 L1 调用 L2 的路由配置（必须）

> **关键原则**：L1 Skill 不能直接“唤起”L2 SubAgent。Agent 之间的调用需要通过 OpenClaw Gateway 的 **routing bindings** 机制完成。

**配置步骤**：

1. **创建 SubAgent**（如上）
2. **编辑 `~/.openclaw/config/openclaw.json`**，在 `agents.list` 中声明所有 SubAgent，并在 `bindings` 中配置路由规则：

   ```json
   {
     "agents": {
       "list": [
         { "id": "prd-writer", "model": "gemini-1.5-pro" },
         { "id": "competitor-worker", "model": "groq-llama-3" }
       ]
     },
     "channels": {
       "telegram": {
         "bindings": [
           { "agentId": "prd-writer", "chatId": "文档生成专用群组" },
           { "agentId": "competitor-worker", "chatId": "竞品调研专用群组" }
         ]
       }
     }
   }
   ```

3. **L1 Skill 中的调用描述**：在 L1 协调器 Skill 的“执行步骤”中描述需要调用哪个 SubAgent 以及传递哪些参数。

**核心理解**：`openclaw.json` 中 `agents.list` 和 `bindings` 的配置是实现 L1→L2 调用的“总控开关”。主 Agent 接收到 L1 Skill 的请求后，根据 bindings 规则将消息路由到对应的 SubAgent，从而完成跨层调用。如果 bindings 未正确配置，即使 L1 Skill 中写明“调用 SubAgent X”，OpenClaw 也无法将消息路由到正确的 SubAgent。

### 3.3 目录与命名规范

- **Skill 目录名**：小写字母 + 连字符，如 `file-batch-rename`。禁止大写字母、下划线、空格、连续连字符。
- **SKILL.md 文件名**：固定为 `SKILL.md`，大小写敏感。
- **SubAgent ID**：小写字母 + 连字符，如 `competitor-worker`，对应 `~/.openclaw/agents/<agentId>/` 目录名。
- **业务域（domain）**：Skill 目录名第一个连字符前的部分，建议使用常见前缀（如 `web`、`file`、`convert`），新增域需在附录 D 中注册。

---

## 4. 三层架构中 Skill、SubAgent 的职责

### 4.1 角色总览

| 角色 | 载体 | 职责 | 特殊要求 |
|------|------|------|----------|
| **L1 协调器** | Skill（`SKILL.md`） | 描述整体流程：分解任务、调用 SubAgent、异常处理 | - 优先通过 SubAgent 完成子任务<br>- 允许直接调用 L3（满足 4.5 节条件）<br>- 输入参数应包含 `business_task`；若未提供则自动生成<br>- 负责创建执行目录、生成 `manifest.json` |
| **L2 执行器** | SubAgent（`AGENTS.md` via `openclaw agents add`） | 执行边界清晰的独立子任务，可调用 L3 Skill | - 独立工作区和记忆<br>- 只能调用可用技能列表中声明的 L3<br>- 产物写入主工作区 `trace-workspace/`<br>- **L1 对 L2 的调用须通过 bindings 路由配置** |
| **L3 原子操作** | Skill（`SKILL.md`） | 不可再分的操作单元 | - 执行步骤 ≤5，每步为单一工具调用<br>- 幂等且无副作用<br>- 可使用简化模板（附录 C）<br>- 无子任务调用（不能调用其他 L3 或 SubAgent） |

### 4.2 L1 协调器 Skill 的详细职责

- **编排而非执行**：不直接操作底层资源（文件系统、网络、数据库等），只负责调用 SubAgent 或（在特定条件下）直接调用 L3 Skill。
- **输入参数**：应包含 `business_task`；若未提供，则必须在执行步骤中自动生成默认值（格式 `auto_<uuid>`），并记录到 `execution.log`。
- **执行步骤**：必须包含创建执行目录、保存输入、描述需要调用的 SubAgent 及参数、生成 `manifest.json` 等。**注意**：L1 负责描述调用关系，实际的 SubAgent 路由由 `openclaw.json` 中的 bindings 配置完成。
- **错误处理**：定义整体流程的异常处理策略，如重试、降级、终止。

### 4.3 L2 执行器（SubAgent）的详细职责

#### 4.3.1 定义与部署

- SubAgent 应通过 `openclaw agents add <agentId>` 命令创建。
- 其行为通过在 `~/.openclaw/agents/<agentId>/agent/AGENTS.md` 中定义（目的、职责、可用技能、约束等）。
- L1 Skill 通过 bindings 路由配置调用 SubAgent，**调用关系必须在 `openclaw.json` 中显式配置**。

#### 4.3.2 权限与隔离

- 每个 SubAgent 拥有独立的工作区（`agent` 目录）、记忆（`MEMORY.md`）和会话（`sessions/`）。
- 只能调用 `可用技能` 列表中声明的 L3 Skill。
- 执行完毕后会话保留，可持久化状态。

#### 4.3.3 留痕与产物继承

- 必须继承父 L1 的 `business_task`。
- 产物写入主工作区的 `trace-workspace/` 下（通过父 L1 传递的 `execution_dir_path`），不得创建新执行目录。

### 4.4 L3 原子 Skill 的详细职责

- **原子性**：每个 L3 Skill 代表一个不可再分的操作单元。执行步骤 ≤5，且每一步均为单一工具调用（如 `read_file`, `write_file`, `http_request` 等）。禁止在单个 `bash` 调用中通过管道串联多个业务步骤。
- **幂等性与无副作用**：优先设计幂等操作；多次调用同一 L3 Skill 应产生相同结果（或可预期）。不应修改全局状态或产生不可逆的副作用。
- **无子任务调用**：L3 Skill 不能调用其他 L3 Skill，也不能创建 SubAgent。组合需求应上升至 L1 或 L2 完成。
- **输入输出简洁**：输入参数不宜超过 5 个，输出至少包含 `status` 和必要结果。
- **留痕**：按本规范第 5.9 节要求，将生成的产物保存到调用者指定的路径，不自行创建执行目录。
- **依赖声明**：必须在 `metadata.openclaw.requires.bins` 中声明所需的外部二进制，否则该 Skill 会被过滤，不会出现在 Agent 的系统提示词中。
- **可简化模板**：允许使用附录 C 中的 L3 简化模板，省略“必须遵守的约定”“交互模式”等章节。

### 4.5 L1 直接调用 L3 的适用条件

L1 协调器在满足以下所有条件时，可以直接调用 L3 原子 Skill，而不必通过 SubAgent：
1. 操作简单快速（单一工具调用，无长时间 I/O）
2. 无外部依赖或副作用
3. 数据量小（< 10KB）
4. L3 文档未标注“仅限 SubAgent 调用”

### 4.6 必须使用 SubAgent 的场景

| 场景 | 说明 |
|------|------|
| 并行执行 | 同时执行多个独立子任务 |
| 上下文隔离 | 子任务产生大量中间输出 |
| 独立重试/回滚 | 需要独立错误处理 |
| 持久化会话 | 复用 SubAgent 状态 |
| 复杂多步骤 | 子任务包含分支/循环逻辑 |

### 4.7 决策示例

| 场景 | 推荐方式 |
|------|----------|
| 合并两个 CSV 文件 | 直接调用 L3 `csv-to-json` |
| 同时下载 10 个网页 | 使用 SubAgent 并行调用 |
| 分析 2GB 日志 | 使用 SubAgent |

### 4.8 各层级行为规范（必须与禁止）

本规范为 L1、L2、L3 分别定义了强制性行为（**必须**）和红线行为（**禁止**）。任何违反“禁止”条款的组件均视为架构违规，不予合入。

#### 4.8.1 L1 协调器 Skill 行为规范

| 类型 | 规范要求 |
|------|----------|
| ✅ **必须** | 1. 若输入参数中未提供 `business_task`，则必须自动生成默认值（格式 `auto_<uuid>`）并记录日志。<br>2. 在执行步骤中创建执行目录（`<workspace>/trace-workspace/<business_task>/<timestamp>/`），并生成 `manifest.json`。<br>3. 对于复杂、并行、需要独立上下文的子任务，必须通过调用 SubAgent 完成。<br>4. 必须处理所有可能的错误，并返回 `status`（success/failed/partial）。<br>5. 必须在 `留痕要求` 章节中引用第 5 章的规范。<br>6. **必须确保 SubAgent 的调用路由在 `openclaw.json` 的 bindings 中已配置**。 |
| ❌ **禁止** | 1. 直接读写数据库、调用外部 HTTP API 或执行长时间 I/O（除非该操作已封装为 L3 且满足 4.5 节条件）。<br>2. 在 L1 的执行步骤中编写超过 5 个步骤的复杂逻辑（应拆分为 SubAgent）。<br>3. 忽略子任务返回的错误或吞掉异常不向上层报告。<br>4. 在 `business_task` 中使用非小写字母、连字符以外的字符（自动生成的 `auto_` 前缀除外）。 |

#### 4.8.2 L2 SubAgent 行为规范

| 类型 | 规范要求 |
|------|----------|
| ✅ **必须** | 1. 在 `~/.openclaw/agents/<agentId>/agent/AGENTS.md` 中定义目的、职责和可用技能。<br>2. 所有产物必须写入主工作区的 `trace-workspace/` 下（通过父 L1 传递的 `execution_dir_path`）。<br>3. 如果 SubAgent 需要与用户交互，必须遵循第 7 章的缰绳编程原则。<br>4. 在独立的子工作区中执行所有任务，与主 Agent 工作区完全隔离。SubAgent 的记忆、会话均独立于主会话，不得污染或干扰主会话的状态。 |
| ❌ **禁止** | 1. 创建新的执行目录（如 `<workspace>/trace-workspace/xxx`），应使用父 L1 传递的 `execution_dir_path`。<br>2. 调用未在 `可用技能` 中声明的 L3 Skill。<br>3. 修改其他 SubAgent 的工作区文件。<br>4. 在 SubAgent 中再次创建 SubAgent（禁止嵌套）。 |

#### 4.8.3 L3 原子 Skill 行为规范

| 类型 | 规范要求 |
|------|----------|
| ✅ **必须** | 1. 执行步骤（`执行步骤` 章节）数量 ≤5。<br>2. 每个步骤必须对应单一工具调用（如 `read_file`, `write_file`, `http_request`, `bash` 执行单个命令）。<br>3. 设计为幂等操作（多次调用结果一致，无不可逆副作用）。<br>4. 输出参数至少包含 `status`（success/failed）。<br>5. 产物保存路径由调用者通过参数传递，L3 自身不创建执行目录。<br>6. 必须在 `metadata.openclaw.requires.bins` 中声明所需的外部二进制。 |
| ❌ **禁止** | 1. 在单个 `bash` 调用中使用管道 `\|`、`&&` 或 `;` 串联多个业务步骤（例如 `cat a.txt \| grep foo \| sort > out.txt` 禁止）。<br>2. 调用其他 L3 Skill 或创建 SubAgent。<br>3. 自行生成 `execution_id` 或创建时间戳目录。<br>4. 修改全局状态（如修改系统环境变量、写入 `/etc` 等）。 |

#### 4.8.4 正反示例对比

| 层级 | ✅ 正确做法 | ❌ 错误做法 |
|------|-------------|--------------|
| **L1** | 调用 SubAgent `prd-writer` 生成文档；若未提供 `business_task`，自动生成 `auto_xxx`。 | 在 L1 中直接调用 `http_request` 获取数据并写入文件。 |
| **L2** | 在 `AGENTS.md` 的 `可用技能` 中声明 `["web-fetcher"]`，并使用该 L3 抓取网页。 | 在 SubAgent 中调用未声明的 `database-query` L3。 |
| **L3** | 步骤：`1. 使用 bash 运行 `wc -l file.txt`，输出行数。` | 步骤：`1. 使用 bash 运行 `cat a.txt \| grep keyword \| sort > result.txt``（管道串联）。 |

#### 4.8.5 L1 调用 L2 的路由配置规范

本规范要求 L1 Skill 与 L2 SubAgent 之间的调用必须通过 `openclaw.json` 中的 **routing bindings** 完成。具体配置规范如下：

**配置要求**：
1. 所有 L2 SubAgent 必须在 `openclaw.json` 的 `agents.list` 中声明。
2. 必须在 `channels.<channel>.bindings` 中配置消息到 SubAgent 的路由规则。
3. L1 Skill 的“执行步骤”中描述需要调用的 SubAgent 及参数，Gateway 根据 bindings 完成实际路由。

**配置示例**（`~/.openclaw/config/openclaw.json`）：

```json
{
  "agents": {
    "list": [
      { "id": "prd-writer", "model": "gemini-1.5-pro" },
      { "id": "competitor-worker", "model": "groq-llama-3" }
    ]
  },
  "channels": {
    "telegram": {
      "bindings": [
        { "agentId": "prd-writer", "chatId": "文档生成专用群组" },
        { "agentId": "competitor-worker", "chatId": "竞品调研专用群组" }
      ]
    }
  }
}
```

**部署检查**：团队成员部署时，必须根据各自的渠道 ID 修改 bindings 配置中的 `chatId` 等参数，确保路由正确。

---

## 5. 留痕规范（产物与过程记录）

### 5.1 设计目标

- **固定输出根目录**：`<workspace>/trace-workspace/`
- **按业务任务组织**：`<business_task>/` 作为一级目录
- **按执行实例打包**：每次 L1 执行创建独立时间戳目录 `YYYYMMDD_HHMMSS_<execution_id前8位>/`
- **产物优先**：重点保存实质性产物，而非详细步骤日志
- **保留关键信息**：通过 `manifest.json` 和 `execution.log` 记录元数据与关键事件

### 5.2 存储路径

| 环境 | 留痕根目录 | 完整路径示例（Linux） |
|------|-----------|---------------------|
| 开发态/部署态 | `<workspace>/trace-workspace/` | `~/.openclaw/workspace/trace-workspace/prd/20260529_100000_abc123/` |

### 5.3 执行目录内文件规范

| 名称 | 类型 | 必选 | 说明 |
|------|------|------|------|
| `manifest.json` | 文件 | ✅ | 执行元数据（见 5.4） |
| `execution.log` | 文件 | 推荐 | 简易文本日志 |
| `input/` | 目录 | 推荐 | 原始输入副本 |
| `output/` | 目录 | ✅ | 最终产物 |
| `artifacts/` | 目录 | 可选 | 中间产物 |

### 5.4 执行清单（manifest.json）规范

`manifest.json` 由 L1 Skill 在**执行结束时**生成，至少包含：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `execution_id` | string | ✅ | UUID |
| `business_task` | string | ✅ | 业务任务名（若自动生成则记录生成值） |
| `skill_name` | string | ✅ | L1 Skill 名称 |
| `start_time` | string | ✅ | ISO 8601 |
| `end_time` | string | ✅ | ISO 8601 |
| `status` | string | ✅ | success/failed/partial |
| `output_files` | array | ✅ | 产物列表（相对路径、size_bytes） |
| `sub_executions` | array | 可选 | 子任务信息 |
| `error` | object | 可选 | 错误信息（含 code, message） |

### 5.5 简易执行日志（execution.log）

推荐记录：任务启动、输入确认、子任务调用/返回、异常、任务结束。每行包含时间戳和事件描述。

### 5.6 父子调用链与产物继承

- L1 Skill 创建执行目录后，调用子任务时传递 `execution_dir_path` 和 `parent_execution_id`。
- 子任务将产物写入父级 `trace-workspace/` 下，不得创建新执行目录。

### 5.7 L1 Skill 中对 `business_task` 的生成与传递规则

- 若输入参数中已提供 `business_task`，则直接使用该值。
- 若未提供，则 L1 必须自动生成默认值（格式 `auto_<uuid>`），并记录到 `execution.log`。
- **嵌套调用时**：如果 L1 调用另一个 L1，调用者必须将当前 `business_task` 显式传递给子 L1，子 L1 不得自行生成新值。

### 5.8 任务恢复时的处理

- 默认每次调用生成新 `execution_id` 和新目录。
- 可选增强：实现状态持久化后可复用原 `execution_id`，继续追加产物和日志。

### 5.9 L3 原子 Skill 的留痕说明

L3 原子 Skill **不创建执行目录**，也不生成 `manifest.json`。其留痕行为如下：
- 所有产物（如转换后的文件、下载的内容等）必须保存到**调用者通过输入参数提供的路径**（通常是 `execution_dir_path/output/` 或 `execution_dir_path/artifacts/`）。
- L3 Skill 的 `留痕要求` 章节应统一表述为：“按本规范第 5.9 节要求，将生成的产物保存到调用者指定的 `trace-workspace_path` 或类似参数中。”
- 若 L3 需要记录日志，应追加写入调用者提供的 `execution.log` 文件（路径由调用者传递）。

---

## 6. 通用原则

1. **单一职责**：每个 Skill/SubAgent 只完成一个明确的任务，避免“万能”组件。
2. **可声明性**：组件的行为必须通过标准化章节完全描述，不依赖隐含知识。
3. **幂等性与安全性**：优先设计幂等操作；涉及敏感资源必须声明权限。
4. **留痕强制**：
   - L1 Skill 必须按第 5.1–5.8 节创建执行目录、生成 `manifest.json`，并正确生成或传递 `business_task`。
   - L3 Skill 必须按第 5.9 节将产物保存到调用者指定路径。
5. **层级标记**：Skill 必须通过 `level` 字段标记其类型（`L1` 或 `L3`），并遵循对应层级的设计约束。
6. **依赖显式声明**：L3 Skill 必须在 `metadata.openclaw.requires.bins` 中声明所有外部二进制依赖；L2 SubAgent 必须在 `AGENTS.md` 中声明可用技能。
7. **路由配置显式声明**：L1 Skill 与 L2 SubAgent 之间的调用关系必须在 `openclaw.json` 的 bindings 中显式配置，不得依赖隐含或自动的路由规则。
8. **确定优先（缰绳编程）**：组件在与用户交互时，应遵循 **“选项优先，必要时允许自由输入，但须明确约束”** 的原则（详见第 7 章）。

---

## 7. 交互模式要求（缰绳编程）

### 7.1 核心原则

> **凡是 AI 可以做出决策的地方，必须提供有限的、明确的选项；凡是必须由用户提供自由内容的地方，应给出清晰的格式、长度、取值范围等约束，避免 AI 自行推断或截断。**

### 7.2 交互类型分类

| 交互类型 | 定义 | 要求 | 示例 |
|---------|------|------|------|
| **确认型** | 需要用户确认是否继续执行 | 必须提供有限选项（如 Y/N，或 1/2/3） | “是否继续？回复 **Y** 继续，**N** 取消。” |
| **选择型** | 从多个预定义选项中挑选一个 | 必须列出所有选项，使用序号或单字符 | “请选择输出格式：**1**=JSON，**2**=CSV，**3**=表格。” |
| **枚举参数型** | 参数值可以从有限集合中选取 | 必须列出可选项，并标注默认值 | “请选择时区：**1**=UTC+8，**2**=UTC+0，**3**=UTC-5（默认 1）。” |
| **自由输入型** | 需要用户提供自定义内容 | 必须给出格式、长度、合法性约束；禁止 AI 自行补充或修改 | “请输入项目描述（不超过 200 字，支持中英文、数字、空格）：” |

### 7.3 错误与正确示例对照

| 场景 | ❌ 错误示例 | ✅ 正确示例 |
|------|------------|------------|
| **确认型** | “是否开始执行？” | “是否开始执行？回复 **Y** 继续，**N** 取消。” |
| **选择型** | “请指定要处理的文件。” | “发现以下文件：`a.txt`、`b.txt`、`c.txt`。请输入序号（1-3）或输入 **all** 处理全部。” |
| **枚举参数型** | “请设置超时时间。” | “请选择超时时间：**1**=30秒，**2**=60秒，**3**=120秒（默认 2）。” |
| **自由输入型** | “请输入备注。” | “请输入备注（纯文本，不超过 200 字符，禁止换行）：” |

### 7.4 自由输入型交互的约束规范

| 约束项 | 说明 | 是否必填 |
|--------|------|----------|
| **数据类型** | 文本、数字、路径、JSON 等 | ✅ |
| **格式要求** | 正则表达式、示例格式 | 推荐 |
| **长度/范围限制** | 最大/最小长度、数值范围 | 推荐 |
| **合法性验证规则** | 如“必须存在的文件” | 推荐 |
| **默认值** | 用户不输入时使用的值 | 可选 |

### 7.5 必须使用选项式/确认式的场景

以下场景**禁止**使用自由输入：
1. 确认破坏性操作（如删除文件、发送邮件）。
2. 分支选择（如“选择处理模式”）。
3. 参数值来自已知枚举集合。

### 7.6 交互模式章节的通用模板

```markdown
## 交互模式

### 交互点 1：[名称]（[类型]）
- **触发时机**：...
- **提示语模板**：...
- **有效选项**（仅确认/选择/枚举）：...
- **数据类型/格式限制**（仅自由输入）：...
- **默认值**：...
- **无效输入处理**：...
```

**若 SubAgent 需要与用户交互，其交互模式同样应遵循本规范所有要求。**

---

## 8. 部署验证与故障排查

为确保所编写的 Skill 与 SubAgent 在部署后能正常工作，开发者必须执行以下验证步骤。

### 8.1 核心 CLI 验证命令

| 验证对象 | CLI 命令 | 预期结果 | 故障排查指引 |
| :--- | :--- | :--- | :--- |
| **所有 Skill** | `openclaw skills list` | 输出中包含已部署的 Skill 名称 | - 检查 Skill 目录是否在 `<workspace>/skills/` 下。<br>- 确认 `SKILL.md` 文件名与目录名一致。<br>- 重启 Gateway：`openclaw gateway restart` |
| **L2 SubAgent** | `openclaw agent list` | 输出中包含已创建的 SubAgent 名称 | - 确认已通过 `openclaw agents add <name>` 创建。<br>- 检查 `~/.openclaw/agents/<agentId>/agent/AGENTS.md` 文件是否存在。 |
| **OpenClaw 平台** | `openclaw --version` | 正常输出版本号，无报错信息 | - 检查 OpenClaw 是否正确安装。<br>- 尝试重启 Gateway 服务。 |
| **路由配置** | `openclaw agents bindings --json` | 输出中包含配置的 bindings 规则 | - 确认 `openclaw.json` 中 bindings 格式正确。<br>- 检查 bindings 中的 `agentId` 与 `agents.list` 中的 `id` 一致。 |

**使用示例**：
```bash
# 验证 Skill 是否部署成功
$ openclaw skills list
prd-generator - L1 - 根据用户需求生成产品需求文档（PRD）
web-fetcher - L3 - 从指定 URL 获取网页内容并保存到文件

# 验证 SubAgent 是否部署成功
$ openclaw agent list
competitor-worker - 根据竞品名称生成对比报告
code-reviewer - 代码审查专家
sql-query-worker - SQL 查询执行器

# 验证路由配置
$ openclaw agents bindings --json
```

### 8.2 自动化验证（适用于 CI/CD）

在持续集成或自动化部署流程中，可以使用以下命令进行静默验证：

```bash
# 检查特定 Skill 是否存在
openclaw skills list | grep -q "prd-generator"

# 检查特定 SubAgent 是否存在
openclaw agent list | grep -q "competitor-worker"

# 检查 bindings 配置（假设 jq 已安装）
openclaw agents bindings --json | jq -e '.[] | select(.agentId=="prd-writer")'

# 若上述命令返回非零退出码，则表示未部署成功
```

### 8.3 交互式快速冒烟测试

完成 CLI 验证后，建议在 OpenClaw 交互界面中进行快速冒烟测试：

1. **启动 OpenClaw**：运行 `openclaw` 进入交互模式。
2. **查看 Skill 列表**：输入 `/skills`，确认列表中包含已部署的 L1 和 L3 Skill。
3. **查看 SubAgent 列表**：输入 `/agents`，确认列表中包含已部署的 L2 SubAgent。
4. **触发调用**：
   - 对于 Skill：输入自然语言描述，尝试触发 `触发条件` 中定义的场景。
   - 对于 SubAgent：根据 Gateway 路由配置（如 `@agent-name`）进行调用。

### 8.4 常见问题与排查

| 问题现象 | 可能原因 | 排查步骤 |
|----------|----------|----------|
| `skills list` 找不到我的 Skill | 目录位置错误或依赖缺失 | 1. 确认 Skill 目录在 `<workspace>/skills/` 下。<br>2. 检查 `metadata.openclaw.requires.bins` 中的二进制是否已安装。<br>3. 运行 `openclaw gateway restart` 后重试。 |
| `agent list` 找不到我的 SubAgent | 未正确创建或配置错误 | 1. 确认已运行 `openclaw agents add <name>`。<br>2. 检查 `~/.openclaw/agents/<agentId>/agent/AGENTS.md` 文件是否存在。 |
| L1 Skill 无法调用 L2 SubAgent | bindings 路由配置缺失或错误 | 1. 检查 `openclaw.json` 中 `agents.list` 是否声明了 SubAgent。<br>2. 检查 `bindings` 中的 `agentId` 是否正确。<br>3. 运行 `openclaw agents bindings --json` 验证配置。 |
| L3 Skill 未被加载 | 依赖检查失败 | 运行 `which <binary>` 检查所需二进制是否在 PATH 中。OpenClaw 在加载时会根据 `metadata.openclaw.requires.bins` 进行过滤，缺失则 Skill 不会出现在系统提示中。 |
| 部署后重启仍不生效 | 缓存未刷新 | 运行 `openclaw gateway restart` 强制重启 Gateway。 |

### 8.5 验证通过标准

一个部署的 Skill 或 SubAgent 被认为“验证通过”，当满足以下所有条件：

1. ✅ `openclaw skills list` 或 `openclaw agent list` 能列出该组件。
2. ✅ 在 TUI 中 `/skills` 或 `/agents` 命令能看到该组件。
3. ✅ 能够成功触发一次基本的调用（例如通过自然语言或 `@` 提及）。
4. ✅ 执行后留痕目录（第 5 章）正常生成 `manifest.json` 和产物。
5. ✅（如涉及 L1→L2 调用）bindings 路由配置验证通过，调用链路正常。

---

## 9. 规范遵守检查清单

### 9.1 通用结构检查

| # | 检查项 | 对应章节 |
|---|--------|----------|
| 1 | `SKILL.md` 包含必要的正文章节 | 3.1.2 |
| 2 | Frontmatter 包含 `name`, `description`, `level`（值为 L1/L3） | 3.1.1 |
| 3 | 目录名与 `name` 一致，且符合命名规范，domain 已注册 | 3.3 |
| 4 | L3 Skill 声明了 `metadata.openclaw.requires.bins` | 3.1.1 |

### 9.2 交互与行为检查

| # | 检查项 | 对应章节 |
|---|--------|----------|
| 5 | 决策型交互采用选项式，自由输入有明确约束 | 7 |
| 6 | SubAgent 交互遵循缰绳编程 | 4.3.2, 7 |

### 9.3 L1 专用检查

| # | 检查项 | 对应章节 |
|---|--------|----------|
| 7 | 输入参数应包含 `business_task`，或 Skill 实现了自动生成逻辑 | 3.1.2, 4.2 |
| 8 | 执行步骤包含创建目录、保存输入、生成 manifest.json | 3.1.2, 5 |
| 9 | 直接调用 L3 满足适用条件 | 4.5 |
| 10 | 步骤中明确写出 SubAgent 或 L3 调用 | 3.1.2 |
| 11 | 生成 `manifest.json`，产物在 `output/` 下 | 5.4, 5.5 |

### 9.4 L3 专用检查

| # | 检查项 | 对应章节 |
|---|--------|----------|
| 12 | 执行步骤 ≤5，每步为单一工具调用，幂等无副作用 | 4.4 |
| 13 | 可使用简化模板 | 附录 C |
| 14 | 留痕要求符合第 5.9 节（不自行创建执行目录） | 5.9 |
| 15 | 声明了 `metadata.openclaw.requires.bins` | 3.1.1 |

### 9.5 SubAgent 与权限检查

| # | 检查项 | 对应章节 |
|---|--------|----------|
| 16 | SubAgent 通过 `openclaw agents add` 命令创建 | 3.2 |
| 17 | SubAgent 在 `AGENTS.md` 中定义了目的和可用技能 | 3.2.2 |
| 18 | 无命名冲突 | 3.3 |
| 19 | L1→L2 调用路由已在 `openclaw.json` 的 bindings 中配置 | 3.2.4, 4.8.5 |

### 9.6 部署验证检查

| # | 检查项 | 对应章节 |
|---|--------|----------|
| 20 | 执行 `openclaw skills list` 验证 Skill 已加载 | 8.1 |
| 21 | 执行 `openclaw agent list` 验证 SubAgent 已加载 | 8.1 |
| 22 | 进行至少一次交互式冒烟测试 | 8.3 |
| 23 | 验证 bindings 路由配置 | 8.1 |

### 9.7 各层级行为规范检查

| # | 检查项 | 对应章节 |
|---|--------|----------|
| 24 | L1 未直接操作底层资源（如直接调用 API） | 4.8.1 |
| 25 | SubAgent 未创建新执行目录 | 4.8.2 |
| 26 | L3 未使用管道串联业务步骤 | 4.8.3 |

---

## 10. 附录

### 附录 A：L1 协调器 Skill 简化模板

```markdown
---
name: your-orchestrator
description: 一句话描述此协调器的功能。当用户需要XXXX时使用此技能。
version: 1.0.0
author: 你的名字
level: L1
allowed-tools:
  - read_file
  - write_file
metadata:
  openclaw:
    emoji: "🎯"
    requires: {}
---

# 协调器标题

## 触发条件
（描述哪些用户输入或场景会触发此 Skill）

## 必须遵守的约定
- 不直接操作底层资源，所有子任务通过 SubAgent 完成
- 必须生成 `manifest.json`

## 输入参数
| 参数名 | 类型 | 必填 | 说明 |
|-------|------|-----|------|
| business_task | string | 否 | 业务任务名，推荐提供语义化值；若未提供则自动生成 `auto_<uuid>` |
| （其他参数） | ... | ... | ... |

## 输出参数
| 参数名 | 类型 | 说明 |
|-------|------|------|
| status | string | success/failed/partial |
| message | string | 结果描述 |

## 执行步骤
1. 生成 execution_id（UUID）。
2. 确定 business_task：若未提供则自动生成 `auto_<uuid>`，并记录到 execution.log。
3. 创建执行目录：
   - 路径：`<workspace>/trace-workspace/<business_task>/<timestamp>_<execution_id前8位>/`
4. 保存用户输入到 `input/`。
5. 调用 SubAgent（需在 `openclaw.json` 的 bindings 中配置路由），传递 `business_task`, `execution_dir_path` 及其他必要参数。
6. 汇总产物到 `output/`，生成 `manifest.json`。
7. 返回结果。

## 错误处理
| 错误场景 | 处理动作 |
|----------|----------|
| SubAgent 超时 | 重试一次，仍失败则状态 failed |
| 目录创建失败 | 终止并报错 |

## 安全与权限
（列出访问的敏感资源，若无则写“无”）

## 留痕要求
按本规范第 5 章要求，创建执行目录，保存输入到 `input/`，产物到 `output/`，生成 `manifest.json`。

## 交互模式
（如有交互点，按缰绳编程原则描述）

## 示例
输入：`{ "business_task": "example", ... }`
输出：`{ "status": "success", ... }`
```

### 附录 B：L2 SubAgent 简化模板（AGENTS.md）

```markdown
# Agent: your-agent-name

## 目的
一句话描述此 SubAgent 的功能。

## 职责
- 职责1
- 职责2

## 可用技能
- web-fetcher（L3）
- html-parser（L3）

## 约束
- 约束条件1

## 输出格式
- 格式：json/markdown/text
- 语言：zh-CN
```

### 附录 C：L3 原子 Skill 简化模板

```markdown
---
name: your-atomic-skill
description: 一句话描述此原子操作的功能。当用户需要XXXX时使用此技能。
version: 1.0.0
author: 你的名字
level: L3
allowed-tools:
  - read_file
  - write_file
  - bash
metadata:
  openclaw:
    emoji: "🔧"
    requires:
      bins:
        - curl
---

# 原子技能标题

## 触发条件
（一句话描述何时调用）

## 输入参数
| 参数名 | 类型 | 必填 | 说明 |
|-------|------|-----|------|
| input_path | string | 是 | 输入文件路径 |
| trace-workspace_path | string | 是 | 输出文件路径（由调用者提供） |
| （其他参数） | ... | ... | ... |

## 输出参数
| 参数名 | 类型 | 说明 |
|-------|------|------|
| status | string | success/failed |
| size | int | 输出文件大小（可选） |

## 执行步骤
1. 使用 `read_file` 或 `bash` 读取输入
2. 执行单一原子操作（如格式转换、计算等）
3. 将结果写入 `trace-workspace_path`

## 错误处理
（一句话说明，如“遇到错误则返回 status=failed”）

## 安全与权限
（无特殊要求写“无”）

## 留痕要求
按本规范第 5.9 节要求，将生成的产物保存到调用者指定的 `trace-workspace_path`，不自行创建执行目录。

## 示例
输入：`{ "input_path": "/path/to/input.csv", "trace-workspace_path": "~/.openclaw/workspace/trace-workspace/result.json" }`
输出：`{ "status": "success", "size": 1024 }`
```

### 附录 D：推荐业务前缀速查表

| 业务域（domain） | 前缀 | 示例 Skill 名称 |
|----------------|------|----------------|
| 文件处理 | `file` | `file-batch-rename` |
| 数据转换 | `convert` | `convert-csv-to-json` |
| 网络/网页 | `web` | `web-fetcher` |
| 文本处理 | `text` | `text-replace` |
| 系统操作 | `sys` | `sys-list-processes` |
| 邮件 | `mail` | `mail-send` |
| 图像处理 | `img` | `img-resize` |
| 日志 | `log` | `log-analyzer` |

> 新增 domain 必须更新本表并通知全体成员。

---

**规范制定人**：江维  
**生效日期**：2026年5月29日