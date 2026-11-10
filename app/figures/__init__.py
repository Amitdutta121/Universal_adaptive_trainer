"""Figures a question (or a tutorial block) can carry: diagram, chart or computed (ADR-080).

Subject-neutral by rule: nothing here names a subject, preset or course
(``tests/test_figures_universal.py`` scans this package). Imports only ``app.config``, pydantic
and the standard library, so ``app.question_types`` and ``app.tutorials`` can both use it.
"""

from app.figures.schema import (
    ChartData,
    ChartDataset,
    ChartFigure,
    ChartSpec,
    ComputedFigure,
    DiagramFigure,
    Figure,
    XYPoint,
    figure_problems,
    mermaid_problems,
    parse_figure,
)

__all__ = [
    "ChartData",
    "ChartDataset",
    "ChartFigure",
    "ChartSpec",
    "ComputedFigure",
    "DiagramFigure",
    "Figure",
    "XYPoint",
    "figure_problems",
    "mermaid_problems",
    "parse_figure",
]
