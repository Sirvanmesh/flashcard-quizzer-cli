"""Domain models for the Flashcard Quizzer."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Flashcard:
    """A single flashcard with a prompt (front) and its answer (back).

    The dataclass is frozen so cards can be shared between quiz modes,
    used as dictionary keys and never modified by accident mid-quiz.
    """

    front: str
    back: str
