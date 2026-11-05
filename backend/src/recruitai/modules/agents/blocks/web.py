"""read_page: a public https page, as text, with the network closed to everything else."""

import asyncio
import ipaddress
import re
import socket
from html.parser import HTMLParser
from typing import ClassVar
from urllib.parse import urljoin, urlsplit

import httpx

from recruitai.modules.agents.blocks.errors import ToolFailed, UrlNotAllowed

MAX_PAGE_BYTES = 1024 * 1024
MAX_REDIRECTS = 3
FETCH_TIMEOUT_S = 10.0
MAX_TEXT = 20_000


async def _public_address(host: str) -> str:
    """One public IP for the host. A name that resolves to a private, loopback, link-local or
    metadata address is refused, so a page address can never reach our own network."""
    try:
        ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        pass
    else:
        raise UrlNotAllowed()  # a bare IP is never needed for a public page
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            host, 443, type=socket.SOCK_STREAM
        )
    except OSError as exc:
        raise ToolFailed() from exc
    addresses = [ipaddress.ip_address(i[4][0]) for i in infos]
    if not addresses or not all(a.is_global for a in addresses):
        raise UrlNotAllowed()
    return str(addresses[0])


class _Text(HTMLParser):
    SKIP: ClassVar[frozenset[str]] = frozenset(
        {"script", "style", "noscript", "template", "svg", "head"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: object) -> None:
        self._skip += tag in self.SKIP
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        self._skip = max(0, self._skip - (tag in self.SKIP))

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def page_text(markup: str) -> str:
    parser = _Text()
    parser.feed(markup)
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(parser.parts))
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()[:MAX_TEXT]


async def fetch_public_page(url: str) -> str:
    """GET a public https page and return its text. https on 443 only, every hop (redirects too)
    re-checked, the connection pinned to the checked IP, 1 MiB and 10 s at most."""
    async with asyncio.timeout(FETCH_TIMEOUT_S):
        async with httpx.AsyncClient(follow_redirects=False) as client:
            for _ in range(MAX_REDIRECTS + 1):
                parts = urlsplit(url)
                host = parts.hostname or ""
                if (
                    parts.scheme != "https"
                    or parts.port not in (None, 443)
                    or parts.username
                    or not host
                ):
                    raise UrlNotAllowed()
                ip = await _public_address(host)
                pinned = parts._replace(netloc=f"[{ip}]" if ":" in ip else ip).geturl()
                async with (
                    client.stream(
                        "GET",
                        pinned,
                        headers={
                            "Host": host,
                            "User-Agent": "RecruitAI-automation",
                            "Accept-Encoding": "identity",  # no compression: the size cap is real
                        },
                        extensions={"sni_hostname": host},
                    ) as response
                ):
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    if response.status_code >= 400:
                        raise ToolFailed()
                    if (
                        response.headers.get("content-encoding", "identity")
                        != "identity"
                    ):
                        raise ToolFailed()
                    kind = (
                        response.headers.get("content-type", "").split(";")[0].strip()
                    )
                    if kind not in ("text/html", "text/plain", "application/xhtml+xml"):
                        raise ToolFailed()
                    body = b""
                    async for chunk in response.aiter_bytes():
                        body += chunk
                        if len(body) > MAX_PAGE_BYTES:
                            break
                    text = body[:MAX_PAGE_BYTES].decode(
                        response.encoding or "utf-8", errors="replace"
                    )
                    return page_text(text) if kind != "text/plain" else text[:MAX_TEXT]
    raise ToolFailed()  # too many redirects
