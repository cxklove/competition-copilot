"""COMAP MCM 2027 instructions observation; bounded HTTP and schedule parsing."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from http.client import HTTPException
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from pydantic import ValidationError

from competition_copilot.application.monitoring import CompetitionObservationSource
from competition_copilot.domain.digital_twin import (
    CompetitionDynamicState,
    CompetitionTarget,
    ObservedTimeWindow,
    ObservedTrackMembership,
)
from competition_copilot.domain.monitoring import (
    MonitorCheckRequest,
    SourceCheckError,
    SourceCheckErrorCode,
    SourceObservationResult,
)
from competition_copilot.domain.source_metadata import SourceMetadata, SourceType
from competition_copilot.domain.temporal import TimeWindow

OFFICIAL_URL = "https://contest.comap.com/undergraduate/contests/mcm/instructions.php"
SUPPORTED_TARGET = CompetitionTarget(
    competition_id="comap-mcm", edition_id="comap-mcm-2027"
)
MAX_BODY_BYTES = 1_000_000


@dataclass(frozen=True)
class ComapPageResponse:
    status: int
    body: bytes
    final_url: str
    content_type: str = "text/html; charset=UTF-8"


class ComapPageFetcher(Protocol):
    """Fetch the fixed approved instructions page; no caller-controlled URL."""

    def fetch(self) -> ComapPageResponse: ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class UrllibComapPageFetcher:
    """Single HTTPS read; no redirects, environment proxy, cookies, auth or retry."""

    def fetch(self) -> ComapPageResponse:
        opener = build_opener(ProxyHandler({}), _NoRedirect())
        request = Request(
            OFFICIAL_URL, headers={"User-Agent": "CompetitionCopilot/0.1"}
        )
        with opener.open(request, timeout=15) as response:
            return ComapPageResponse(
                status=response.status,
                body=response.read(MAX_BODY_BYTES + 1),
                final_url=response.geturl(),
                content_type=response.headers.get("Content-Type", ""),
            )


class ComapParseError(ValueError):
    """The approved bounded schedule structure or its labeled text is unsupported."""


class _ScheduleParser(HTMLParser):
    """Read only the ul immediately following the exact 2027 schedule heading."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.titles = []
        self.items = []
        self._title = None
        self._strong = None
        self._item = None
        self._armed = False
        self._capturing = False
        self.headings = 0
        self.complete = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self._title = []
        if tag == "strong":
            self._strong = []
        if self._armed and tag == "ul":
            self._armed = False
            self._capturing = True
        elif self._armed and tag not in ("br",):
            raise ComapParseError("Schedule heading must be followed by its list")
        elif self._capturing and tag == "ul":
            raise ComapParseError("Nested schedule lists are unsupported")
        if self._capturing and tag == "li":
            if self._item is not None:
                raise ComapParseError("Unclosed schedule item")
            self._item = []

    def handle_data(self, data):
        for buffer in (self._title, self._strong, self._item):
            if buffer is not None:
                buffer.append(data)
        if self._armed and data.strip():
            raise ComapParseError("Unexpected text between schedule heading and list")

    def handle_endtag(self, tag):
        if tag == "title" and self._title is not None:
            self.titles.append(" ".join("".join(self._title).split()))
            self._title = None
        if tag == "strong" and self._strong is not None:
            heading = " ".join("".join(self._strong).split())
            self._strong = None
            if heading == "2027 Contest Dates and Times:":
                self.headings += 1
                self._armed = True
        if self._capturing and tag == "li" and self._item is not None:
            self.items.append(" ".join("".join(self._item).split()))
            self._item = None
        if self._capturing and tag == "ul":
            if self._item is not None:
                raise ComapParseError("Unclosed schedule item")
            self._capturing = False
            self.complete = True


_MONTHS = {
    name: index
    for index, name in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        1,
    )
}
_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_DATE = rf"(?P<weekday>{'|'.join(_WEEKDAYS)}),\s+(?P<month>{'|'.join(_MONTHS)})\s+(?P<day>\d{{1,2}}),\s+(?P<year>\d{{4}})\.?"
_CLOCK = re.compile(
    rf"(?:Before\s+)?(?P<hour>\d{{1,2}}):(?P<minute>\d{{2}})\s+(?P<period>a\.m\.|p\.m\.)\s+(?:(?P<zone>[A-Z]{{2,4}})\s+)?on\s+{_DATE}"
)
_DATE_ONLY = re.compile(
    rf"(?:Before\s+)?(?:(?:{'|'.join(_WEEKDAYS)}),\s+)?(?:{'|'.join(_MONTHS)})\s+\d{{1,2}},\s+\d{{4}}\.?"
)


def _clock_value(text: str) -> datetime | None:
    if _DATE_ONLY.fullmatch(text) or text in ("TBA", "To be announced"):
        return None
    match = _CLOCK.fullmatch(text)
    if match is None:
        raise ComapParseError("Unsupported labeled schedule format")
    values = match.groupdict()
    hour, minute = int(values["hour"]), int(values["minute"])
    if not 1 <= hour <= 12 or not 0 <= minute <= 59:
        raise ComapParseError("Invalid clock time")
    # The reviewed source explicitly specifies EST, a fixed UTC-05:00 zone.
    # Other/omitted zones and date-only facts cannot be promoted to aware instants.
    if values["zone"] != "EST":
        return None
    hour = hour % 12 + (12 if values["period"] == "p.m." else 0)
    try:
        result = datetime(
            int(values["year"]),
            _MONTHS[values["month"]],
            int(values["day"]),
            hour,
            minute,
            tzinfo=timezone(timedelta(hours=-5), "EST"),
        )
    except ValueError as exc:
        raise ComapParseError("Invalid calendar date") from exc
    if _WEEKDAYS[result.weekday()] != values["weekday"]:
        raise ComapParseError("Conflicting date and weekday")
    return result


