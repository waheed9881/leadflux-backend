"""
LinkedIn Search Service
Finds LinkedIn profiles via Google X-Ray search and scrapes them
"""
import logging
import asyncio
import random
from typing import List, Dict, Any, Optional
from urllib.parse import quote
from playwright.async_api import async_playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError

from app.services.linkedin_playwright_scraper import LinkedInPlaywrightScraper

logger = logging.getLogger(__name__)

class LinkedInSearchService:
    """Service to search and scrape LinkedIn profiles"""
    
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.scraper = LinkedInPlaywrightScraper(headless=headless)
        
    async def search_and_scrape(self, query: str, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search for LinkedIn profiles and scrape them
        
        Args:
            query: Search query (e.g., "software engineer")
            max_results: Maximum number of profiles to scrape
            
        Returns:
            List of scraped profile data
        """
        # 1. Search Google for LinkedIn profiles
        profile_urls = await self.search_profiles(query, max_results)
        
        if not profile_urls:
            logger.warning(f"No LinkedIn profiles found for query: {query}")
            return []
            
        # 2. Scrape each profile
        logger.info(f"Found {len(profile_urls)} profiles, starting scrape...")
        
        results = []
        async with self.scraper as scraper:
            for i, url in enumerate(profile_urls):
                try:
                    logger.info(f"Scraping profile {i+1}/{len(profile_urls)}: {url}")
                    data = await scraper.scrape_profile(url)
                    results.append(data)
                    
                    # Random delay between scrapes
                    if i < len(profile_urls) - 1:
                        await asyncio.sleep(random.uniform(2.0, 5.0))
                except Exception as e:
                    logger.error(f"Error scraping {url}: {e}")
                    results.append({
                        "linkedin_url": url,
                        "error": str(e),
                        "success": False
                    })
                    
        return results

    async def search_profiles(self, query: str, max_results: int = 10) -> List[str]:
        """
        Search Google for LinkedIn profiles using X-Ray search
        
        Args:
            query: Search query
            max_results: Max results to return
            
        Returns:
            List of LinkedIn profile URLs
        """
        # Construct Google X-Ray search query
        # site:linkedin.com/in/ "query"
        search_query = f'site:linkedin.com/in/ "{query}"'
        google_url = f"https://www.google.com/search?q={quote(search_query)}&num={max_results + 5}"
        
        urls = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled']
            )
            
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            page = await context.new_page()
            
            try:
                logger.info(f"Searching Google for: {search_query}")
                await page.goto(google_url, wait_until="networkidle")
                
                # Handle potential consent screen
                try:
                    consent_button = await page.query_selector('button:has-text("Accept all"), button:has-text("I agree")')
                    if consent_button:
                        await consent_button.click()
                        await page.wait_for_load_state("networkidle")
                except:
                    pass
                
                # Extract LinkedIn URLs
                # Google search results are usually in <a> tags with href containing linkedin.com/in/
                links = await page.query_selector_all('a[href*="linkedin.com/in/"]')
                
                for link in links:
                    href = await link.get_attribute("href")
                    if href:
                        # Clean URL (remove Google redirect if present)
                        if "google.com/url?" in href:
                            import urllib.parse
                            parsed = urllib.parse.urlparse(href)
                            q = urllib.parse.parse_qs(parsed.query).get('q')
                            if q:
                                href = q[0]
                        
                        # Ensure it's a direct profile link
                        if "linkedin.com/in/" in href and "/dir/" not in href:
                            # Clean query params
                            href = href.split('?')[0].rstrip('/')
                            if href not in urls:
                                urls.append(href)
                                if len(urls) >= max_results:
                                    break
                                    
                logger.info(f"Found {len(urls)} LinkedIn profile URLs")
                
            except Exception as e:
                logger.error(f"Error searching Google: {e}")
            finally:
                await browser.close()
                
        return urls
