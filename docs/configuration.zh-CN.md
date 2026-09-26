# 配置参考

所有业务参数都可通过 GitHub Actions repository variable `CUSTOM_CONFIG` 修改，无需编辑 Python。
配置层级为：`config/base.yaml` 默认值 → `config/custom.yaml` 用户覆盖；Actions 中非空的
`CUSTOM_CONFIG` 替换 `custom.yaml`。凭据始终放 Secrets，通过 `${oc.env:NAME}` 引用。
完整可复制配置见 [github.example.yaml](../config/github.example.yaml)。

## 数量、分配与回退

| 参数 | 基础默认值 | 含义 |
| --- | --- | --- |
| `executor.max_paper_num` | 100；精选示例为 3 | 每日总上限，精选不再强制最多 3 篇 |
| `recommendation.interest_slots` | 2 | 第一阶段选取的相关论文名额，arXiv/S2 共同竞争 |
| `recommendation.explore_slots` | 1 | 探索池名额上限 |
| `recommendation.min_interest_for_explore` | 2 | 相关论文达到此数量后才启用探索位；可设 0 |
| `recommendation.fill_with_interest` | true | 探索不足或分配后有空位时，合格相关论文能否补足总上限 |
| `recommendation.source_limits` | `{}` | 每个来源的最终上限，未指定则仅受总上限约束 |
| `recommendation.source_weights` | `{}` | 相关来源倒数排名权重，未指定为 1；0 不选择该相关来源 |
| `recommendation.explore_sources` | `[huggingface, openalex]` | 归类为探索来源的列表，按日期轮换优先来源 |
| `executor.send_empty` | false | 无合格结果时是否仍发空邮件 |

所有名额必须为非负整数。先通过质量门槛和全局去重，再选相关、选探索、可选补位。
总上限、来源上限始终生效；不会因为名额不足降低相关性或热度门槛。
`source_weights` 只影响相关池排序；探索池使用服务端热度/引用评分。

常见配法（仍需合并到完整配置）：

```yaml
# 相关 2 + 探索 1；不足时可用第 3 篇相关论文补位
executor:
  max_paper_num: 3
recommendation:
  interest_slots: 2
  explore_slots: 1
  min_interest_for_explore: 2
  fill_with_interest: true
```

```yaml
# 相关最多 4 + 探索最多 2，不跨类型补位
executor:
  max_paper_num: 6
recommendation:
  interest_slots: 4
  explore_slots: 2
  min_interest_for_explore: 1
  fill_with_interest: false
  source_limits:
    arxiv: 3
    semantic_scholar: 2
```

只看相关论文：`explore_slots: 0`。只看探索：`interest_slots: 0`、
`min_interest_for_explore: 0`、`fill_with_interest: false`。关闭某个来源的网络请求，
应使用该来源的 `enabled: false`；只设名额为 0 不会阻止请求。

## 主题与兴趣

相关性引擎由 `executor.reranker` 选择：`bm25`（无模型）、`local`（upstream 本地 embedding）、
`api`（upstream embedding API）。这三种均可与 `recommendation.enabled: true` 的精选流程配合。
本地 embedding 需要 Actions Variable `INSTALL_EMBEDDINGS=true`，或本地命令加 `--extra embeddings`。

- `recommendation.embedding_sources: [arxiv]`：默认仅替换 arXiv 候选打分。
- `recommendation.embedding_min_relevance: 3.0`：独立阈值，分数为 upstream 近期入库加权余弦相似度 × 10；不是概率，不与 BM25 门槛混用。
- `reranker.local.model` / `encode_kwargs`：沿用 upstream 的模型与编码参数。

embedding 使用 Zotero 摘要和原始近期入库排名衰减公式，不对候选再做 BM25 必须命中的限制。
没有摘要的 Zotero 条目仍参与全库去重，但不参与 embedding 语料。
Semantic Scholar、Hugging Face、OpenAlex 不会改用本地模型召回，仍按原有接口和精选策略处理。

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `recommendation.recent_limit` | 100 | 最近多少篇 Zotero 文献参与兴趣提取 |
| `recommendation.half_life_days` | 60 | 入库时间权重半衰期 |
| `recommendation.query_terms` | 80 | TF-IDF 兴趣词数量上限 |
| `recommendation.min_matched_terms` | 3 | BM25 候选最少命中词项 |
| `recommendation.min_relevance` | 0.06 | 相关论文归一化 BM25 门槛，不是概率 |
| `recommendation.explore_max_relevance` | 0.15 | 避免探索与当前兴趣过度重复；设 1 可取消该限制 |
| `recommendation.explore_include_topics` | `[]` | 想看的探索主题，自由文本描述列表 |
| `recommendation.explore_exclude_topics` | `[]` | 不想看的主题，自由文本描述列表 |
| `recommendation.explore_focus_min_score` | 0.05 | 包含主题最小 TF-IDF 相似度 |
| `recommendation.explore_exclude_min_score` | 0.05 | 排除主题触发阈值 |

包含列表为空则不要求主题命中。排除主题相似度超过门槛，且不低于最匹配包含主题时，
拒绝该候选；仅设排除列表时直接按排除门槛判断。描述使用英文最匹配论文元数据。
这里没有固定的 NLP、CV 或生物枚举；更换列表即可迁移学科。

```yaml
recommendation:
  explore_include_topics:
    - natural language processing language models LLM reasoning RAG question answering
    - language agents agentic tool use tool calling coding agents
  explore_exclude_topics:
    - computer vision image video generation 3D camera reconstruction robotics
```

