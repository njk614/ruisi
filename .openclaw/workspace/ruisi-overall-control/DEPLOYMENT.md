# Overall Control Skill 部署说明

## ✅ 部署前检查

### 1. 文件清单

```
ruisi-overall-control/
├── SKILL.md                    ✅ Skill 定义
├── config.yaml                 ✅ 配置文件（已配置设备ID）
├── requirements.txt            ✅ Python 依赖
├── agents/
│   └── orchestrator.md         ✅ Agent 编排器
├── scripts/
│   ├── mqtt_controller.py      ✅ MQTT 控制
│   ├── send_feedback.py        ✅ 反馈推送
│   ├── zone_context.py         ✅ 区域管理
│   └── environment_query.py    ✅ 环境查询
└── references/
    ├── zone-device-mapping.md
    ├── device-control-api.md
    └── environment-data-format.md
```

### 2. 依赖检查

```bash
pip install -r requirements.txt
```

需要的包：

- paho-mqtt>=2.0.0
- pyyaml>=6.0
- requests>=2.31.0

## 🚀 在 OpenClaw 中测试

### 用户指令测试

直接在 OpenClaw 中发送自然语言指令：

```
1. "大会议室开灯"
   → 预期：灯光打开，收到反馈消息

2. "开空调"
   → 预期：询问区域，选择后空调打开

3. "空调24度"
   → 预期：空调打开并设置为24℃

4. "关闭门厅空调"
   → 预期：门厅空调关闭

5. "大会议室关灯"
   → 预期：大会议室灯光关闭
```

### OpenClaw 执行流程

```
用户输入 → OpenClaw 触发 ruisi-overall-control skill
         ↓
    读取 agents/orchestrator.md
         ↓
    LLM 解析语义（提取参数）
         ↓
    调用 scripts/mqtt_controller.py（MQTT 控制）
         ↓
    调用 scripts/send_feedback.py（推送反馈）
         ↓
    返回结果给用户
```

## 📋 MQTT 协议说明

### 灯光控制

- Topic: `office/control/light`
- 格式: `{"devsId":"设备ID", "status":"on/off"}`

### 空调开关

- Topic: `office/control/wkq`
- 格式: `{"devsId":"设备ID", "status":"on/off"}`

### 空调温度

- Topic: `office/control/{设备ID}/temp`
- 格式: 温度值（字符串，如 "24"）

## 🔍 故障排查

### 问题：灯光/空调不响应

1. 检查设备 ID 是否正确（config.yaml）
2. 检查 MQTT Broker 连接（60.204.215.30:1883）
3. 检查认证信息是否正确

### 问题：反馈消息未收到

1. 检查 XMPP API 是否运行（http://127.0.0.1:18900/send）
2. 检查设备 JID 配置（config.yaml）

### 问题：区域识别错误

1. 用户指令中明确指定区域
2. 或者先设置 current_zone 上下文

## 📝 留痕位置

执行记录会保存在：

```
.openclaw/workspace/trace-workspace/<business_task>/<timestamp>/
```

## ✨ 支持的场景

- ✅ 开关灯（指定区域/全部设备）
- ✅ 开关空调（指定区域/全部设备）
- ✅ 设置空调温度（16-30℃）
- ✅ 自动环境调节（由 ruisi-video-perceptionflow 触发）

---

**部署完成，可以开始在 OpenClaw 中使用！**
