import json
import random
import time
import os
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from playwright_stealth import stealth_sync 

FALLBACK = "data not provided/will be shared upon signup"

def parse_json_ld(soup):
    """Extracts structured event data embedded for SEO."""
    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if item.get('@type') == 'Event': 
                        return item
            elif data.get('@type') == 'Event':
                return data
        except (json.JSONDecodeError, TypeError):
            continue
    return None

def extract_safe(element, selector, attr=None):
    """Safely extracts text or attributes, returning the fallback if missing."""
    if not element: 
        return FALLBACK
    found = element.select_one(selector)
    if not found: 
        return FALLBACK
    return found.get(attr, FALLBACK).strip() if attr else found.get_text(strip=True) or FALLBACK

def scrape_daily_events():
    events_data = []
    current_id = 1
    
    sources = [
        {"url": "https://www.headstart.in/", "platform": "headstart"},
        {"url": "https://allevents.in/", "platform": "allevents"},
        {"url": "https://www.eventbrite.com/", "platform": "eventbrite"},
        {"url": "https://luma.com/home?locale=en-IN", "platform": "luma"}
    ]

    # Anti-bot: Stagger execution by 5 to 10 minutes (300 to 600 seconds)
    jitter = random.randint(300, 600)
    print(f"Jitter applied: Sleeping for {jitter} seconds to avoid exact cron footprints...")
    time.sleep(jitter)

    # Build proxy configuration if environment variables exist
    proxy_config = None
    proxy_server_raw = os.getenv("PROXY_SERVER")
    
    if proxy_server_raw:
        # Split by comma and pick one proxy randomly per run
        proxy_list = [p.strip() for p in proxy_server_raw.split(",") if p.strip()]
        selected_proxy = random.choice(proxy_list)
        
        # Auto-fix missing http:// prefix if necessary
        if not selected_proxy.startswith("http://") and not selected_proxy.startswith("https://"):
            selected_proxy = f"http://{selected_proxy}"
            
        proxy_config = {
            "server": selected_proxy,
            "username": os.getenv("PROXY_USERNAME", ""),
            "password": os.getenv("PROXY_PASSWORD", "")
        }
        print(f"Proxy active: Using {selected_proxy} (selected from pool of {len(proxy_list)})")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        ) 
        
        context_args = {
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "viewport": {'width': 1920, 'height': 1080}
        }
        
        # Inject proxy if available
        if proxy_config:
            context_args["proxy"] = proxy_config

        context = browser.new_context(**context_args)
        page = context.new_page()
        stealth_sync(page) 

        for source in sources:
            try:
                print(f"Scraping {source['url']}...")
                page.goto(source["url"], wait_until="domcontentloaded", timeout=60000)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(3000)
                
                soup = BeautifulSoup(page.content(), 'html.parser')
                schema_data = parse_json_ld(soup)
                
                if schema_data:
                    # Handle varying schema data types safely
                    organizer = schema_data.get('organizer', {})
                    host_name = organizer.get('name', FALLBACK) if isinstance(organizer, dict) else (organizer or FALLBACK)
                    
                    location = schema_data.get('location', {})
                    venue_name = location.get('name', FALLBACK) if isinstance(location, dict) else (location or FALLBACK)
                    
                    event = {
                        "id": current_id,
                        "event name": schema_data.get('name', FALLBACK),
                        "host": host_name,
                        "date and time": schema_data.get('startDate', FALLBACK),
                        "venue": venue_name,
                        "registration link": schema_data.get('url', source["url"]),
                        "image url": schema_data.get('image', FALLBACK)
                    }
                    if isinstance(event["image url"], list) and len(event["image url"]) > 0:
                        event["image url"] = event["image url"][0]
                    
                    events_data.append(event)
                    current_id += 1
                else:
                    cards = soup.select('.eds-event-card-content, .event-card, .item')
                    for card in cards:
                        event = {
                            "id": current_id,
                            "event name": extract_safe(card, 'h2, h3, .eds-event-card-content__title'),
                            "host": extract_safe(card, '.host, .eds-event-card-content__sub-title'),
                            "date and time": extract_safe(card, '.date, .eds-event-card-content__sub-title'),
                            "venue": extract_safe(card, '.location, .card-text--truncated__one'),
                            "registration link": extract_safe(card, 'a', attr='href'),
                            "image url": extract_safe(card, 'img', attr='src')
                        }
                        events_data.append(event)
                        current_id += 1
                        
            except Exception as e:
                print(f"Scrape failed for {source['url']}: {str(e)}")

        browser.close()

    with open('events.json', 'w', encoding='utf-8') as f:
        json.dump(events_data, f, indent=4, ensure_ascii=False)
        print(f"Successfully saved {len(events_data)} events to events.json")

if __name__ == "__main__":
    scrape_daily_events()
