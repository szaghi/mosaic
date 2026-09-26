"""HAL (Hyper Articles en Ligne) search source."""

from __future__ import annotations

import re

import httpx

from mosaic.models import Paper, SearchFilters
from mosaic.parsing import normalise_doi
from mosaic.sources.base import BaseSource, any_of, build_field_query, lucene_phrase, with_retry

_BASE = "https://api.archives-ouvertes.fr/search/"
_FL = "title_s,authFullName_s,producedDate_s,doiId_s,abstract_s,journalTitle_s,fileMain_s,openAccess_bool,uri_s"


class HALSource(BaseSource):
    """Search source for HAL (Hyper Articles en Ligne).

    HAL is the French open archive for scholarly publications, operated by
    CCSD (Centre pour la Communication Scientifique Directe). It indexes
    1.5 million+ open-access documents, with particular strength in French
    academic output and grey literature. No authentication is required — the
    API is freely accessible without any key or email address.

    The API supports Lucene/SOLR query syntax, enabling native year, author,
    and journal filtering as well as field-scoped queries.

    Attributes:
        name: Human-readable source name used for display and filtering.
    """

    name = "HAL"

    def __init__(self) -> None:
        """Initialise the HAL source.

        No credentials or configuration are required.
        """

    def available(self) -> bool:
        """Return True — HAL requires no credentials.

        Returns:
            Always True.
        """
        return True

    def search(
        self,
        query: str,
        max_results: int = 25,
        filters: SearchFilters | None = None,
    ) -> list[Paper]:
        """Search the HAL open archive API.

        Supports field scoping to title via the ``title_t:`` prefix and to
        abstract via ``abstract_t:``. Year (``producedDateY_i``), author, and
        journal filters are appended natively as Lucene clauses.

        Args:
            query: Free-text search query.
            max_results: Maximum number of results to request (capped at 100).
            filters: Optional filters for field scoping and native filtering.
                ``raw_query`` overrides the default mapping if set. Year,
                author, and journal filters are applied natively.

        Returns:
            A list of Paper objects parsed from the ``response.docs`` array.
            Returns an empty list when no documents are present in the response.
        """
        # Search the tokenised ``*_t`` fields (case/accent-insensitive).  The
        # ``*_s`` variants are exact-match strings meant for display and
        # faceting: ``title_s:"deep learning"`` only matches a title that is
        # exactly "deep learning".
        q = build_field_query(query, filters, "title_t:{}", "abstract_t:{}", phrase=True)

        # Append native year filter on the integer production-year field
        if filters:
            if filters.years:
                q += f" AND producedDateY_i:({' OR '.join(str(y) for y in filters.years)})"
            elif filters.year_from is not None or filters.year_to is not None:
                lo = filters.year_from if filters.year_from is not None else "*"
                hi = filters.year_to if filters.year_to is not None else "*"
                q += f" AND producedDateY_i:[{lo} TO {hi}]"

            if filters.authors:
                q += " AND " + any_of(map(lucene_phrase, filters.authors), "authFullName_t:{}")

            if filters.journal:
                q += f" AND journalTitle_t:{lucene_phrase(filters.journal)}"

        params: dict = {
            "q": q,
            "rows": min(max_results, 100),
            "fl": _FL,
            "wt": "json",
        }

        with httpx.Client(timeout=30) as client:
            resp = with_retry(lambda: client.get(_BASE, params=params))
            resp.raise_for_status()
            docs = resp.json().get("response", {}).get("docs", [])
        return [self._parse(doc) for doc in docs]

    def _parse(self, doc: dict) -> Paper:
        """Parse a single HAL document dict into a Paper.

        Args:
            doc: A dict from the HAL ``response.docs`` array, containing
                ``title_s`` (list), ``authFullName_s`` (list), ``producedDate_s``
                (string), ``doiId_s`` (string or absent), ``abstract_s`` (list
                or absent), ``journalTitle_s`` (string or absent), ``fileMain_s``
                (string or absent), ``openAccess_bool`` (boolean), and ``uri_s``
                (string).

        Returns:
            A Paper with ``url`` set to the HAL record page (``uri_s``) and
            ``pdf_url`` set to ``fileMain_s`` when present.
        """
        # title_s is a list; take the first element
        title_list = doc.get("title_s") or []
        title = title_list[0] if title_list else ""

        # authors: plain list of full-name strings
        authors: list[str] = list(doc.get("authFullName_s") or [])

        # year: extract four-digit year from producedDate_s (e.g. "2017-06-12" or "2017")
        year: int | None = None
        date_str = doc.get("producedDate_s") or ""
        m = re.search(r"\d{4}", date_str)
        if m:
            try:
                year = int(m.group())
            except ValueError:
                year = None

        doi = normalise_doi(doc.get("doiId_s"))

        # abstract_s is a list; take the first element; may be absent
        abstract_list = doc.get("abstract_s")
        abstract: str | None = None
        if abstract_list:
            abstract = abstract_list[0] or None

        journal = doc.get("journalTitle_s") or None

        # url: HAL record landing page
        url = doc.get("uri_s") or None

        # pdf_url: fileMain_s when deposited
        pdf_url = doc.get("fileMain_s") or None

        is_open_access: bool = bool(doc.get("openAccess_bool", False))

        return Paper(
            title=title,
            authors=authors,
            year=year,
            doi=doi,
            abstract=abstract,
            journal=journal,
            url=url,
            pdf_url=pdf_url,
            source=self.name,
            is_open_access=is_open_access,
        )
