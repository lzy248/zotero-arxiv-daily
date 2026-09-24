# Daily Paper

每天，从你的 Zotero 最近研究兴趣出发，挑选值得读的论文，并把中文摘要和可选的详细读书笔记发到邮箱。

本项目基于 [TideDra/zotero-arxiv-daily](https://github.com/TideDra/zotero-arxiv-daily) 二次开发，复用 Zotero 读取、arXiv 检索、全文提取、LLM 接口、SMTP 和 GitHub Actions。保留 upstream 历史与 AGPL-3.0 许可证，不重新构建整套系统。

[首次部署](docs/github-setup.zh-CN.md) · [完整配置参考](docs/configuration.zh-CN.md) · [配置示例](config/github.example.yaml) · [邮件展开预览](docs/email-preview.html) · [折叠预览](docs/email-preview-collapsible.html)

## 推荐来源

| 类型 | 来源 | 用途 |
| --- | --- | --- |
| Recent Interest | arXiv | 新发布、与你最近收藏主题相关的论文 |
| Related / Catch-up | Semantic Scholar Recommendations | 近期 Zotero 文献作为 seeds，寻找遗漏或经典相关工作 |
| Explore / Trending | Hugging Face Daily Papers、OpenAlex | 在可配置的主题范围中发现热门论文 |

默认示例每天最多 3 篇，优先 2 篇相关 + 1 篇探索；数量、分配和来源上限均可修改。没有合格论文时少发，不降低质量阈值凑数。

兴趣来自最近入库文献的标题、摘要、标签和收藏夹路径，按时间衰减加权，使用 TF-IDF/BM25 排序。无需本地 embedding、向量数据库或 GPU。完整 Zotero Library 与当日候选通过 DOI、arXiv ID、Semantic Scholar ID、规范化标题去重；不保存推荐历史，所以没有收藏的论文以后仍可能再次推荐。

## 快速部署

1. Fork 本仓库，在 Actions 页面启用工作流。
2. 在 Settings → Secrets and variables → Actions 添加凭据：

| Secret | 说明 |
| --- | --- |
| `ZOTERO_ID`、`ZOTERO_KEY` | 个人 Library 数字 ID 与读取权限 Key |
| `SENDER`、`SENDER_PASSWORD` | 发件邮箱及 SMTP 授权码 / 应用密码 |
| `RECEIVER` | 收件邮箱 |
| `OPENAI_API_KEY`、`OPENAI_API_BASE` | LLM 凭据；关闭 LLM 时不需要 |
| `SEMANTIC_SCHOLAR_API_KEY` | 可选；公开访问可能限流 |
| `OPENALEX_API_KEY` | 可选；公开访问可能限流或受配额限制 |

3. 创建 Actions **Variable `CUSTOM_CONFIG`**，复制 [完整示例](config/github.example.yaml)。修改 SMTP 地址、端口及 `YOUR_MODEL_NAME`，不要把密钥直接写入 Variable。
4. 手动运行 **Send emails daily**。这是实际发送任务；`CI` 才是离线测试。
5. 后续默认北京时间每天 11:11 运行，GitHub 调度可能延迟。

`CUSTOM_CONFIG` 覆盖仓库的 `config/custom.yaml`，再与 `config/base.yaml` 合并。示例偏向 NLP / LLM / 语言 Agent；开源基础配置不限制探索主题，可以自行替换为任何学科。

## 常用配置

下面展示可调参数；部署时请合并进完整示例，保留 Zotero、SMTP、LLM 凭据引用。

```yaml
executor:
  max_paper_num: 3                # 每日总上限，不在代码中固定为 3
  source: [arxiv]
  reranker: bm25
  send_empty: false

recommendation:
  enabled: true
  interest_slots: 2              # 先选多少篇相关论文
  explore_slots: 1               # 最多多少篇探索论文
  min_interest_for_explore: 2    # 有足够相关论文后才启用探索位；0 表示不限
  fill_with_interest: true       # 空余总名额是否允许合格相关论文补足
  source_limits: {}             # 可设 {arxiv: 1, semantic_scholar: 1}
  source_weights: {}            # 相关来源倒数排名的权重，默认 1；0 表示不选择
  explore_sources: [huggingface, openalex]
  explore_include_topics:
    - natural language processing large language models LLM reasoning RAG language agents tool calling
  explore_exclude_topics:
    - computer vision image video generation 3D camera reconstruction robotics
    - biology medicine molecular protein physics quantum particles
  explore_focus_min_score: 0.05
  explore_exclude_min_score: 0.05
  openalex:
    fields: [17]                 # Computer Science

llm:
  enabled: true                  # false：摘要原文，不调用 LLM
  language: Chinese              # TLDR 语言
  reading_notes:
    enabled: true                # false：只生成 TLDR，不生成详细笔记
    language: Chinese

email:
  sender_name: Daily Paper
  subject_prefix: Daily Paper
  max_width: 1120                # 桌面最大宽度；窄屏自动收缩
  notes_collapsible: true        # 支持的邮箱可展开 / 收起；false 使用展开排版
```

主题筛选使用词频/逆文档频率加权与一、二元词组的 TF-IDF 相似度，不是字符串包含匹配，也不调用 LLM。排除主题相似度达到阈值、且不低于包含主题时拒绝候选。这是可解释的文本筛选，不保证所有交叉学科论文都能准确分类。探索仍需通过热度和质量门槛；没有合适探索论文不会用 CV 论文补位。

## 中文读书笔记

只对最终入选论文读取可访问全文，再调用现有兼容 Chat Completions / Responses 的 LLM 接口。笔记包含五部分：

1. 研究问题与背景。
2. 核心贡献与已有工作的区别。
3. 方法原理与关键公式 / 算法。
4. 实验设置、主要结果与证据。
5. 局限性与未解决的问题。

不包含“与你研究的联系”。长文分段提取证据再汇总；超出预算会均匀抽样并标注覆盖范围。拿不到全文时明确写“仅依据摘要”，不伪装成全文阅读。笔记失败时继续发送 TLDR 或摘要。LLM 费用由服务商决定。

邮件是表格布局 + 内联样式的 HTML，支持窄屏适配。折叠是发送前生成内容的展示交互，不是点击后请求 LLM。不同邮箱对 HTML 交互的支持不同，推荐先测试自己的客户端。

## 运行、缓存与模型依赖

```bash
uv run --no-dev src/zotero_arxiv_daily/main.py
uv run pytest
```

生产 Actions 使用 `--locked --no-dev`，显式启用基于 `uv.lock` 的 uv 依赖缓存，不安装开发环境。首次需要下载依赖，缓存命中可减少后续下载；每次 runner 仍会启动新进程。

默认依赖不含 PyTorch、sentence-transformers、peft。BM25 启动不会导入 embedding、PDF 布局或 ONNX 模型。PDF 布局提取按需在入选论文的提取子进程中启动；这不是用于排序的 embedding 模型。

保留 upstream 的可选 embedding 排序模式：

```bash
uv run --extra embeddings src/zotero_arxiv_daily/main.py recommendation.enabled=false executor.reranker=local
```

Actions 中另设 Variable `INSTALL_EMBEDDINGS=true` 安装可选依赖；同时设置上述两个配置项，才会切到 upstream 模式。该模式不应用精选模块的多来源分配策略。模型权重单独缓存，`EMBEDDING_CACHE_VERSION` 可用于更换模型后刷新缓存。缓存只避免重新下载，不能省掉模型加载与 CPU 推理；小模型可在 CPU 运行，效果和耗时需实测。

## 模块与扩展

- `discovery/`：Semantic Scholar、Hugging Face、OpenAlex 独立适配器，共享 HTTP 超时/重试。
- `recommendation.py`：近期兴趣、BM25、主题筛选、跨来源去重与可配置分配。
- `reading_notes.py`：全文读取、分段证据提取与五部分笔记。
- `construct_email.py`：邮件 HTML；`utils.py` 复用 SMTP 与文件解析。
- `config/base.yaml`：公共默认值；`config/github.example.yaml`：可直接复制的部署示例。

新发现来源实现 `retrieve(profile, config) -> list[Paper]`，在 `discovery/__init__.py` 加入调度并定义配置。将来源名加入 `explore_sources` 可归入探索池。各来源可独立禁用，API 失败不会阻断其他来源。修改领域、名额、主题和 LLM 开关无需改 Python。

## 测试与已知边界

测试使用 stub，不连接私人 Library，不发真实邮件；默认跳过下载本地 embedding 模型的 slow 测试。覆盖名额分配、去重、近期权重、自定义主题、API 降级、笔记覆盖范围和邮件渲染。

- 没有推荐历史库，也不会自动将论文写入 Zotero。
- 目前面向英文论文元数据，未实现中文分词。
- OpenAlex 热度是近期引用表现代理，不是真实引用增长率。
- 邮件发送成功表示 SMTP 接受，不保证收件箱位置或客户端交互兼容。
- API 返回 model_not_found 时，检查服务商实际可用模型 ID；任务可以成功发送降级摘要，但笔记并未生成。

## 致谢与许可证

感谢 [TideDra/zotero-arxiv-daily](https://github.com/TideDra/zotero-arxiv-daily) 提供上游实现。本分支沿用 [AGPL-3.0](LICENSE)，保留原有历史和相关声明。模型、API 和论文内容另受其各自条款约束。
