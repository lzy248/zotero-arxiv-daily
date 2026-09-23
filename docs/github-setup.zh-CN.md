# GitHub Actions 首次配置

仓库：https://github.com/lzy248/zotero-arxiv-daily

## 1. 准备 Secrets

进入 Settings → Secrets and variables → Actions → Secrets，逐个添加：

| 名称 | 内容 |
| --- | --- |
| `ZOTERO_ID` | Zotero 数字 User ID，不是用户名 |
| `ZOTERO_KEY` | 可读取个人 Library 的 Zotero API key |
| `SENDER` | 发件邮箱地址 |
| `SENDER_PASSWORD` | SMTP 授权码或应用密码，依邮箱服务商要求 |
| `RECEIVER` | 收件邮箱，可与发件邮箱相同 |
| `OPENAI_API_KEY` | 支持现有兼容接口的 LLM 服务商 key；生成详细笔记需要 |
| `OPENAI_API_BASE` | 服务商提供的 API base URL，通常包含 `/v1` |

可选添加 `SEMANTIC_SCHOLAR_API_KEY` 与 `OPENALEX_API_KEY`；不填时先尝试公开配额，
鉴权失败或限流时该来源会跳过。不要把真实 key 写进公开代码、Issues 或配置变量。
Zotero 的 ID 和 key 在 https://www.zotero.org/settings/keys 获取。

## 2. 设置 CUSTOM_CONFIG

在同一页面切换到 Variables，新增 repository variable `CUSTOM_CONFIG`。
把 [config/github.example.yaml](../config/github.example.yaml) 的完整内容复制进去，然后修改：

- `email.smtp_server` 与 `smtp_port`：示例为 QQ 邮箱 `smtp.qq.com:465`，其他邮箱按服务商设置。
- `llm.generation_kwargs.model`：将 `YOUR_MODEL_NAME` 替换为实际模型 ID。
- `source.arxiv.category`：当前关注 AI、机器学习、语言、视觉、检索、神经计算、多智能体、
  机器人，以及软件工程、数据库、算法、分布式系统、安全等计算机分类。
- `recommendation.openalex.fields`：当前仅 `[17]`（Computer Science），不轮换生物、医学、物理。
- `email.notes_collapsible`：当前为 `true`；若邮箱不支持折叠，可改为 `false` 使用展开排版。

示例启用中文 TLDR 与五部分读书笔记。Secrets 引用 `${oc.env:...}` 原样保留。
LLM 需有可用额度；若暂不准备 LLM，则设置 `llm.enabled: false`，仍可推荐并发送论文摘要。
无需配置 `REPOSITORY` 或 `REF`，保持为空即可使用当前仓库及分支。

## 3. 启用并验证

公开 fork 的 Actions 如显示启用提示，先在 Actions 页面启用 workflow。
配置完成后选择 **Send emails daily** → **Run workflow** 手动运行一次。
这是真实发送流程；没有合格论文且 `send_empty: false` 时不会发邮件。
查看任务日志确认数据获取、笔记生成和邮件发送是否成功。

定时任务为 UTC 每日 22:00，即北京时间次日 **06:00**；GitHub 调度可能延迟。
`Test` workflow 同样会真实发送邮件，只是开启 debug，并非离线测试。
`CI` 才是使用测试桩、不发真实邮件的自动测试。

详细笔记成本按 LLM 服务商计费；全文获取失败时标注“仅依据摘要”，模型失败时保留 TLDR。
具体预算、API 模块及限制见 [实现说明](curated-recommendations.zh-CN.md)。
