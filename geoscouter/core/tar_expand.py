"""Stream remote tar archives and expand member filenames into scrape rows."""

from __future__ import annotations

import io
import logging
import re
import tarfile
from typing import BinaryIO
from urllib.parse import quote, urljoin
from html.parser import HTMLParser

import pandas as pd

from geoscouter.utils.http import ncbi_get

class GeoLinkParser(HTMLParser):
    """Collect links from a GEO webpage."""

    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)

def discover_remote_tar_urls(gse_id: str) -> list[str]:
    """Find TAR archive links in a GEO Series download page."""
    page_url = (
        f"https://www.ncbi.nlm.nih.gov/geo/download/?acc={gse_id}"
    )

    response = ncbi_get(page_url, timeout=30)

    try:
        response.raise_for_status()

        parser = GeoLinkParser()
        parser.feed(response.text)

    finally:
        response.close()

    tar_urls = []

    for link in parser.links:
        full_url = urljoin(page_url, link)
        path = full_url.lower().split("?", 1)[0]

        if "/suppl/" in path and is_tar_filename(path):
            if full_url not in tar_urls:
                tar_urls.append(full_url)

    return tar_urls

logger = logging.getLogger(__name__)

_TAR_FILENAME_RE = re.compile(r"\.(tar\.gz|tgz|tar)$", re.IGNORECASE)
_DEFAULT_MAX_MEMBERS = 5000
_DEFAULT_MAX_SCAN_BYTES = 2 * 1024**3


def is_tar_filename(filename: str) -> bool:
    """True when filename ends with .tar, .tar.gz, or .tgz."""
    if not filename or pd.isna(filename):
        return False
    return bool(_TAR_FILENAME_RE.search(str(filename).strip()))


def normalize_geo_url(url: str) -> str:
    """Convert NCBI FTP URLs to HTTPS for requests."""
    if url.startswith("ftp://ftp.ncbi.nlm.nih.gov/"):
        return "https://" + url[len("ftp://") :]
    return url


def geo_file_download_url(gse_id: str, filename: str) -> str:
    """GEO per-file download URL when SOFT/HTML did not provide a link."""
    return (
        f"https://www.ncbi.nlm.nih.gov/geo/download/"
        f"?acc={gse_id}&format=file&file={quote(filename)}"
    )


