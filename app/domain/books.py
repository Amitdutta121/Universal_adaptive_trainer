"""Source book entities shared across subsystems.

A book's text lives in chunks (:mod:`app.domain.chunks`). What remains here is the
warning a book row can carry. The chapter/section tree that used to be declared by a book
JSON document, or read from a PDF's outline, was retired with that import path (Task 10);
its tables are kept until the open question about dropping them is answered.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ExtractionWarningCode, WarningSeverity


class ExtractionWarning(BaseModel):
    """One thing that went wrong, or could not be determined, during extraction.

    Warnings are surfaced to the professor rather than logged and forgotten: an
    extraction that quietly dropped half a book is worse than one that says so.
    """

    model_config = ConfigDict(frozen=True)

    code: ExtractionWarningCode
    message: str = Field(min_length=1)
    #: Where the problem occurred, e.g. "page 42" or "section 3.1". Optional
    #: because some warnings are document-wide.
    location: str | None = None
    #: Defaults to ``DEFECT``: a new warning is treated as a problem until it is
    #: explicitly declared informational, so the failure mode is over-reporting
    #: rather than hiding something.
    severity: WarningSeverity = WarningSeverity.DEFECT

    @property
    def is_defect(self) -> bool:
        return self.severity is WarningSeverity.DEFECT

    def __str__(self) -> str:
        return f"{self.message} ({self.location})" if self.location else self.message
