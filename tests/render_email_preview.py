"""Offline layout preview: PYTHONPATH=src python tests/render_email_preview.py."""
from pathlib import Path
from zotero_arxiv_daily.protocol import Paper
from zotero_arxiv_daily.construct_email import render_email

notes = {
    'background': '这是一份用于检查邮件排版的示例笔记，不是模型对真实论文的分析。正式运行时，这一节会说明论文试图解决的问题、研究背景，以及现有方法为什么不足。',
    'contributions': '正式笔记会区分作者声称的贡献与原文提供的证据，并说明它与已有工作的差异。\n只根据论文内容描述，不补写原文没有提供的对比结果。',
    'method': '这一节解释主要模块、数据流和算法步骤。关键公式会用纯文本描述变量与含义，方便在不同邮箱中阅读。\n复杂公式或图片若未被文本提取器完整读取，会明确指出证据缺失。',
    'experiments': '正式笔记会列出数据集、基线、评估指标和主要结果，并在可用时标明对应章节或表格。\n当前内容仅演示排版，因此不包含虚构的实验数字。',
    'limitations': '这一节整理作者讨论的局限性与尚未解决的问题；额外的批判性分析需要明确标为分析，不与作者结论混淆。',
}
papers = [Paper(source='arxiv', title='示例论文：从问题设定到实验结论，完整阅读一项研究',
    authors=['Researcher A', 'Researcher B'], abstract='', url='https://arxiv.org',
    tldr='先看一句话概括，再按需要阅读方法、实验与局限性。此邮件仅展示排版。',
    recommendation_type='Recent Interest', recommendation_reason='与你最近收藏的研究主题相关',
    reading_notes=notes, reading_notes_basis='排版示例 · 未调用 LLM'),
    Paper(source='openalex', title='示例论文：跨学科探索带来的新问题', authors=['Researcher C'],
    abstract='', url='https://openalex.org', tldr='这张卡片演示全文不可获取时的摘要解读与明确的内容依据。',
    recommendation_type='Explore / Trending', recommendation_reason='近期受到关注的跨领域研究',
    reading_notes={**notes, 'experiments': '摘要未提供实验设置、基线或具体数字，无法判断。'},
    reading_notes_basis='仅依据摘要；未获取全文 · 排版示例')]

if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1] / 'docs'
    (root / 'email-preview.html').write_text(render_email(papers), encoding='utf-8')
    (root / 'email-preview-collapsible.html').write_text(render_email(papers, collapsible=True), encoding='utf-8')
