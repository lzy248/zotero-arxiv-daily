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

未启用主线时，embedding 使用 Zotero 摘要和原始近期入库排名衰减公式，不对候选再做 BM25 必须命中的限制。
此时没有摘要的 Zotero 条目仍参与全库去重，但不参与 embedding 语料。
启用主线后的标题回退与双池计分见下一节。
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
arXiv 现沿用 upstream 的 RSS 直接读取元数据，不再请求曾返回 HTTP 406 的旧元数据 API。
`rss_attempts`（默认 5）与 `rss_retry_delay`（默认 5 秒）控制 RSS 重试。
旧 `api_retries`、`batch_retries`、`rss_fallback` 已不再使用，可从自定义配置中移除。

## 固定研究主线与全局主题过滤

主线功能需要 `recommendation.enabled: true`，同时兼容 `bm25`、`local`、`api`。无需额外 Zotero 账号或数据库，在当前 Library 内建立一个专用集合即可。配置举例：

```yaml
recommendation:
  enabled: true
  mainline:
    enabled: true
    include_path: ["研究主线", "研究主线/**"]
    weight: 0.6
    strict: false
    min_relevance: 0.06
    embedding_min_relevance: 3.0
  topic_filter:
    include_topics: []
    exclude_topics: []
    min_score: 0.05
    exclude_min_score: 0.05
```

| 参数 | 基础默认值 | 含义 |
| --- | --- | --- |
| `recommendation.mainline.enabled` | false | 是否使用固定主线集合；本地 custom.yaml 已开启 |
| `mainline.include_path` | `[]` | 当前 Zotero 库中的集合完整路径 glob 列表；启用时必填 |
| `mainline.weight` | 0.6 | 主线独立计分预算，范围 `(0, 1]`；近期池使用余下权重 |
| `mainline.strict` | false | false：主线参与加权但不强制命中；true：所有来源，包括探索，必须达到主线门槛；本地配置为 false |
| `mainline.min_relevance` | 0.06 | 非 embedding 来源匹配主线的归一化 BM25 门槛 |
| `mainline.embedding_min_relevance` | 3.0 | embedding 来源匹配主线的余弦相似度 × 10 门槛 |
| `recommendation.topic_filter.include_topics` | `[]` | 所有来源必须匹配其中至少一个文本主题；空列表不限制 |
| `topic_filter.exclude_topics` | `[]` | 所有来源的排除主题；按相似度与包含主题比较 |
| `topic_filter.min_score` | 0.05 | 全局包含主题的 TF-IDF 门槛 |
| `topic_filter.exclude_min_score` | 0.05 | 全局排除主题的 TF-IDF 门槛 |

表中 `mainline.*` / `topic_filter.*` 均位于 `recommendation` 下。现有 `explore_include_topics` / `explore_exclude_topics` 继续只控制探索来源；全局主题过滤、主线门槛与原有质量门槛同时生效。即使 embedding 主线通过，全局文本主题过滤仍可拒绝候选；不需要词面限制时保持 `topic_filter` 两个列表为空。

### 固定语料如何避免漂移

- 主线独立从完整 Library 读取，不受 `zotero.include_path` / `ignore_path` 约束。这两个旧参数仍只选择近期兴趣语料；如果不希望某论文影响主线，应从主线集合移除或缩小 `mainline.include_path`。
- `研究主线` 匹配集合自身，`研究主线/**` 匹配其子集合；嵌套集合应写完整路径，例如 `科研/研究主线` 和 `科研/研究主线/**`。
- 全部主线文献每天参与匹配，不使用 `recent_limit` 或时间衰减。BM25 为每篇主线论文建立独立的永久查询，再取最高匹配值，避免少量关键论文被其他文献挤掉。`query_terms` 仍限制每篇参考论文的词项数量。
- 与主线重复的文献先从近期池去除，避免同一论文重复计权；近期池继续使用最近窗口与其原有时间/排名权重。
- embedding 主线使用标题与摘要，空摘要时使用标题；取候选与任意主线文献的最高余弦相似度 × 10。主线和近期池一次性批量计算，不为每篇参考文献重复初始化模型。
- 有近期池时：`final = weight × mainline + (1 - weight) × recent`；近期池为空时：`final = mainline`。
- `strict: true` 先要求主线分数过阈值，再执行原有最终相关性、热度、名额和去重规则。因此主线匹配不保证一定入选；严格模式可能一天没有结果。
- Semantic Scholar 的严格模式只用主线种子；软模式按主线权重预留种子名额，其余给近期兴趣。可用主线种子按日期轮换，不依赖入库日期；不受轮换影响的全部主线语料仍用于本地筛选。无 DOI/arXiv/S2 ID 的文献不能作该服务的种子，但仍可作本地主线参考。
- 启用后集合为空、路径无匹配或参数非法时直接报错。不会为了出结果回退到普通近期推荐。关闭 `mainline.enabled` 恢复旧行为。

### 使用步骤和边界

在 Zotero 建立集合、加入自己的论文和强相关参考文献，并同步到云端。随后在本地配置或 GitHub Actions 的 `CUSTOM_CONFIG` 中开启主线。此功能只读取集合，不修改 Zotero，也不自动创建收藏夹。全库去重仍会排除所有已拥有论文，包括主线集合中的论文。

