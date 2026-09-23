# 每日精选：基于 upstream 的小幅扩展

基线为 TideDra/zotero-arxiv-daily `2879bcd`，保留原仓库历史与许可证。
继续复用 Zotero 客户端、收藏夹过滤、arXiv RSS/API 检索与 Paper 数据结构、
TLDR/单位提取、HTML 邮件、SMTP 和每日 GitHub Actions。
未引入推荐历史数据库、embedding 模型、向量服务或额外界面。

## 启用与部署

当前 `config/custom.yaml` 已启用精选模式。部署时 fork 本仓库或把改动推送至自己的 fork，
按 upstream README 设置 Zotero 和 SMTP secrets，再将 **整个 `config/custom.yaml`**
复制到 Actions variable `CUSTOM_CONFIG`。原 workflow 会用该变量覆盖文件，
因此已有部署仅更新代码而不更新这个变量，不会自动启用精选。

核心配置（合并到现有 CUSTOM_CONFIG，不要移除 Zotero 和 email 配置）：

```yaml
executor:
  source: [arxiv]
  reranker: bm25
  max_paper_num: 3
recommendation:
  enabled: true
llm:
  enabled: false
source:
  arxiv:
    category: [cs.AI, cs.CV, cs.LG, cs.CL]
    fetch_full_text: false
```

必要 secrets 仍为 `ZOTERO_ID`、`ZOTERO_KEY`、`SENDER`、`SENDER_PASSWORD`、`RECEIVER`。
可选新增 `SEMANTIC_SCHOLAR_API_KEY` 和 `OPENALEX_API_KEY`，两个现有推送 workflow 已透传。
公开接口可能限流；免费 key 可提高可用性，代码不会使用付费服务或自动购买额度。
如服务返回鉴权错误或配额不足，该来源跳过，其他来源继续。

默认关闭 LLM，因此不需要 OpenAI key。希望继续使用原 TLDR 时设置 `llm.enabled: true`，
沿用 upstream 的 `llm.api`、`generation_kwargs` 配置与 secrets。
不下载全文时 LLM 仍可根据 abstract 生成 TLDR；单位信息可能缺失。
本地启动命令仍为 `uv run src/zotero_arxiv_daily/main.py`，测试为 `uv run pytest`。
为减少与 upstream 的依赖文件冲突，保留其依赖与锁文件（安装仍包含 upstream 的模型库，
但精选运行不会导入模型、下载权重或调用 embedding）。

## 详细读书笔记与新版邮件

已增加自动读书笔记：先推荐并选出论文，再尝试获取全文和调用现有 LLM 接口，
不需要点击邮件触发，也不影响 BM25 排序。开启方式（合并进 CUSTOM_CONFIG）：

```yaml
llm:
  enabled: true
  language: Chinese
  reading_notes:
    enabled: true
    language: Chinese
    chunk_tokens: 8000
    max_chunks: 6
    max_output_tokens: 3500
    extraction_timeout: 90
email:
  notes_collapsible: false
source:
  arxiv:
    fetch_full_text: false
```

仍需配置 `OPENAI_API_KEY`、`OPENAI_API_BASE` 和现有 `llm.generation_kwargs.model`。
模型需支持约 16K 或更大的上下文（或者调低分块/输出预算）。本地示例保留
`llm.enabled: false`，避免未配置 API 时阻断推荐；只打开 reading_notes 开关不会调用 LLM。
LLM 费用依服务商计费，不属于此前免费数据源额度。

只有最终入选论文会触发笔记全文下载；保持 `source.arxiv.fetch_full_text: false`，
避免在候选阶段下载全部论文。arXiv 依次尝试 HTML、PDF、LaTeX，其他来源使用
开放 PDF 或 arXiv ID，复用 upstream 的提取函数与子进程超时工具。
不绕过付费墙。提取失败降级为摘要解读；无内容时不生成笔记。

笔记固定包含研究背景、核心贡献、方法、实验与证据、局限性五部分，
不包含个人研究联系或借鉴建议。长文分块提取证据再汇总，最多读取 6 个片段；
更长时均匀抽样覆盖首尾并在邮件标明“仅分析 x/y 个片段”，不宣称完整阅读。
图片、复杂公式可能未完整提取，也会标注。普通短文只调用一次笔记 API，
长文最多 6 次片段提取 + 1 次汇总，另保留上游 TLDR/单位提取调用。
JSON 格式错误、调用失败等只影响该篇笔记，不阻止已有摘要和邮件发送。

邮件仍是 `text/html`，使用表格、内联样式、标题和段落，正文中的模型输出一律转义，
不用 JavaScript。`notes_collapsible: false` 是兼容优先的展开排版；设为 `true`
使用原生 `<details>/<summary>`，支持的客户端可点击展开，不支持时可能直接展开
或过滤标签，不能保证所有邮箱都具有交互效果。没有用 `display:none` 隐藏正文。
浏览器预览不代表 Gmail、QQ 邮箱、Outlook 等所有客户端均已实测。

离线预览：[展开版](email-preview.html) / [折叠版](email-preview-collapsible.html)。
预览内容明确标为排版示例，不是真实 LLM 生成结果。

实现位于 `reading_notes.py`，接口调用复用 `protocol._request_llm`；
展示位于现有 `construct_email.py`，SMTP 和定时 Actions 无须新增服务。
本次扩展后回归为 **128 passed, 1 deselected**，另检查了浏览器中 HTML 邮件排版。
未配置真实 LLM key，因此实际模型笔记质量与真实邮箱客户端渲染尚未联调。

## 排序与名额

