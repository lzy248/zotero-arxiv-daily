# 实现说明

本分支为 Daily Paper，基于 upstream `TideDra/zotero-arxiv-daily`，保留历史与许可证。
用户入口见 [README](../README.md)，参数定义见 [配置参考](configuration.zh-CN.md)，
首次运行见 [部署清单](github-setup.zh-CN.md)。

## 复用与扩展边界

复用 Zotero 客户端、收藏夹过滤、arXiv RSS/API 检索、Paper 数据结构、全文提取、
LLM 兼容接口、TLDR、单位提取、SMTP 和 GitHub Actions。新增模块集中在：

- `discovery/common.py`：共享 HTTP 超时、有限重试与记录转换。
- `discovery/semantic_scholar.py`：近期、主题不过度重复的 Zotero seeds，先批量解析 ID 再推荐。
- `discovery/huggingface.py`：官方 trending 排序，不自行重算社区热度。
- `discovery/openalex.py`：近期引用表现、领域轮换，排除撤稿。
- `recommendation.py`：BM25 兴趣、TF-IDF 探索主题、传递身份去重、可配置名额。
- `reading_notes.py`：最终入选论文的全文读取、证据压缩与结构化笔记。

arXiv API 获取元数据失败时，可用同批 RSS 条目的标题、摘要、作者继续推荐，
仍然只处理配置允许的新公告，不另建数据源。RSS 本身不可用时不能凭空恢复论文。

## 无模型排序

最近入库时间按半衰期衰减，title/tags 提高词频权重，生成 TF-IDF 兴趣词；
候选以 BM25 的词频饱和、长度归一化排序。兴趣分数不是质量概率。
Semantic Scholar 以服务端顺序为主，做小幅引用/相关性调整；各相关来源按可调权重
进行倒数排名合并，不直接比较不同来源的原始分数。

探索主题是配置文本与候选的 TF-IDF 一元/二元词组相似度。包含、排除主题均可自定义，
与 Zotero 最近兴趣分离，允许在 NLP/Agent 范围内探索不同子方向。

## 名额与身份

先质量筛选、全局传递别名去重，再选相关、探索和可选相关补位。
DOI、去版本 arXiv ID、S2 ID、Unicode/大小写/标点归一化标题都参与身份合并。
完整 Library 用于去重，无摘要和被收藏夹过滤排除的条目仍然参与。
不维护推荐历史，不自动写入 Zotero。

## 读书笔记与邮件

五部分：背景、贡献、方法、实验、局限性。获取不到全文明确标注摘要模式；长文
按预算分段，超预算抽样标注覆盖。LLM 输出需满足结构，渲染前一律转义，不执行模型 HTML。
失败继续发送已有摘要，不将工作流成功误解为所有笔记均成功。

邮件采用流式表格与内联样式，桌面宽度可配置，移动端缩小间距。原生折叠属于可选增强，
不能保证所有邮件客户端交互一致。预览文件只演示排版，不是真实模型生成的研究结论。

## 启动审计与依赖

BM25 主程序导入实测不加载 torch、sentence_transformers、transformers、peft、
pymupdf、pymupdf4llm、onnxruntime。PDF 模型只在提取 PDF 的工作进程中按需加载。
默认依赖清单排除 embedding 相关库，保留 `embeddings` 可选 extra 以使用 upstream 排序器。
Actions 默认 `--locked --no-dev`，依赖缓存与可选模型缓存独立。

## 测试

单元与集成测试使用 stub，验证去重、主题筛选、名额、API 故障降级、全文回退、
笔记结构与邮件渲染。slow 测试单独覆盖 upstream 本地模型，需要安装 embedding extra。
真实运行仍需检查来源故障、模型权限、配额及 SMTP 日志。

## 接口参考

- [Semantic Scholar 官方教程](https://www.semanticscholar.org/product/api/tutorial)
- [Hugging Face Daily Papers](https://huggingface.co/docs/huggingface_hub/package_reference/hf_api#huggingface_hub.HfApi.list_daily_papers)
- [OpenAlex API](https://help.openalex.org/api/)
- [setup-uv 缓存说明](https://github.com/astral-sh/setup-uv)
- [GitHub 缓存说明](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
