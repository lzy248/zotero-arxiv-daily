"""Table-based HTML email with optional native disclosure; no JavaScript."""
from datetime import datetime
from html import escape
import math
from urllib.parse import urlsplit
from .protocol import Paper

NOTE_HEADINGS = {
    'background': '研究问题与背景',
    'contributions': '核心贡献与已有工作的区别',
    'method': '方法原理与关键公式 / 算法',
    'experiments': '实验设置、主要结果与证据',
    'limitations': '局限性与未解决的问题',
}

framework = '''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Daily Papers · 每日论文精选</title>
<style>
@media only screen and (max-width:600px) {
  .email-outer { padding:12px 6px !important; }
  .email-padding { padding:18px 14px !important; }
  .paper-title { font-size:20px !important; }
}
</style></head>
<body style="margin:0;padding:0;background-color:#f3f5f7;color:#263548;font-family:Arial,'Microsoft YaHei',sans-serif;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#f3f5f7;table-layout:fixed;">
<tr><td class="email-outer" align="center" style="padding:28px 16px;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="width:100%;max-width:__MAX_WIDTH__px;table-layout:fixed;">
<tr><td class="email-padding" style="padding:28px 32px;background-color:#152e42;border-radius:12px 12px 0 0;">
<p style="margin:0 0 10px;color:#9bc7d2;font-size:12px;letter-spacing:3px;">DAILY PAPERS</p>
<h1 style="margin:0;color:#ffffff;font-size:26px;line-height:1.4;">每天，读懂一点新发现。</h1>
<p style="margin:12px 0 0;color:#c7d8e3;font-size:13px;">__DATE__ · __COUNT__ 篇精选</p>
</td></tr><tr><td style="padding:20px 0 0;">__CONTENT__</td></tr>
<tr><td style="padding:12px 20px 24px;color:#758294;font-size:12px;line-height:1.8;">
AI 笔记用于辅助阅读，关键结论、数字和公式请以原文为准。<br>
To unsubscribe, remove your email in your Github Action setting.
</td></tr></table></td></tr></table></body></html>'''


def safe_url(value):
    try:
        parsed = urlsplit(value or '')
        return escape(value, quote=True) if parsed.scheme in ('http', 'https') and parsed.netloc else '#'
    except ValueError:
        return '#'


def get_empty_html():
    return '<p style="padding:24px;background:#fff;border-radius:12px;">No Papers Today. Take a Rest!</p>'


def get_block_html(title, authors, rate, tldr, pdf_url, affiliations=None,
                   recommendation='', link_label='PDF', notes='', number=''):
    # Text parameters are escaped by render_email; notes is trusted template HTML.
    return f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
style="width:100%;table-layout:fixed;background-color:#ffffff;border:1px solid #dfe6ed;border-radius:12px;margin-bottom:20px;">
<tr><td class="email-padding" style="padding:28px 32px;">
<p style="margin:0 0 12px;color:#157a80;font-size:12px;letter-spacing:1px;">{number} {recommendation}</p>
<h2 class="paper-title" style="margin:0 0 12px;font-size:23px;line-height:1.45;color:#152e42;overflow-wrap:anywhere;word-break:break-word;">{title}</h2>
<p style="margin:0 0 4px;font-size:12px;line-height:1.7;color:#6a7889;">{authors}</p>
<p style="margin:0 0 16px;font-size:12px;line-height:1.7;color:#87919e;">{affiliations or ''}</p>
<div style="padding:16px;background-color:#f0f7f7;border-left:3px solid #259397;">
<strong style="font-size:11px;letter-spacing:1px;color:#157a80;">TLDR</strong>
<p style="margin:8px 0 0;font-size:14px;line-height:1.85;">{tldr}</p></div>
<p style="margin:16px 0;font-size:12px;color:#758294;">{rate}</p>
<a href="{pdf_url}" style="display:inline-block;background-color:#152e42;color:#ffffff;text-decoration:none;padding:10px 18px;border-radius:6px;font-size:13px;">{link_label}</a>
{notes}
</td></tr></table>'''


def notes_html(paper, collapsible=False):
    if not paper.reading_notes:
        if paper.reading_notes_status:
            return f'<p style="font-size:12px;color:#758294;">{escape(paper.reading_notes_status)}</p>'
        return ''
    sections = []
    for index, (key, heading) in enumerate(NOTE_HEADINGS.items(), 1):
        text = paper.reading_notes.get(key, '未提供 / 无法判断')
        paragraphs = ''.join(
            f'<p style="margin:8px 0;font-size:14px;line-height:1.9;overflow-wrap:anywhere;">{escape(line)}</p>'
            for line in text.splitlines() if line.strip())
        sections.append(f'<h3 style="margin:22px 0 8px;font-size:15px;color:#203e55;">'
                        f'<span style="color:#259397;">{index:02d}</span> {heading}</h3>{paragraphs}')
    body = (f'<p style="margin:12px 0;color:#758294;font-size:12px;line-height:1.7;">'
            f'阅读依据：{escape(paper.reading_notes_basis or "未标注")}</p>' + ''.join(sections))
    if collapsible:
        # Native enhancement only: no CSS hiding. Unsupported clients may show expanded text.
        body = ('<details><summary style="cursor:pointer;color:#157a80;font-weight:bold;'
                'font-size:15px;padding:14px 0;">详细读书笔记 · 点击展开 / 收起</summary>'
                + body + '</details>')
    else:
        body = '<h2 style="font-size:17px;color:#152e42;margin:20px 0 8px;">详细读书笔记</h2>' + body
    return '<div style="margin-top:22px;border-top:1px solid #e6ebf0;">' + body + '</div>'


def get_stars(score: float):
    full = '<span class="full-star">★</span>'
    half = '<span class="half-star">★</span>'
    if score <= 6:
        return ''
    if score >= 8:
        return full * 5
    number = math.ceil((score - 6) / .2)
    return '<div class="star-wrapper">' + full * (number // 2) + half * (number % 2) + '</div>'


def render_email(papers: list[Paper], collapsible=False, max_width=1120) -> str:
    if not isinstance(max_width, int) or isinstance(max_width, bool) or max_width < 320:
        raise ValueError('email.max_width must be an integer of at least 320 pixels')
    parts = []
    for index, p in enumerate(papers, 1):
        authors = p.authors if len(p.authors) <= 5 else p.authors[:3] + ['...'] + p.authors[-2:]
        affiliations = ', '.join(p.affiliations[:5]) if p.affiliations else 'Unknown Affiliation'
        if p.affiliations and len(p.affiliations) > 5:
            affiliations += ', ...'
        recommendation = escape(p.recommendation_type or p.source)
        if p.recommendation_type:
            reason = escape(f'{p.source} · {p.recommendation_reason or ""}')
        else:
            reason = f'Relevance: {round(p.score, 1) if p.score is not None else "Unknown"}'
        parts.append(get_block_html(
            escape(p.title), escape(', '.join(authors)), reason,
            escape(p.tldr or p.abstract or '暂无摘要'), safe_url(p.pdf_url or p.url),
            escape(affiliations), recommendation, 'PDF' if p.pdf_url else 'Paper',
            notes_html(p, collapsible), f'{index:02d} /'))
    return (framework.replace('__MAX_WIDTH__', str(max_width)).replace('__CONTENT__', ''.join(parts) or get_empty_html())
            .replace('__COUNT__', str(len(papers)))
            .replace('__DATE__', datetime.now().strftime('%Y.%m.%d')))
