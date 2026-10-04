from dataclasses import dataclass, field
from datetime import datetime, timezone


class CollectionError(Exception):
    """Only controlled messages belong here; never include response bodies/tokens."""
    def __init__(self, status, reason):
        self.status, self.reason = status, reason
        super().__init__(reason)


@dataclass
class Result:
    page_url: str
    page_name: str = ""
    website_url: str = ""
    observations: set[tuple[str, str]] = field(default_factory=set)
    status: str = "no_email"
    error_reason: str = ""
    collected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