def parse_comap_schedule(html: str, source: SourceMetadata) -> CompetitionDynamicState:
    parser = _ScheduleParser()
    parser.feed(html)
    parser.close()
    if (
        "Contest Rules, Registration and Instructions" not in parser.titles
        or parser.headings != 1
        or not parser.complete
        or not parser.items
    ):
        raise ComapParseError("Missing/ambiguous COMAP 2027 instructions schedule root")
    labels = ("Registration Deadline", "Contest Starts", "Contest Ends")
    values = {}
    recognized = False
    for item in parser.items:
        label, separator, text = item.partition(":")
        if separator and label in (
            *labels,
            "Solution Report Deadline",
            "Contest Results",
        ):
            recognized = True
        if label in labels:
            if not separator or label in values:
                raise ComapParseError("Duplicate or malformed tracked schedule label")
            values[label] = _clock_value(text.strip())
    if not recognized:
        raise ComapParseError("Schedule list has no recognized instructions facts")

    def observed_window(start, end):
        if start is None and end is None:
            return ObservedTimeWindow(state="unknown")
        return ObservedTimeWindow(
            state="known_value",
            value=TimeWindow(start_at=start, end_at=end),
            sources=(source,),
        )

    return CompetitionDynamicState(
        registration_window=observed_window(None, values.get("Registration Deadline")),
        competition_window=observed_window(
            values.get("Contest Starts"), values.get("Contest Ends")
        ),
        # MCM/ICM problem labels are not tracks; this page is not an audited track inventory.
        track_membership=ObservedTrackMembership(state="unknown"),
    )


class ComapOfficialObservationAdapter(CompetitionObservationSource):
    """Observe only the reviewed COMAP MCM 2027 instructions URL once."""

    def __init__(self, fetcher: ComapPageFetcher | None = None) -> None:
        self._fetcher = UrllibComapPageFetcher() if fetcher is None else fetcher

    def observe(self, request: MonitorCheckRequest) -> SourceObservationResult:
        if not isinstance(request, MonitorCheckRequest):
            raise TypeError("observe requires MonitorCheckRequest")
        request = MonitorCheckRequest.model_validate(request)

        def failure(code, message):
            return SourceObservationResult(
                target=request.target,
                observed_at=request.observed_at,
                source=request.source,
                outcome="check_failed",
                error=SourceCheckError(code=code, message=message),
            )

        if (
            request.target != SUPPORTED_TARGET
            or str(request.source.source_url) != OFFICIAL_URL
            or request.source.source_type != SourceType.OFFICIAL
        ):
            return failure(
                SourceCheckErrorCode.SOURCE_UNAVAILABLE,
                "Unsupported target or official source",
            )
        try:
            response = self._fetcher.fetch()
        except HTTPError as exc:
            code = (
                SourceCheckErrorCode.SOURCE_UNAVAILABLE
                if exc.code in (404, 410)
                else SourceCheckErrorCode.FETCH_FAILED
            )
            return failure(code, "Official page unavailable")
        except (TimeoutError, URLError, OSError, HTTPException):
            return failure(
                SourceCheckErrorCode.FETCH_FAILED, "Official page fetch failed"
            )
        if response.status != 200:
            code = (
                SourceCheckErrorCode.SOURCE_UNAVAILABLE
                if response.status in (404, 410)
                else SourceCheckErrorCode.FETCH_FAILED
            )
            return failure(code, "Official page HTTP failure")
        if response.final_url != OFFICIAL_URL or len(response.body) > MAX_BODY_BYTES:
            return failure(
                SourceCheckErrorCode.FETCH_FAILED,
                "Invalid official response URL or size",
            )
        if response.content_type.lower() not in (
            "text/html",
            "text/html; charset=utf-8",
        ):
            return failure(
                SourceCheckErrorCode.FETCH_FAILED,
                "Unsupported official response media type",
            )
        try:
            html = response.body.decode("utf-8")
        except UnicodeDecodeError:
            return failure(SourceCheckErrorCode.FETCH_FAILED, "Invalid UTF-8 response")
        # Explicit check time describes this observation; verification is preserved, not granted.
        source = SourceMetadata(
            source_url=request.source.source_url,
            source_type=request.source.source_type,
            observed_at=request.observed_at,
            verification_status=request.source.verification_status,
        )
        try:
            state = parse_comap_schedule(html, source)
            return SourceObservationResult(
                target=request.target,
                observed_at=request.observed_at,
                source=source,
                outcome="check_succeeded",
                dynamic_state=state,
            )
        except ComapParseError:
            return failure(
                SourceCheckErrorCode.PARSE_FAILED,
                "Unsupported COMAP schedule structure or format",
            )
        except ValidationError:
            return failure(
                SourceCheckErrorCode.INVALID_OBSERVATION,
                "Parsed facts do not satisfy frozen observation contract",
            )
