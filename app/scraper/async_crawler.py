"""Asynchronous web crawler"""
import asyncio
import logging
from collections import deque
from typing import AsyncIterator, Set, Tuple
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup
from app.core.config import settings

logger = logging.getLogger(__name__)


class AsyncCrawler:
    """Asynchronous crawler for internal website links"""
    
    def __init__(self, max_pages: int = None, timeout: int = None, concurrency: int = None):
        self.max_pages = max_pages or settings.DEFAULT_MAX_PAGES
        self.timeout = timeout or settings.DEFAULT_TIMEOUT
        self.concurrency = concurrency or settings.DEFAULT_CONCURRENCY
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self, headers: dict) -> httpx.AsyncClient:
        async with self._client_lock:
            if self._client is not None:
                return self._client

            timeout = httpx.Timeout(self.timeout, connect=min(self.timeout, 5.0))
            limits = httpx.Limits(max_connections=max(10, self.concurrency * 10), max_keepalive_connections=20)

            # HTTP/2 is optional in httpx (requires `h2`). Prefer it when available, but fall back safely.
            try:
                self._client = httpx.AsyncClient(
                    timeout=timeout,
                    headers=headers,
                    follow_redirects=True,
                    http2=True,
                    limits=limits,
                )
            except Exception:
                self._client = httpx.AsyncClient(
                    timeout=timeout,
                    headers=headers,
                    follow_redirects=True,
                    limits=limits,
                )
            return self._client

    async def aclose(self) -> None:
        """Close the underlying HTTP client (safe to call multiple times)."""
        async with self._client_lock:
            if self._client is None:
                return
            client = self._client
            self._client = None

        try:
            await client.aclose()
        except Exception:
            pass
    
    async def crawl(self, root_url: str) -> AsyncIterator[Tuple[str, BeautifulSoup]]:
        """Crawl a website starting from root_url"""
        visited: Set[str] = set()
        queue: deque[str] = deque([root_url])
        semaphore = asyncio.Semaphore(self.concurrency)
        
        headers = {
            "User-Agent": settings.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

        try:
            client = await self._get_client(headers=headers)
            while queue and len(visited) < self.max_pages:
                url = queue.popleft()
                
                if url in visited:
                    continue
                
                visited.add(url)
                
                async with semaphore:
                    try:
                        resp = await client.get(url)
                        # Handle 403 Forbidden gracefully
                        if resp.status_code == 403:
                            logger.debug(f"Skipping {url}: 403 Forbidden (site blocked scraping)")
                            continue
                        if resp.status_code == 429:
                            # Simple backoff for rate limiting
                            await asyncio.sleep(1.0)
                            continue
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as e:
                        if e.response.status_code == 403:
                            logger.debug(f"Skipping {url}: 403 Forbidden (site blocked scraping)")
                        continue
                    except httpx.TimeoutException:
                        continue
                    except Exception:
                        continue
                
                content_type = resp.headers.get("Content-Type", "")
                if "text/html" not in content_type:
                    continue
                
                try:
                    soup = BeautifulSoup(resp.text, "html.parser")
                except Exception:
                    continue
                
                yield url, soup
                
                # Discover new internal links
                for a in soup.select("a[href]"):
                    href = a.get("href")
                    if not href:
                        continue
                    
                    absolute = urljoin(url, href)
                    # Remove fragments
                    absolute = absolute.split("#")[0]
                    
                    if self._same_domain(root_url, absolute) and absolute not in visited:
                        if absolute not in queue and len(visited) + len(queue) < self.max_pages:
                            queue.append(absolute)
        finally:
            # Client is shared/reused; do not close per crawl.
            pass
    
    def _same_domain(self, root: str, url: str) -> bool:
        """Check if URL is from the same domain as root"""
        try:
            root_domain = urlparse(root).netloc
            url_domain = urlparse(url).netloc
            # Handle www. variations
            root_domain = root_domain.replace("www.", "")
            url_domain = url_domain.replace("www.", "")
            return root_domain == url_domain
        except Exception:
            return False

