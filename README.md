# 刷屏检测

检测消息刷屏和网页链接，支持全体禁言/解禁。

---

## 快速开始

1. 在插件配置 `enabled_groups` 中填入要检测的群号（不填则不生效）
2. 在 `admins` 中填入管理员的 QQ 号
3. 重启 AstrBot 即可

---

## 检测规则

### 刷屏检测
- 用户在 `spam_window` 秒内累计发送 ≥ `spam_trigger` 条消息
- 触发后撤回该消息 + 禁言 `spam_mute_seconds` 秒
- 默认：1 秒内 ≥5 条 → 禁言 1 分钟
- 仅对 `enabled_groups` 中的群生效
- 白名单用户不受检测

### 网页链接检测
- 检测到消息中含 `http://` 或 `https://` 链接
- 触发后撤回该消息 + 禁言 `url_mute_seconds` 秒
- 默认：禁言 2 分钟
- 优先级高于刷屏检测（先检测链接，再检测刷屏）
- 仅对 `enabled_groups` 中的群生效

---

## 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled_groups` | list | `[]` | 启用检测的群号列表，填群号才生效 |
| `admins` | list | `[]` | 管理员QQ号列表 |
| `spam_trigger` | int | `5` | 刷屏触发阈值（1秒内发多少条/个表情算刷屏） |
| `spam_window` | int | `1` | 刷屏检测时间窗口（秒） |
| `spam_mute_seconds` | int | `60` | 刷屏禁言时长（秒） |
| `url_mute_seconds` | int | `120` | 网页链接禁言时长（秒） |
| `private_notify` | bool | `true` | 是否私聊提醒违规用户 |
| `funny_mute` | bool | `true` | 启用趣味禁言文案 |
| `funny_mute_words` | list | 3条默认文案 | 趣味文案列表，可用 `{name}` 占位 |
| `whitelist` | list | `[]` | 白名单QQ号（通过命令管理） |

---

## 命令

| 命令 | 说明 | 权限 |
|------|------|------|
| `防刷屏状态` | 查看当前群检测配置 | 任何人 |
| `全员解禁` | 关闭全员禁言 | 任何人 |
| `全体禁言` | 开启全员禁言，仅群主和管理员可发言 | 管理员 |
| `加白 <QQ号>` | 将用户加入白名单 | 管理员 |
| `移白 <QQ号>` | 将用户移出白名单 | 管理员 |
| `白名单` | 查看白名单列表 | 管理员 |
| `刷屏日报` | 查看今日刷屏统计（图片） | 任何人 |
| `刷屏周报` | 查看本周刷屏统计（图片） | 任何人 |

---

## 工作原理

```
群消息到达
  ├─ 群不在 enabled_groups 中？→ 跳过
  ├─ 白名单用户？→ 跳过
  ├─ 含 http/https 链接？→ 撤回 + 禁言
  └─ spam_window 秒内 ≥ spam_trigger 条？→ 撤回 + 禁言
```

刷屏检测使用 `deque` 时间戳队列，每条消息记录一个时间戳，新消息到达时统计窗口内的数量。触发后清空队列，防止重复处罚。

---

## 目录结构

```
astrbot_plugin_anti_spam_simple/
├── metadata.yaml
├── main.py
├── _conf_schema.json
├── README.md
├── _data/
│   └── violations.json    # 违规记录（自动生成）
└── _reports/
    └── report_*.png        # 日报图片（自动生成）
```

---

## 许可

MIT

*由 **若曦** 编写*
