"""One pager for Egeria find/get calls: an empty page is not the end, and on some paths neither is null.

Egeria's paging contract (finding-metadata/overview, "Paging", restated by the Egeria lead on 2026-11-13):
page with ``startFrom`` += ``pageSize`` until the server returns *null* (the ``elements`` key absent). An
*empty list* means server-side filtering (security, zones, Memento/lineage) removed every row of that page,
so the caller carries on. ``startFrom`` is an offset into the repository's rows *before* filtering, so the
pager always advances by the page size it asked for, never by the number of rows it got back.

On some paths Egeria also sends null for a page that filtering emptied (metadata-expert by-search-conditions:
raw capture 2026-11-13, ``~/.re-gate/B5-RAW-CAPTURE-2026-11-13.md``; MetadataElementHandler returns null for
an empty filtered list). There, null is not proof of the end. A call site says which kind of path it pages
with ``end_policy``:

- ``"trusted"``: null is the end (``end="confirmed"``).
- ``"suspect"`` (the default): on null, probe the next ``probe_pages`` pages. Rows there mean the null was a
  filtered page and paging resumes; nothing there ends the read with ``end="not_confirmed"``.

The result says how the read ended, so a caller never shows "nothing" or a total it didn't establish:

- ``confirmed``: the server said there is no more, on a path where that can be trusted.
- ``not_confirmed``: the read stopped without proof of the end (a suspect null and empty probes, or too
  many consecutive filtered positions).
- ``capped``: the caller's limits stopped it (``want`` rows collected, or ``max_pages``); there may be more.
- ``stalled``: a page brought only rows already read (a server ignoring ``startFrom``); stopped so it
  can't loop forever.

Anything but ``confirmed`` is "at least N" (``PageResult.count_text``), never a total.

``fetch(start, size)`` returns a list (rows; ``[]`` for a filtered page) or anything else (None, pyegeria's
"No elements found" string) for null. Exceptions from ``fetch`` propagate: the caller decides what a failed
read means. This module only pages; it changes nothing about what pyegeria's public methods return.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Hashable, List, Optional, Tuple

DEFAULT_FETCH_PAGE_SIZE = 100   # rows asked for per request; below the server's maximum page size
DEFAULT_PROBE_PAGES = 3         # extra pages read after a null on a suspect path
DEFAULT_MAX_EMPTY_ROWS = 2000   # consecutive filtered positions before giving up (rows, not pages)
DEFAULT_MAX_PAGES = 1000        # requests per read, probes included

END_POLICIES = ("trusted", "suspect")
ENDS = ("confirmed", "not_confirmed", "capped", "stalled")


@dataclass(frozen=True)
class PageResult:
    """What a paged read found and how it ended. ``items`` is cut to ``want`` when one was given."""
    items: List[Any]
    end: str
    note: Optional[str] = None
    pages_read: int = 0
    positions_read: int = 0   # how far into the server's (pre-filter) rows the read got

    @property
    def complete(self) -> bool:
        """True only when the server confirmed there is nothing more."""
        return self.end == "confirmed"

    def count_text(self) -> str:
        """The count as it may be shown: "N" when complete, else "at least N"."""
        n = len(self.items)
        return str(n) if self.complete else f"at least {n}"


def default_key(item: Any) -> Hashable:
    """An element's GUID (Egeria 6 elementHeader, or a relationship header), else the object's identity."""
    if isinstance(item, dict):
        for holder in (item.get("elementHeader"), item.get("relationshipHeader"), item):
            if isinstance(holder, dict) and isinstance(holder.get("guid"), str):
                return holder["guid"]
    return id(item)


@dataclass
class _Pager:
    """The paging state machine, shared by the sync and async drivers. ``request()`` gives the next
    (start, size) to fetch or None when done; ``feed(page)`` takes what that fetch returned."""
    want: Optional[int]
    size: int
    policy: str
    probe_pages: int
    max_empty_rows: int
    max_pages: int
    key: Callable[[Any], Hashable]
    start: int = 0
    pages: int = 0
    empty_rows: int = 0
    probes_left: Optional[int] = None   # None: not probing
    null_at: Optional[int] = None       # where the suspect null came back
    items: List[Any] = field(default_factory=list)
    seen: set = field(default_factory=set)
    result: Optional[PageResult] = None

    def request(self) -> Optional[Tuple[int, int]]:
        if self.result is not None:
            return None
        if self.pages >= self.max_pages:
            self._finish("capped", f"stopped after {self.pages} pages of {self.size}; there may be more")
            return None
        return self.start, self.size

    def feed(self, page: Any) -> None:
        self.pages += 1
        at = self.start
        self.start += self.size
        if not isinstance(page, list):
            self._null(at)
        elif not page:
            self._empty(at)
        else:
            self._rows(page, at)

    # ── one handler per kind of page ──

    def _null(self, at: int) -> None:
        if self.policy == "trusted":
            self._finish("confirmed", None)
            return
        if self.probes_left is None:
            self.probes_left, self.null_at = self.probe_pages, at
        else:
            self.probes_left -= 1
        if self.probes_left <= 0:
            self._finish("not_confirmed",
                         f"Egeria reported no more at position {self.null_at}, and the next "
                         f"{self.probe_pages} pages of {self.size} were empty too; on this path a filtered page "
                         f"also reads as 'no more', so later matches can't be ruled out")

    def _empty(self, at: int) -> None:
        self.probes_left = None   # an empty page means the server has rows here: not the end
        self.empty_rows += self.size
        if self.empty_rows >= self.max_empty_rows:
            self._finish("not_confirmed",
                         f"{self.empty_rows} consecutive positions (up to {at + self.size}) were filtered out "
                         f"for you; there may be more")

    def _rows(self, page: list, at: int) -> None:
        self.probes_left = None
        self.empty_rows = 0
        fresh = []
        for item in page:
            k = self.key(item)
            if k not in self.seen:
                self.seen.add(k)
                fresh.append(item)
        if not fresh:
            self._finish("stalled",
                         f"the read from position {at} returned only rows already read (the server may be "
                         f"ignoring startFrom), so it stopped at {len(self.items)}")
            return
        self.items.extend(fresh)
        if self.want is not None and len(self.items) >= self.want:
            self._finish("capped", f"stopped at the {self.want} rows asked for; there may be more")

    def _finish(self, end: str, note: Optional[str]) -> None:
        items = self.items[: self.want] if self.want is not None else self.items
        self.result = PageResult(items=list(items), end=end, note=note, pages_read=self.pages,
                                 positions_read=self.start)


def _pager(want, fetch_page_size, end_policy, probe_pages, max_empty_rows, max_pages, key) -> _Pager:
    if end_policy not in END_POLICIES:
        raise ValueError(f"end_policy must be one of {END_POLICIES}, not {end_policy!r}")
    for name, value, low in (("fetch_page_size", fetch_page_size, 1), ("probe_pages", probe_pages, 1),
                             ("max_empty_rows", max_empty_rows, 1), ("max_pages", max_pages, 1)):
        if not isinstance(value, int) or isinstance(value, bool) or value < low:
            raise ValueError(f"{name} must be a whole number of at least {low}, not {value!r}")
    if want is not None and (not isinstance(want, int) or isinstance(want, bool) or want < 1):
        raise ValueError(f"want must be None or a whole number of at least 1, not {want!r}")
    return _Pager(want=want, size=fetch_page_size, policy=end_policy, probe_pages=probe_pages,
                  max_empty_rows=max_empty_rows, max_pages=max_pages, key=key or default_key)


def page_all(fetch: Callable[[int, int], Any], *, want: Optional[int] = None,
             fetch_page_size: int = DEFAULT_FETCH_PAGE_SIZE, end_policy: str = "suspect",
             probe_pages: int = DEFAULT_PROBE_PAGES, max_empty_rows: int = DEFAULT_MAX_EMPTY_ROWS,
             max_pages: int = DEFAULT_MAX_PAGES, key: Optional[Callable[[Any], Hashable]] = None) -> PageResult:
    """Read every row ``fetch(start, size)`` gives (or the first ``want``), paging until the end is known
    or a limit stops it. See the module docstring for ``end_policy`` and the ``end`` states."""
    pager = _pager(want, fetch_page_size, end_policy, probe_pages, max_empty_rows, max_pages, key)
    while (req := pager.request()) is not None:
        pager.feed(fetch(*req))
    return pager.result


async def async_page_all(fetch: Callable[[int, int], Awaitable[Any]], *, want: Optional[int] = None,
                         fetch_page_size: int = DEFAULT_FETCH_PAGE_SIZE, end_policy: str = "suspect",
                         probe_pages: int = DEFAULT_PROBE_PAGES, max_empty_rows: int = DEFAULT_MAX_EMPTY_ROWS,
                         max_pages: int = DEFAULT_MAX_PAGES,
                         key: Optional[Callable[[Any], Hashable]] = None) -> PageResult:
    """``page_all`` for an async ``fetch``."""
    pager = _pager(want, fetch_page_size, end_policy, probe_pages, max_empty_rows, max_pages, key)
    while (req := pager.request()) is not None:
        pager.feed(await fetch(*req))
    return pager.result
