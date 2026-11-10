"""The figure contract (ADR-080), frozen after fig1.

A figure is an optional ``figure`` on any question's ``content``. It is something the student
reads, never an answer: grading does not look at it. Every figure has a required ``alt``, the
text a screen reader reads and the only view of a computed figure a text-only judge gets.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

#: A computed figure's ``file``: ``<course_id>/<sha256>.svg`` (see :mod:`app.figures.storage`).
FIGURE_KEY = re.compile(r"^[0-9]{1,12}/[0-9a-f]{64}\.svg$")


class _FigureBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: The text alternative: what the figure shows, in words.
    alt: str = Field(min_length=1, pattern=r"\S")
    caption: str = ""


class DiagramFigure(_FigureBase):
    kind: Literal["diagram"]
    #: Mermaid source. The frontend renders it with ``securityLevel: "strict"``.
    source: str = Field(min_length=1)


class XYPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class ChartDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    data: list[float] | list[XYPoint] = Field(min_length=1)


class ChartData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: One per data point; empty for a scatter chart, whose points carry their own x.
    labels: list[str] = Field(default_factory=list)
    datasets: list[ChartDataset] = Field(min_length=1)


class ChartSpec(BaseModel):
    """A Chart.js chart as data only: no callbacks, no plugins, no options beyond axis titles."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["bar", "line", "pie", "doughnut", "scatter"]
    data: ChartData
    x_title: str | None = None
    y_title: str | None = None


class ChartFigure(_FigureBase):
    kind: Literal["chart"]
    chart: ChartSpec


class ComputedFigure(_FigureBase):
    kind: Literal["computed"]
    #: Storage key of the SVG file, never the SVG text (ADR-080 decision 4).
    file: str = Field(min_length=1)


Figure = Annotated[DiagramFigure | ChartFigure | ComputedFigure, Field(discriminator="kind")]

_FIGURE_ADAPTER: TypeAdapter[DiagramFigure | ChartFigure | ComputedFigure] = TypeAdapter(Figure)


def parse_figure(raw: Any) -> DiagramFigure | ChartFigure | ComputedFigure:
    """The figure in ``raw``. Raises ``pydantic.ValidationError`` when it is not one."""
    return _FIGURE_ADAPTER.validate_python(raw)


#: First keyword of every Mermaid diagram type allowed.
MERMAID_KINDS = (
    "flowchart",
    "graph",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "stateDiagram-v2",
    "erDiagram",
    "mindmap",
    "timeline",
)
#: Mermaid directives that reach outside the diagram: links, callbacks, init overrides.
_MERMAID_FORBIDDEN = re.compile(r"^\s*(click|%%\{)|javascript:|<script", re.IGNORECASE | re.M)


def mermaid_problems(source: str) -> list[str]:
    """Why ``source`` cannot be drawn safely as a Mermaid diagram; ``[]`` if it can."""
    source = source.strip()
    problems: list[str] = []
    first = source.split(None, 1)[0] if source else ""
    if first not in MERMAID_KINDS:
        problems.append(
            f"the diagram must start with a Mermaid diagram type ({', '.join(MERMAID_KINDS)})"
        )
    if _MERMAID_FORBIDDEN.search(source):
        problems.append("the diagram may not use click, init directives, links or scripts")
    if '\\"' in source:
        # Mermaid has no backslash escapes: A["\"x\""] does not parse, and the reader
        # would see the source instead of the diagram.
        problems.append(
            'labels may not contain \\" (Mermaid has no escapes); write A["label"], '
            "and #quot; for a quote inside a label"
        )
    return problems


def _chart_problems(chart: ChartSpec) -> list[str]:
    problems: list[str] = []
    labels = chart.data.labels
    for dataset in chart.data.datasets:
        name = f"dataset '{dataset.label}'"
        points = all(isinstance(point, XYPoint) for point in dataset.data)
        if chart.type == "scatter":
            if not points:
                problems.append(f"{name}: a scatter chart needs {{x, y}} points")
        elif points:
            problems.append(f"{name}: a {chart.type} chart needs one number per label")
        elif len(dataset.data) != len(labels):
            problems.append(
                f"{name} has {len(dataset.data)} values but the chart has {len(labels)} labels"
            )
    return problems


def figure_problems(figure: Any) -> list[str]:
    """Why ``figure`` cannot be shown, as plain sentences; ``[]`` if it can.

    Accepts a parsed figure or its raw dict.
    """
    if isinstance(figure, DiagramFigure | ChartFigure | ComputedFigure):
        parsed = figure
    else:
        try:
            parsed = parse_figure(figure)
        except ValidationError as exc:
            return [
                f"field '{'.'.join(str(part) for part in error['loc'])}': {error['msg']}"
                for error in exc.errors()
            ]
    if isinstance(parsed, DiagramFigure):
        return mermaid_problems(parsed.source)
    if isinstance(parsed, ChartFigure):
        return _chart_problems(parsed.chart)
    if not FIGURE_KEY.match(parsed.file):
        return ["the computed figure's file is not a stored figure key"]
    return []