全局文本主题过滤采用与探索主题相同的 TF-IDF 一、二元词组算法：包含主题达到门槛才保留，排除主题达到门槛且不低于包含主题时拒绝。它不会调用 LLM，最适合英文主题描述。BM25 和 TF-IDF 是词项相关性筛选，可能漏掉同义表达或保留共享术语的偏题文章；embedding 也不是研究价值的保证。阈值代表筛选强度，不是概率。

这些规则只固定用于匹配的参考范围，不保存历史推荐、不训练模型。主线集合内容变化才会改变固定参考池；新的普通阅读条目不会替换它。

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
| `llm.reading_notes.mode` | 默认 `full`，全文直读；`auto` 仅超限时分段；`chunked` 强制分段 |
| `llm.reading_notes.stream` | 默认 true，流式接收长输出，完整接收并校验后才显示；不支持 SSE 的兼容服务可设 false |
| `llm.reading_notes.context_window_tokens` | 总上下文，默认 200000，包含输入和预留输出 |
| `llm.reading_notes.max_input_tokens` | 默认 null，不另设输入上限；仍受总上下文减去输出后的容量限制 |
| `llm.reading_notes.max_output_tokens` | 最大输出，默认 65536（64 Ki tokens），不是要求生成这么长 |
| `llm.reading_notes.section_target_chars` | 默认 null，不设每节目标字数；可按需设整数 |
| `llm.reading_notes.max_section_chars` | 默认 null，无每节字符上限；即使配置上限也只校验/重试，不静默截断 |
| `llm.reading_notes.include_visuals` | 默认 true，生成困难—设计表、实验依据表和方法流程图 |
| `llm.reading_notes.max_visual_rows` / `max_pipeline_steps` | 默认 null；可限制表格行数或流程步骤 |
| `llm.reading_notes.chunk_tokens` | 分段模式每块输入，默认 8000，最小 500；full 模式不使用 |
| `llm.reading_notes.max_chunks` | 分段模式最多块数，默认 6，允许 1–12 |
| `llm.reading_notes.extract_max_output_tokens` | 每块结构化证据输出上限，默认 3000；不用于全文直读 |
| `llm.reading_notes.raw_anchor_tokens` | 分段时额外保留的论文开头原文，默认 4000，防止丢失问题定义 |
| `llm.reading_notes.extraction_timeout` | 每种全文提取方式超时秒数，默认 90 |

默认全文模式没有分段摘要压缩。200000 总上下文预留 65536 输出及 512 tokens 消息开销后，
最多约 133952 tokens 可用于系统提示、标题、摘要和全文；实际分词可能与服务商略有差异。
调大这些值不会改变服务商的真实容量。若服务商拒绝限额，笔记会显示失败而非假装完整阅读。
只有在 auto/chunked 模式下，超过最大块数才会均匀取样并标注覆盖；原文表格保留，图片/复杂公式仍可能缺失。
每块证据必须提供在该片段中能找到的原文引用；证据提取失败会重试并标注，不能将某一片段未提及误判为整篇论文缺失。
最终笔记使用同一份证据，TLDR 从创新点和方法解释中提炼，而非独立强调性能数字。
流式接收依据 [OpenAI Docs](https://developers.openai.com/api/docs/guides/streaming-responses) 的事件格式实现；
只有收到正常结束标记且 JSON 校验通过才显示笔记，不能把中途断开的输出当作完整结果。
设置 `source.arxiv.fetch_full_text: false` 可避免候选阶段下载全文，笔记阶段仍会下载
最终入选论文；关闭 LLM 时，推荐无需任何模型或全文。

## 超时和重试

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `source.arxiv.rss_attempts` | 5 | RSS 获取的最大尝试次数 |
| `source.arxiv.rss_retry_delay` | 5 | RSS 重试之间的等待秒数 |
| `source.arxiv.conversion_delay` | 1；示例为 0 | 候选转换间隔秒数；纯元数据转换无需等待 |
| `recommendation.http.attempts` | 3 | 外部发现 API 总尝试次数，允许 1–10 |
| `recommendation.http.read_timeout` | 30 | 单次请求读取超时秒数；连接超时 10 秒 |
| `recommendation.http.max_retry_delay` | 30 | 指数退避或 Retry-After 等待秒数上限 |
| `llm.api.timeout` | 300 | LLM 单次请求超时秒数；全文与长输出通常需要更长等待 |
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
动态插入。当前 `0 23 * * *` 即北京时间次日 07:00，可能有平台调度延迟。

Actions Variables 除 `CUSTOM_CONFIG` 外：

- `INSTALL_EMBEDDINGS=true`：安装可选 embedding 依赖并启用 Hugging Face 权重缓存；不自动切换排序器。
- `EMBEDDING_CACHE_VERSION`：可填 `v1`，更换模型后改成新值来刷新权重缓存。
- `REPOSITORY` / `REF`：继承 upstream 的高级 checkout 选项，通常留空。

uv 依赖缓存按 `uv.lock` 更新；Hugging Face 缓存只保存模型下载目录，不保存 Token、
Zotero Library、论文笔记或 API Key。缓存可被 GitHub 淘汰，不保证每次命中；缓存模型
不代表持久运行模型，每次新 runner 仍需加载模型并计算。
