"""Adaptive Trainer.

An adaptive Python training platform made of two deliberately separate systems:

* the professor-facing content-generation system (books -> curriculum -> questions
  -> validation -> professor review -> personalization), and
* the student-facing adaptive-training system (BKT mastery, subtopic weakness,
  weakness-weighted roulette selection).

See ``docs/DECISIONS.md`` for the architectural decision log.
"""

__version__ = "0.1.0"
