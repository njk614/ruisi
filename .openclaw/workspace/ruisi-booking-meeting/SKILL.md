---
name: ruisi-booking-meeting
description: 处理会议预约、会议室查询、预定创建和内部提醒。使用本 Skill 完成可预约时段查询、冲突检查、写入 meetings.json、生成 booking_info.json，并为我方参会人员记录提醒。
version: 2.1.0
author: 智能接待系统团队
level: L1
allowed-tools:
  - read_file
  - write_file
  - bash
metadata:
  openclaw:
    emoji: '📅'
    requires:
      bins:
        - python3
dependencies:
  - command: 'python3'
    min_version: '3.9'
---

# 会议预定

## 触发

用户表达预约会议、预定会议室、查询可用会议时段、创建会议预定或发送会议提醒时触发。

## 核心约束

- 单 Skill 执行，不调用 SubAgent，也不依赖其他 Skill。
- 数据查询和写入必须通过 `scripts/` 下脚本完成，不得手工改写 `meetings.json`。
- 创建预定前必须收集并确认：会议时间和会议室、预定人、我方参会人员、客户方参会人员、会议主题。
- 每次向用户询问后必须停止当前轮次，等待用户回复；不得猜测缺失信息。
- 用户输入 `cancel` 时终止流程，返回 `failed` 并说明用户取消。

## 数据路径

- 会议室清单：默认 `/home/clawd/.openclaw/workspace/SimulatedData/meeting_rooms.json`，可用 `OPENCLAW_DATA_ROOT` 覆盖目录。
- 预定记录：默认 `/home/clawd/.openclaw/workspace/SimulatedData/meetings.json`。
- 预定记录覆盖优先级：`OPENCLAW_MEETINGS_PATH` > `OPENCLAW_BOOKINGS_PATH` > 默认路径；`OPENCLAW_BOOKINGS_PATH` 仅兼容旧配置。

## 脚本

| 脚本                               | 用途                                                                |
| ---------------------------------- | ------------------------------------------------------------------- |
| `scripts/select_meeting_slot.py`   | 生成会议室可预约时段，输出 `artifacts/available_slots.json`         |
| `scripts/query_free_rooms.py`      | 按最终时间范围查询空闲会议室，输出 `artifacts/available_rooms.json` |
| `scripts/create_booking.py`        | 检查冲突、写入 `meetings.json`、输出 `output/booking_info.json`     |
| `scripts/send_internal_message.py` | 为我方参会人员记录内部提醒消息                                      |

## 执行流程

1. 生成 `execution_id`；若无 `business_task`，使用 `auto_<uuid>`。
2. 创建执行目录：
   `<workspace>/trace-workspace/<business_task>/<YYYYMMDD_HHMMSS>_<execution_id前8位>/`
   并创建 `input/`、`artifacts/`、`output/`。
3. 保存用户原始输入到 `input/initial_params.json`，记录 `execution.log`。
4. 若用户还未选择候选时段，运行：
   ```bash
   python3 scripts/select_meeting_slot.py --output-path <execution_dir_path>/artifacts/available_slots.json
   ```
   可按需增加 `--date-from YYYY-MM-DD`、`--days 3`、`--preferred-room-name 大会议室`。
5. 向用户原样展示 `available_slots.json` 的 `display_text`。该文本已按会议室分组展示 `options[]` 编号，并在末尾提示“请回复**编号**，选择其他日期请直接回复“0””。用户选择编号后，记录 `available_slot`、`room_id`、`room_name`。
6. 若用户回复 `0`，视为选择其他日期，询问日期并等待回复；下一轮归一化为 `YYYY-MM-DD` 后重新运行 `select_meeting_slot.py --date-from <日期> --days 3`。
7. 询问具体会议时间段；必须包含开始和结束时间，并完全落在所选 `available_slot.slot` 内。
8. 若用户已提供完整时间范围但未确定会议室，运行：
   ```bash
   python3 scripts/query_free_rooms.py --time-range "<slot>" --output-path <execution_dir_path>/artifacts/available_rooms.json
   ```
   多个会议室可用时，让用户选择一个。
9. 依次补齐 `booker_name`、`internal_attendees`、`customer_attendees`、`meeting_topic`；一次只问一个缺失字段。
10. 创建前向用户确认时间、会议室、预定人、我方参会人员、客户方参会人员和会议主题；只有回复 `Y` 才继续。
11. 用户确认后运行：
    ```bash
    python3 scripts/create_booking.py --room-id "<room_id>" --slot "<slot>" --booker-name "<booker_name>" --internal-attendees "<names>" --customer-attendees "<names-or-无>" --meeting-topic "<meeting_topic>" --output-path <execution_dir_path>/output/booking_info.json
    ```
    若只有会议室名称，可用 `--room-name "<room_name>"` 代替 `--room-id`。
12. 读取 `output/booking_info.json`，对 `internal_attendees` 中每个人运行 `send_internal_message.py`，输出 `artifacts/message_<index>.json`。
13. 汇总提醒结果到 `artifacts/reminder_result.json`，生成 `manifest.json`，返回 `status`、`message`、`booking_id`、`output_files`。

## 字段规则

- `slot` 标准格式为 `YYYY-MM-DD HH:MM~HH:MM`；自然语言时间必须先归一化。只给单个时间点时，必须追问结束时间。
- `internal_attendees` 至少 1 人；`customer_attendees` 可为姓名列表，若无客户方人员必须明确输入 `无`。
- 参会人员支持英文逗号、中文逗号、顿号、分号分隔。
- `internal_staff` 自动等于 `internal_attendees` 数量；`visitor_count` 自动等于 `customer_attendees` 数量。
- `zone` 优先取会议室数据中的字段；否则小会议室为 `meeting-room-small`，大会议室为 `meeting-room-large`。
- `booking_id` 格式为 `M<会议日期YYYYMMDD>_<三位流水号>`，例如 `M20260605_001`；流水号按同一会议日期已有记录最大值递增。
- `created_time` 使用本地时间格式 `YYYY-MM-DD HH:MM:SS`。
- `output/booking_info.json` 必须包含：
  `booking_id`、`room_id`、`room_name`、`zone`、`time_range`、`booker_name`、`internal_staff`、`visitor_count`、`meeting_topic`、`internal_attendees`、`customer_attendees`、`created_time`。

## 异常处理

| 场景                 | 处理                                       |
| -------------------- | ------------------------------------------ |
| 无可预约时段         | 提示选择其他日期请回复 `0`，让用户重新选择 |
| 具体时间超出候选时段 | 说明可选范围并重新询问                     |
| 指定时间无空闲会议室 | 让用户重新选择时间或会议室                 |
| 缺少必填字段         | 一次只询问一个字段                         |
| 创建脚本返回冲突     | 提示重新选择时间或会议室                   |
| 提醒部分失败         | 保留预定结果，返回 `partial`               |

## 输出与留痕

- 成功时返回 `success`、说明信息、`booking_id`、`output_files`。
- 创建失败或用户取消时返回 `failed`。
- 提醒部分失败但预定成功时返回 `partial`。
- 执行目录应包含 `manifest.json`、`execution.log`、`input/initial_params.json`、`artifacts/`、`output/booking_info.json`。

## 安全

- 只能写入执行目录、`/home/clawd/.openclaw/workspace/SimulatedData/meetings.json`、`OPENCLAW_MEETINGS_PATH` 指向文件，或旧兼容变量 `OPENCLAW_BOOKINGS_PATH` 指向文件。
- 不调用真实外部消息平台；提醒发送只记录本地 JSON。
- 不访问或修改非会议预定相关路径。
