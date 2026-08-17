import asyncio
import json
import re
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# লগিং সেটআপ
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

BASE_URL = "https://dzritv.com/"

async def fetch_stream_links(context, match_url):
    """প্রতিটি ম্যাচের ভেতরে গিয়ে এম্বেডেড স্ট্রিমিং লিঙ্ক ও আইফ্রেম খোঁজা"""
    stream_links = []
    try:
        page = await context.new_page()
        await page.goto(match_url, wait_until="domcontentloaded", timeout=30000)
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')

        # ১. আইফ্রেম (Iframe) সোর্স খোঁজা
        for iframe in soup.find_all('iframe', src=True):
            src = iframe['src']
            if src.startswith('http'):
                stream_links.append({"type": "iframe", "url": src})

        # ২. ডাইরেক্ট .m3u8 (HLS) স্ট্রিমিং লিঙ্ক খোঁজা
        m3u8_matches = re.findall(r'https?://[^\s\'"]+\.m3u8[^\s\'"]*', content)
        for m3u8 in set(m3u8_matches):
            stream_links.append({"type": "hls", "url": m3u8})

        await page.close()
    except Exception as e:
        logging.warning(f"Could not fetch streams from {match_url}: {e}")
    
    return stream_links

async def scrape_dzritv():
    async with async_playwright() as p:
        # Chromium ব্রাউজার হেডলেস মোডে চালু
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        logging.info(f"Loading {BASE_URL}...")
        try:
            await page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
            content = await page.content()
        except Exception as e:
            logging.error(f"Failed to load main page: {e}")
            await browser.close()
            return

        soup = BeautifulSoup(content, 'html.parser')
        matches_data = []

        # ম্যাচ এলিমেন্টগুলো খোঁজা (DZRI TV এর লেআউট অনুযায়ী)
        match_cards = soup.find_all(['article', 'div', 'a'], class_=re.compile(r'match|event|item|card|post', re.I))

        for card in match_cards:
            # শিরোনাম বা টিম নাম
            title_elem = card.find(['h1', 'h2', 'h3', 'h4', 'span']) or card
            title = title_elem.get_text(strip=True) if title_elem else "Unknown Match"

            # ম্যাচের ডাইরেক্ট লিঙ্ক
            match_href = card.get('href') if card.name == 'a' else None
            if not match_href:
                a_tag = card.find('a', href=True)
                match_href = a_tag['href'] if a_tag else None

            if match_href and not match_href.startswith('http'):
                match_href = BASE_URL.rstrip('/') + match_href

            # সময় বা লাইভ স্ট্যাটাস
            time_elem = card.find(class_=re.compile(r'time|date|status|live', re.I))
            match_time = time_elem.get_text(strip=True) if time_elem else "Scheduled"

            # যদি ফিল্টার করে সঠিক ম্যাচের শিরোনাম পাওয়া যায়
            if title and len(title) > 3 and match_href:
                logging.info(f"Processing Match: {title}")
                
                # ম্যাচের ডেডিকেটেড পেজ থেকে লিঙ্ক বের করা
                streams = await fetch_stream_links(context, match_href)

                matches_data.append({
                    "title": title,
                    "match_url": match_href,
                    "time_status": match_time,
                    "streams": streams
                })

        final_output = {
            "last_updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
            "total_matches": len(matches_data),
            "matches": matches_data
        }

        # JSON ফাইলে আউটপুট সেভ
        with open("matches.json", "w", encoding="utf-8") as f:
            json.dump(final_output, f, indent=4, ensure_ascii=False)

        logging.info(f"Successfully scraped {len(matches_data)} matches to matches.json")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_dzritv())
