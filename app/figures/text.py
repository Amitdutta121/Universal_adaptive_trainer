"""A figure as plain text, for the readers that cannot see pictures (ADR-080).

Dedup, the blind solver and the judges are text-only. They read a question's figure through
:func:`figure_as_text`: the kind, caption and ``alt``, plus what the figure is drawn from (the
Mermaid source, or the chart's type, axis titles, labels and every value). A computed figure is
an SVG file, so only its ``alt`` and caption are given.

The output is deterministic: the same figure always gives the same text, so the dedup hash and
the embedding cache key stay stable.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from app.figures.schema import ChartFigure, DiagramFigure, XYPoint, parse_figure


def _number(value: float) -> str:
    """``42.0`` as ``42``; other floats in full (``repr``), never rounded."""
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def _chart_lines(figure: ChartFigure) -> list[str]:
    chart = figure.chart
    lines = [f"Chart type: {chart.type}"]
    if chart.x_title:
        lines.append(f"X axis: {chart.x_title}")
    if chart.y_title:
        lines.append(f"Y axis: {chart.y_title}")
    labels = chart.data.labels
    if labels:
        lines.append("Labels: " + ", ".join(labels))
    for dataset in chart.data.datasets:
        xy = [point for point in dataset.data if isinstance(point, XYPoint)]
        numbers = [point for point in dataset.data if not isinstance(point, XYPoint)]
        if xy:
            values = ", ".join(f"({_number(p.x)}, {_number(p.y)})" for p in xy)
        elif len(numbers) == len(labels):
            values = ", ".join(
                f"{label} = {_number(value)}" for label, value in zip(labels, numbers, strict=True)
            )
        else:
            values = ", ".join(_number(value) for value in numbers)
        lines.append(f'Series "{dataset.label}": {values}')
    return lines


def figure_as_text(raw: Any) -> str:
    """``raw`` (a question's ``content["figure"]``) as plain text; ``""`` when there is none.

    A figure that does not parse is given as its sorted JSON, so a broken figure still reaches
    the readers instead of disappearing.
    """
    if raw is None:
        return ""
    try:
        figure = parse_figure(raw)
    except ValidationError:
        return "Figure (unreadable): " + json.dumps(raw, sort_keys=True, default=str)
    head = f"Figure ({figure.kind})"
    lines = [f"{head}: {figure.caption}" if figure.caption else head, f"Alt text: {figure.alt}"]
    if isinstance(figure, DiagramFigure):
        lines.append("Mermaid source:")
        lines.append(figure.source.strip())
    elif isinstance(figure, ChartFigure):
        lines.extend(_chart_lines(figure))
    return "\n".join(lines)
