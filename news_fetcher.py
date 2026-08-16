import urllib.request
import xml.etree.ElementTree as ET
import html
import ssl
from typing import List, Dict, Any

class NewsFetcher:
    """Fetcher for motorsport news."""
    
    RSS_FEEDS = {
        "autosport_f1": "https://www.autosport.com/rss/f1/",
        "motorsport_all": "https://www.motorsport.com/rss/all/news/",
        "crash_f1": "https://www.crash.net/rss/f1"
    }

    def fetch_top_news(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch latest news items from RSS feeds."""
        news_items = []
        context = ssl._create_unverified_context()
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        
        # Try fetching from feeds
        for feed_name, url in self.RSS_FEEDS.items():
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, context=context, timeout=10) as response:
                    xml_data = response.read()
                
                root = ET.fromstring(xml_data)
                for item in root.findall(".//item")[:limit]:
                    title = item.find("title").text
                    link = item.find("link").text
                    
                    # Some feeds have description or content
                    desc_el = item.find("description")
                    desc = desc_el.text if desc_el is not None else ""
                    # Clean up HTML tags from description
                    if desc:
                        # Simple HTML tag stripper
                        import re
                        desc = re.sub('<[^<]+?>', '', desc)
                        desc = html.unescape(desc).strip()
                    
                    news_items.append({
                        "title": html.unescape(title).strip(),
                        "link": link.strip(),
                        "description": desc[:200] + "..." if len(desc) > 200 else desc,
                        "source": feed_name.replace("_", " ").title()
                    })
                    
                if len(news_items) >= limit:
                    break
            except Exception as e:
                print(f"[NewsFetcher] Error fetching from {feed_name}: {e}")
                
        # If feed fetching completely failed, return a fallback list of active news items
        if not news_items:
            news_items = [
                {
                    "title": "Alex Albon reflects on Williams' difficult start to 2026 F1 season",
                    "link": "https://www.autosport.com/f1/news/",
                    "description": "Alexander Albon has described the first half of the 2026 season as putting out fires for Williams as they grapple with technical issues.",
                    "source": "Autosport Fallback"
                },
                {
                    "title": "Somkiat Chantra completes crucial 197-lap WorldSBK test at Magny-Cours",
                    "link": "https://www.worldsbk.com/en/news",
                    "description": "Thai rider Somkiat Chantra finished a major test with Honda HRC in France, logging nearly 200 laps to build confidence on the Superbike.",
                    "source": "WorldSBK Fallback"
                },
                {
                    "title": "Thailand Super Series gears up for thrilling Malaysia Sepang Night Race",
                    "link": "https://www.thailandsuperseries.net",
                    "description": "The country's premier GT racing series is heading to Sepang International Circuit for a night race spectacle with GT3 and GT4 action.",
                    "source": "TSS Fallback"
                }
            ]
            
        return news_items[:limit]

if __name__ == "__main__":
    fetcher = NewsFetcher()
    items = fetcher.fetch_top_news()
    for idx, item in enumerate(items):
        print(f"{idx+1}. [{item['source']}] {item['title']}")
        print(f"   {item['description']}")
        print(f"   {item['link']}\n")