def _tarfile_mode_for_filename(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith((".tar.gz", ".tgz")):
        return "r|gz"
    return "r|*"


def list_tar_members_from_stream(
    stream: BinaryIO,
    filename: str = "",
    *,
    max_members: int = _DEFAULT_MAX_MEMBERS,
    max_scan_bytes: int = _DEFAULT_MAX_SCAN_BYTES,
) -> list[str]:
    """List file member names from a tar byte stream (no disk write)."""
    members: list[str] = []
    mode = _tarfile_mode_for_filename(filename)
    label = filename or "archive"
    try:
        with tarfile.open(fileobj=stream, mode=mode) as tf:
            bytes_scanned = 0
            for member in tf:
                bytes_scanned += max(member.size, 0) + 512
                if bytes_scanned > max_scan_bytes:
                    logger.warning("Tar scan byte limit reached for %s", label)
                    break
                if member.isfile():
                    name = member.name.strip()
                    if name:
                        members.append(name)
                if len(members) >= max_members:
                    logger.warning("Tar member limit reached for %s", label)
                    break
    except Exception as e:
        logger.warning("Failed to read tar stream %s: %s", label, e)
        return []
    return members


def list_tar_members_from_bytes(
    data: bytes,
    filename: str = "",
    **kwargs,
) -> list[str]:
    """List file member names from in-memory tar bytes (for tests)."""
    return list_tar_members_from_stream(io.BytesIO(data), filename, **kwargs)


def list_remote_tar_members(
    url: str,
    filename: str = "",
    **kwargs,
) -> list[str]:
    """Fetch a remote tar and return member filenames."""
    url = normalize_geo_url(url)
    label = filename or url.rsplit("/", 1)[-1]
    try:
        logger.warning("Attempting to open TAR: %s", url)
        response = ncbi_get(url, stream=True, timeout=120)
        response.raise_for_status()
        response.raw.decode_content = True
        try:
            return list_tar_members_from_stream(response.raw, label, **kwargs)
        finally:
            response.close()
    except Exception as e:
        logger.warning("Failed to fetch tar %s: %s", label, e)
        return []

def list_nested_tar_members(url: str) -> dict[str, list[str]]:
    """Return filenames contained in nested TAR archives."""
    nested_files: dict[str, list[str]] = {}

    try:
        response = ncbi_get(url, stream=True, timeout=120)
        response.raise_for_status()
        response.raw.decode_content = True

        try:
            with tarfile.open(
                fileobj=response.raw, mode="r|*"
            ) as outer_tar:

                for member in outer_tar:
                    if not member.isfile() or not is_tar_filename(member.name):
                        continue

                    file = outer_tar.extractfile(member)

                    if file is None:
                        continue

                    filenames = []

                    try:
                        with tarfile.open(
                            fileobj=file, mode="r|*"
                        ) as inner_tar:

                            for inner_member in inner_tar:
                                if inner_member.isfile():
                                    filenames.append(inner_member.name)

                    except (tarfile.TarError, OSError, EOFError) as e:
                        logger.warning(
                            "Could not read nested archive %s: %s",
                            member.name,
                            e,
                        )
                        continue

                    finally:
                        file.close()

                    if filenames:
                        nested_files[member.name] = filenames

        finally:
            response.close()

    except Exception as e:
        logger.warning("Could not inspect archive %s: %s", url, e)

    return nested_files

def resolve_tar_url(row: dict, gse_id: str, url_map: dict[str, str]) -> str:
    """Resolve download URL for a supplementary tar row."""
    row_url = row.get("Supplementary URL")
    if row_url:
        return normalize_geo_url(str(row_url))
    fname = str(row.get("Supplementary file", "")).strip()
    if fname in url_map:
        return normalize_geo_url(url_map[fname])
    return geo_file_download_url(gse_id, fname)


def _member_row(base_row: dict, member_name: str) -> dict:
    row = {
        k: v
        for k, v in base_row.items()
        if k
        not in ("Supplementary file", "Size", "File type/resource", "Supplementary URL")
    }
    row["Supplementary file"] = member_name
    row["Size"] = ""
    row["File type/resource"] = member_name
    return row


def _expand_once(
    supp_data: list[dict],
    gse_id: str,
    url_map: dict[str, str],
) -> tuple[list[dict], bool]:
    """Expand tar rows one level; return (new_rows, any_expanded)."""
    result: list[dict] = []
    any_expanded = False

    nested_archive_members: dict[str, list[str]] | None=None

    for row in supp_data:
        fname = str(row.get("Supplementary file", "")).strip()
        if not is_tar_filename(fname):
            result.append(row)
            continue

        url = resolve_tar_url(row, gse_id, url_map)
        members = list_remote_tar_members(url, fname)
        if not members:
            if nested_archive_members is None:
                nested_archive_members = {}

                outer_urls = discover_remote_tar_urls(gse_id)

                for outer_url in outer_urls:
                    found = list_nested_tar_members(outer_url)

                    for nested_name, filenames in found.items():
                        key = nested_name.rsplit("/",1)[-1]
                        nested_archive_members[key] = filenames

            key = fname.rsplit("/",1)[-1]
            members = nested_archive_members.get(key, [])

        if not members:
            logger.warning(
                "Keeping tar row for %s (%s): could not list members",
                gse_id,
                fname,
            )
            result.append(row)
            continue

        any_expanded = True
        logger.info("Expanded %s file %s -> %d member(s)", gse_id, fname, len(members))
        for member in members:
            result.append(_member_row(row, member))

    return result, any_expanded


def expand_tar_rows(
    supp_data: list[dict],
    gse_id: str,
    url_map: dict[str, str],
    *,
    max_depth: int = 1,
) -> list[dict]:
    """
    Replace remaining .tar rows with inner file rows (tar row dropped).

    Recurses up to max_depth when nested tar members have resolvable URLs.
    """
    if not supp_data:
        return supp_data

    rows = supp_data
    for depth in range(max_depth + 1):
        rows, expanded = _expand_once(rows, gse_id, url_map)
        if not expanded:
            break
        if depth == max_depth:
            break

    return rows
