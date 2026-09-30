"""Ragas-based faithfulness and answer-correctness scoring, run alongside
the existing precision/recall harness (scoring.py) over the same golden set
and the same pipeline output -- see docs/RAGAS_EVAL_SPEC.md for the full
rationale and the metric-to-data mapping this implements.

Kept separate from scoring.py: different dependency footprint (the `eval`
uv dependency group, not installed by default) and a different failure mode
(Ragas makes its own judge-model calls and can fail independently of the
pipeline run itself).
"""

from dataclasses import dataclass

from ragas import EvaluationDataset, SingleTurnSample, evaluate
from ragas.llms import llm_factory
from ragas.metrics import AnswerCorrectness, Faithfulness

from ..agents.classifier import DEFAULT_CHAT_MODEL
from ..agents.diffing import diff_sections
from ..agents.verifier import VerifiedFinding
from .golden_set import GoldenSetCase


@dataclass(frozen=True)
class RagasReport:
    faithfulness: float | None
    answer_correctness: float | None
    n_samples: int


def _credible_findings_by_item_key(
    verified_findings: list[VerifiedFinding],
) -> dict[str, VerifiedFinding]:
    """Same "credible = excerpt_verified, strongest confidence wins" rule as
    scoring.py's _credible_confidence_by_item_key, but keeps the whole
    VerifiedFinding (for .finding.reasoning), not just its confidence --
    not reusing that function directly since it discards the finding itself.
    """
    best: dict[str, VerifiedFinding] = {}
    for vf in verified_findings:
        if not vf.excerpt_verified:
            continue
        item_key = vf.finding.item_key
        if item_key not in best or vf.confidence > best[item_key].confidence:
            best[item_key] = vf
    return best


def build_ragas_samples(
    case: GoldenSetCase, verified_findings: list[VerifiedFinding]
) -> list[SingleTurnSample]:
    """One sample per section where the golden set expects a finding and the
    pipeline produced a credible one -- the same scope as today's `tp` cases
    in scoring.py. Sections with no finding to score (fn/tn) or no real
    reference describing a non-existent event (fp) are left out, for the
    same reason avg_confidence_tp/avg_confidence_fp are already split that
    way in scoring.py.

    `retrieved_contexts` is built via diff_sections(), the same function the
    classifier itself calls -- scoring faithfulness against a section's full
    body_text instead would check groundedness against a superset of what
    the model actually saw, which could hide real overclaiming.
    """
    credible = _credible_findings_by_item_key(verified_findings)
    older_sections = {s["item_key"]: s for s in case.older_filing["sections"]}
    newer_sections = {s["item_key"]: s for s in case.newer_filing["sections"]}

    samples = []
    for entry in case.ground_truth:
        if not entry.expect_finding:
            continue
        vf = credible.get(entry.item_key)
        if vf is None:
            continue
        older_section = older_sections.get(entry.item_key)
        newer_section = newer_sections.get(entry.item_key)
        if older_section is None or newer_section is None:
            continue

        older_diff, newer_diff = diff_sections(
            older_section["body_text"], newer_section["body_text"]
        )
        samples.append(
            SingleTurnSample(
                user_input=(
                    f"What material change occurred in Item {entry.item_key} "
                    "between the two filings?"
                ),
                response=vf.finding.reasoning,
                retrieved_contexts=[older_diff, newer_diff],
                reference=entry.note,
            )
        )
    return samples


def score_with_ragas(samples: list[SingleTurnSample]) -> RagasReport:
    """Runs Ragas's faithfulness and answer-correctness metrics over
    `samples`, using the same chat model as the rest of the pipeline
    (DEFAULT_CHAT_MODEL) as the judge, for consistency and cost -- not
    whatever model Ragas defaults to. Makes real, billed OpenAI calls; only
    call this from the already `-m eval`-gated path, never from the default
    test run.
    """
    if not samples:
        return RagasReport(faithfulness=None, answer_correctness=None, n_samples=0)

    dataset = EvaluationDataset(samples=samples)
    judge_llm = llm_factory(model=DEFAULT_CHAT_MODEL)
    result = evaluate(
        dataset,
        metrics=[Faithfulness(), AnswerCorrectness()],
        llm=judge_llm,
        show_progress=False,
    )
    df = result.to_pandas()
    return RagasReport(
        faithfulness=float(df["faithfulness"].mean()),
        answer_correctness=float(df["answer_correctness"].mean()),
        n_samples=len(samples),
    )