`zotero.include_path` / `ignore_path` 只筛选兴趣语料，不影响完整 Library 去重。
`source.arxiv.category` 控制 arXiv 订阅分类；`include_cross_list: false` 排除 cross-list 公告。
`rss_fallback: true` 在 arXiv 元数据 API 报错时继续使用已取得的 RSS 数据；可关闭。
`api_retries` 与 `batch_retries` 控制两层有限重试，默认均为 2。

## 外部来源

| 配置块 | 常用参数 |
| --- | --- |
| `recommendation.semantic_scholar` | `enabled`、`api_key`、`seed_limit`（5）、`limit`（30） |
| `recommendation.huggingface` | `enabled`、`period`（daily/weekly/monthly）、`limit`（20）、`min_upvotes`（5） |
| `recommendation.openalex` | `enabled`、`api_key`、`fields`、`lookback_days`（180）、`min_citations`（5）、`limit`（20） |

OpenAlex field ID：17 计算机，31 物理，13 生物化学/遗传/分子生物，27 医学，22 工程。
当前示例仅 `[17]`，开源基础配置仍保留跨学科轮换列表，可自行选择。

## LLM 与读书笔记

| 配置 | 含义 |
| --- | --- |
| `llm.enabled: false` | 完全不调用 LLM；使用原摘要 |
| `llm.enabled: true` + `reading_notes.enabled: false` | 生成 TLDR，保留原有单位提取，不生成详细笔记 |
| 两者都 true | 自动读取入选论文并生成五部分笔记，再生成 TLDR |
| `llm.api.key` / `base_url` | 凭据引用与兼容接口地址 |
| `llm.api_mode` | `chat_completion` 或 `response` |
| `llm.generation_kwargs.model` | 服务商实际支持的模型 ID |
| `llm.language` | TLDR 语言；中文填 `Chinese` |
| `llm.reading_notes.language` | 笔记语言；中文填 `Chinese` |
| `llm.reading_notes.chunk_tokens` | 每块输入预算，默认 8000，最小 500 |
| `llm.reading_notes.max_chunks` | 最多处理块数，默认 6，允许 1–12 |
| `llm.reading_notes.max_output_tokens` | 最终笔记输出预算，默认 3500 |
| `llm.reading_notes.extraction_timeout` | 每种全文提取方式超时秒数，默认 90 |

超过最大块数时均匀取样并标注覆盖范围，非静默只取开头。图片/复杂公式可能缺失。
设置 `source.arxiv.fetch_full_text: false` 可避免候选阶段下载全文，笔记阶段仍会下载
最终入选论文；关闭 LLM 时，推荐无需任何模型或全文。

## 超时和重试

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `source.arxiv.api_retries` | 2 | arXiv 客户端额外重试次数 |
| `source.arxiv.batch_retries` | 2 | 批次遭遇 429 时最大尝试次数，之后可降级到 RSS |
| `source.arxiv.rss_fallback` | true | API 失败后保留 RSS 候选 |
| `source.arxiv.conversion_delay` | 1；示例为 0 | 候选转换间隔秒数；纯元数据转换无需等待 |
| `recommendation.http.attempts` | 3 | 外部发现 API 总尝试次数，允许 1–10 |
| `recommendation.http.read_timeout` | 30 | 单次请求读取超时秒数；连接超时 10 秒 |
| `recommendation.http.max_retry_delay` | 30 | 指数退避或 Retry-After 等待秒数上限 |
| `llm.api.timeout` | 90 | LLM 单次请求超时秒数 |
| `llm.api.max_retries` | 2 | SDK 针对临时网络/限流/服务端错误的额外重试 |
| `llm.reading_notes.format_attempts` | 2 | 最终笔记 JSON 格式或字段不完整时的最大生成尝试，允许 1–5 |

发现 API 对 408、429、5xx 和网络错误有限重试；401/403/404 等直接停止该来源。
各来源可用自身的 `http` 配置覆盖公共值，例如 `recommendation.openalex.http.attempts: 2`。
笔记格式重试不重复下载全文；模型不存在、鉴权失败等不会被格式重试吞掉。
没有自动重试整个工作流或 SMTP sendmail，以免重复发送邮件。

## 邮件、定时与缓存

| 配置 | 默认值 / 示例 |
| --- | --- |
| `email.sender_name` | `Daily Paper`，发件人显示名 |
| `email.subject_prefix` | `Daily Paper`，主题前缀；随后追加日期 |
| `email.max_width` | 1120 像素；可调，最小 320，窄屏流式收缩 |
| `email.notes_collapsible` | 基础默认 false，示例 true |
| `email.smtp_server` / `smtp_port` | 示例 QQ 为 `smtp.qq.com:465` |

手机窄屏通过媒体查询缩小边距；客户端忽略样式时仍保留百分比宽度。
定时在 `.github/workflows/main.yml` 的 cron 中配置；GitHub cron 不支持从 Variable
动态插入。当前 `11 3 * * *` 即北京时间每天 11:11，可能有平台调度延迟。

Actions Variables 除 `CUSTOM_CONFIG` 外：

- `INSTALL_EMBEDDINGS=true`：安装可选 embedding 依赖并启用 Hugging Face 权重缓存；不自动切换排序器。
- `EMBEDDING_CACHE_VERSION`：可填 `v1`，更换模型后改成新值来刷新权重缓存。
- `REPOSITORY` / `REF`：继承 upstream 的高级 checkout 选项，通常留空。

uv 依赖缓存按 `uv.lock` 更新；Hugging Face 缓存只保存模型下载目录，不保存 Token、
Zotero Library、论文笔记或 API Key。缓存可被 GitHub 淘汰，不保证每次命中；缓存模型
不代表持久运行模型，每次新 runner 仍需加载模型并计算。
