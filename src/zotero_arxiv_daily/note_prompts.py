"""Prompts and display labels for evidence-based, explanatory reading notes."""

SECTIONS = {
    'background': '研究问题与具体 Gap',
    'contributions': '核心亮点与已有工作的区别',
    'method': '困难 → 设计 → 作用机制',
    'experiments': '实验是否支撑这些贡献',
    'limitations': '适用边界与未解决的问题',
}

EXTRACTION = '''Extract an evidence ledger, not a miniature review of the whole paper.
This is ONE supplied fragment, not the entire paper. A fact absent from this fragment
may appear in other fragments: never conclude that the paper lacks it.
Return only JSON: {"facts": [{"kind": "background|contributions|method|experiments|limitations",
"claim": "precise factual statement", "quote": "short verbatim supporting excerpt from THIS FRAGMENT",
"location": "section/table/figure identifier present in this fragment, or fragment only"}]}.
Preserve task constraints, named prior approaches and their failure modes; the specific gap;
difficulty -> mechanism -> effect links; input/output and steps; closest-baseline differences;
numbers with dataset, metric, evaluation setting and comparator; ablations and counterexamples.
Main-text results take precedence over incidental appendix details. Quotes must be exact
contiguous text from this fragment, at most 500 characters each. Do not make up locators.
Select at most 12 useful facts. If a fragment is only references/no relevant evidence, use [].
Do not repeat abstract facts unless the fragment supplies additional supporting details.'''


def synthesis(config):
    visuals = ''
    if config.get('include_visuals', True):
        visuals = '''
Also return three arrays (empty if unsupported), MAX_ROWS:
"method_map": [{"difficulty": "concrete failure mode", "design": "corresponding component",
"mechanism": "how/why the design addresses the difficulty", "evidence": "original section/figure or F# label"}],
"experiment_table": [{"comparison": "method vs named baseline or ablation",
"setting": "dataset + metric + evaluation conditions", "result": "exact supported numbers or explicit qualitative result",
"meaning": "which claim this supports, or fails to support", "evidence": "original table/section or F# label"}],
"pipeline": ["one concrete method step", "next step"], MAX_STEPS.
Do not fabricate a linear order if the method cannot be represented as ordered steps; use [].
Tables should complement rather than duplicate prose. Keep cells readable while explaining the actual mechanism.
These are structured data, not HTML, Markdown tables, image URLs or Mermaid.
'''.replace('MAX_ROWS', f"with at most {config['max_visual_rows']} rows per table" if config.get('max_visual_rows') is not None else 'with as many evidence-supported rows as needed')
        visuals = visuals.replace('MAX_STEPS', f"at most {config['max_pipeline_steps']} steps" if config.get('max_pipeline_steps') is not None else 'as many meaningful steps as the method requires')
    length = (f"Aim for roughly {config['section_target_chars']} Chinese characters per prose section when useful."
              if config.get('section_target_chars') is not None else
              'There is no fixed section length. Explain the reasoning and mechanisms fully; omit repetition and filler.')
    return f'''Write explanatory reading notes in {config.language} for a researcher who has
not read this paper. Help them understand WHY the work was needed and HOW its mechanisms work.
Return only a JSON object with these five string fields, plus the arrays specified below:
background: State the concrete task (input, output, constraints), how existing approaches solve it,
where they fail, WHY they fail, and the precise remaining gap. Contrast at least the closest
named approaches when supported. Avoid generic openings like "LLMs have developed rapidly".
contributions: Lead with the central insight. Explain the actual difference from the closest
prior method: which information, decision, state, objective or feedback path changes and why
that matters. Distinguish novel mechanisms, combinations of known components and evaluation claims.
method: Explain the execution path in understandable terms. For each key difficulty, identify
the matching design, its inputs and outputs, how it works, and why it should alleviate that
difficulty. Explain key formulas/variables where useful; naming MCTS, reflection or memory is
not an explanation. Label mechanism-based interpretations as interpretations, not experimental proof.
experiments: Prioritize MAIN results before appendix engineering details. Explain what was tested,
against which baselines, under what budget/feedback conditions, with which metrics. Preserve
supported numerical comparisons and mixed/negative results. Map ablations to individual contribution
claims. Separate overall improvement from causal evidence about a component; do not claim
statistical significance unless tested. Never conflate visible tests and held-out evaluation.
limitations: Separate author-stated limits, evidence-supported boundary conditions, and your
clearly labeled inferences. Explain when the mechanism is likely to fail and what remains unverified.

{length} Clarity and causal reasoning
matter more than filling a length quota. Use connected paragraphs per section with plain
text/newlines. Do not include personal research relevance or suggestions for the reader.
Use only supplied evidence; cite original section/table labels where available. With a ledger,
you may cite F# fragment labels. Never claim you saw raw text when only ledger facts were supplied.
The COVERAGE MANIFEST is authoritative: absence in ONE fragment does not mean absence from the paper.
Review ALL fragments and raw anchors before declaring evidence missing. Put coverage caveats in
the supplied coverage label; do not repeat a disclaimer in every section. In abstract-only mode,
explain what the abstract does support and explicitly limit unsupported method/experiment details.
Self-check before returning: is the gap specific? is each key component tied to a difficulty?
are main results consistent with the abstract? did you confuse partial evidence with absent evidence?
{visuals}'''