- 读取完整 Zotero Library，包括无摘要条目，用于去重；`include_path` / `ignore_path`
  只控制兴趣语料。兴趣从最近 100 篇的 title、abstract、tags、collection path 提取。
- 时间权重为 `2 ** (-入库天数 / 60)`；title、tags 获得额外词频权重。
  用 TF-IDF 生成最多 80 个加权查询词，候选用 BM25 长度归一化与词频饱和打分。
  去除英文停用词；不采用字符串包含匹配。适合主要为英文的论文元数据，未实现中文分词。
- 默认至少命中 3 个兴趣词且 normalized BM25 >= 0.06 才进入相关论文池。
  这是保守的启发式阈值，不是论文质量概率；可通过 `min_relevance` 调整。
- arXiv 继续使用 upstream 新论文 RSS，不额外抓取历史；Semantic Scholar 从最近语料中
  选最多 5 个具有 DOI/arXiv/S2 ID 且标题主题不过度重复的 seeds，批量解析 ID 后调用 Recommendations。
  无标识符的条目仍用于兴趣，不进行易误匹配的标题搜索。
- S2 内部以服务端 relevance 排名为主，BM25 和封顶引用数仅轻量调整。
  arXiv 与 S2 分别排序后按倒数排名合并，避免比较不同来源的分数尺度。
  不限定 S2 发表年份，因此可发现经典工作。
- 优先选 2 篇相关论文；满足条件时再取 1 篇 Explore。没有合格 Explore 时可选第 3 篇相关论文。
  只有 1 篇相关时只发 1 篇，没有相关时不发；不为达到 2–3 篇而降低门槛。
- 探索候选需低于 `explore_max_relevance: 0.15`，减少与当前主题高度重复的热门论文。
  日期奇偶轮换优先来源，优先来源没有合格论文则使用另一个来源。

## 热门来源

Hugging Face 使用官方 `sort=trending`，支持 `period: daily / weekly / monthly`，
默认 weekly，取前 20 篇，至少 5 upvotes，保留其热度排序。

OpenAlex 每次查询一个领域，轮换 Computer Science (17)、Physics (31)、
Biochemistry/Genetics/Molecular Biology (13)、Medicine (27)、Engineering (22)。
默认最近 180 天、至少 5 次引用、排除撤稿，按 citation count 获取前 20 条，
再按 `log(1 + citations) / sqrt(max(30, age_days))` 轻量调整。
这只是近期引用表现代理，不代表实时引用增长率，也不用于跨领域直接比较引用数。
领域轮换依据 UTC 日期、无需历史状态；同一领域内不继续做分页采集。

## 去重与容错

使用规范化 DOI、去版本 arXiv ID、S2 ID、Unicode/大小写/标点归一化标题建立别名集合，
同时检查完整 Zotero 与当日所有候选，包含跨来源传递别名。
没有推荐历史意味着：没有加入 Zotero 的论文以后仍可能再推荐，这是有意保留的行为。

外部请求连接/读取超时分别为 10/30 秒、最多 3 次尝试，429/5xx 有限退避，
不无限分页或重试。单来源失败、单条记录格式错误都不会阻断其他来源。
不会在错误日志中输出 API key 或包含 key 的请求 URL。
没有摘要或 PDF 的论文仍可显示标题与落地页，邮件不会产生 `href="None"`。
摘要或 LLM 失败沿用上游回退行为，推荐原因随论文显示。

## 模块边界与 upstream 更新

```
discovery/common.py             共享 HTTP、重试、日期与记录转换
discovery/semantic_scholar.py   Zotero seeds → Recommendations API
discovery/huggingface.py        Daily Papers trending
discovery/openalex.py           跨学科引用表现
discovery/__init__.py           调用适配器与来源故障隔离
recommendation.py              兴趣提取、BM25、身份去重、名额选择
reranker/bm25.py               接入现有 reranker 注册接口
```

每个外部适配器统一暴露 `retrieve(profile, config) -> list[Paper]`，只依赖自身配置与
共享 HTTP 工具；新增来源只需增加一个模块并在 dispatcher 注册。
可分别设置 `recommendation.<source>.enabled: false` 关闭来源。

`config/base.yaml` 的精选开关默认关闭，已有 local/api reranker 仍然可用；
切回 upstream 模式时同时设置 `recommendation.enabled: false` 与原 `executor.reranker`。
更新 upstream 时重点审查 Executor 接入点、Paper 的可选字段、邮件标签及 workflow secrets，
不需要替换其 arXiv 检索实现。仓库未自动发布或向真实邮箱发送测试邮件。

## 本次验证

2026-09-23：Python 3.13、运行依赖对齐 upstream `uv.lock`，非慢速测试
**122 passed, 1 deselected**。覆盖近期权重、相关性阈值、seed 多样性、四类身份去重、
传递别名、完整 Library 去重、无 LLM 的端到端邮件流程、名额不足不凑数、
三种外部 API 记录转换、429/超时/鉴权失败与来源隔离。
被排除的是 upstream 本地 embedding 模型下载测试。

另用公开论文完成 Semantic Scholar batch + Recommendations 的只读请求，
并验证 Hugging Face `sort=trending` 与 OpenAlex 领域/日期/引用数筛选实际可响应。
这验证接口连通与格式，不代表已验证私人 Library 的推荐效果；首次运行后可根据
实际结果调整相关性阈值。

接口参考：

- [Semantic Scholar 官方教程](https://www.semanticscholar.org/product/api/tutorial)
- [Hugging Face list_daily_papers](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api#huggingface_hub.HfApi.list_daily_papers)
- [OpenAlex API](https://help.openalex.org/api/)
- [OpenAlex 领域筛选示例](https://help.openalex.org/tutorials/funder-portfolios/)
