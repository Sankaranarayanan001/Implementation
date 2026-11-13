import html
import re
from urllib.parse import unquote, urljoin, urlparse

import requests
from ddgs import DDGS  # type: ignore
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("search-server")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
BAD_END = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")
BAD_PARTS = ("sentry", "example.", "yourdomain", "wixpress", "domain.com", "email.com")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; lead-finder/1.0)"}
CONTACT_PATHS = ["", "/contact", "/contact-us", "/contact-us/", "/about", "/about-us"]


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web for a query and return top results"""
    try:
        results = DDGS().text(query, max_results=max_results)
        items = [
            {"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")}
            for r in results
        ]
        return {"query": query, "results": items}
    except Exception as e:
        return {"query": query, "error": str(e)}


def _extract(text: str) -> set:
    text = unquote(html.unescape(text))
    text = re.sub(r"\s*[\[\(]\s*at\s*[\]\)]\s*", "@", text, flags=re.I)
    text = re.sub(r"\s*[\[\(]\s*dot\s*[\]\)]\s*", ".", text, flags=re.I)
    found = set()
    for e in EMAIL_RE.findall(text):
        e = e.lower().strip(".")
        if e.endswith(BAD_END) or any(b in e for b in BAD_PARTS):
            continue
        found.add(e)
    return found


LINK_RE = re.compile(r'href=["\']([^"\'#]+)', re.I)
PRIORITY = re.compile(r"contact|touch|enquir|reach|about|team|career", re.I)
SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".pdf", ".zip", ".css", ".js", ".webp")


@mcp.tool()
def list_site_pages(url: str) -> dict:
    """List the internal pages of a website (from sitemap.xml and homepage links). Contact-like pages come first."""
    if not url.startswith("http"):
        url = "https://" + url
    host = urlparse(url).netloc
    pages = {url.rstrip("/")}

    # 1) sitemap.xml
    try:
        r = requests.get(urljoin(url, "/sitemap.xml"), headers=HEADERS, timeout=8)
        if r.ok:
            for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text):
                if not loc.endswith(".xml"):
                    pages.add(loc.rstrip("/"))
    except Exception:
        pass

    # 2) links on the homepage
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        for href in LINK_RE.findall(r.text):
            full = urljoin(url, href).split("?")[0].rstrip("/")
            if urlparse(full).netloc == host and not full.lower().endswith(SKIP_EXT):
                pages.add(full)
    except Exception as e:
        return {"url": url, "error": str(e), "pages": []}

    ordered = sorted(pages, key=lambda p: not PRIORITY.search(p))
    return {"url": url, "total_pages": len(ordered), "pages": ordered[:40]}


@mcp.tool()
def scan_page_for_emails(url: str) -> dict:
    """Fetch ONE page and return any email addresses found on it"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        return {"url": url, "emails": sorted(_extract(r.text))[:10]}
    except Exception as e:
        return {"url": url, "emails": [], "error": str(e)}

if __name__ == "__main__":
    mcp.run(transport="stdio")