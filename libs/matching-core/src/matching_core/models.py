from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class CallerProfile:
    """What FeedService needs to know about the person requesting a feed.

    `id` is a plain string (not uuid.UUID) — the only type this package
    takes from the standard library's most basic common denominator, so
    adapters on either side (SQLAlchemy UUID columns, JSON over HTTP) can
    convert to/from it trivially without this package caring which.
    """

    id: str
    gender: str | None
    seeking: str | None
    age_min: int | None
    age_max: int | None
    has_location: bool
    interests: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class CandidateProfile:
    """A candidate as read from storage, before scoring/response shaping."""

    id: str
    name: str
    age: int | None
    bio: str | None
    photo_key: str | None
    interests: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class FeedCandidate:
    """A scored candidate, ready for the caller's adapter to shape into its
    own response schema."""

    id: str
    name: str
    age: int | None
    bio: str | None
    photo_url: str | None
    interests: list[str]
    score: float
