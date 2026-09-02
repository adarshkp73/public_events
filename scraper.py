import json
import random
import time
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

FALLBACK = "data not provided/will be shared upon signup"

# Multi-city target array
TARGET_CITIES = ["bengaluru", "chennai", "kolkata", "hyderabad", "delhi"] 

def sanitize_link(raw_link, base_domain):
    """Ensures registration links are absolute and avoids empty/malformed values."""
    if not raw_link or raw_link == FALLBACK or raw_link.startswith("#"):
        return FALLBACK
    if raw_link.startswith("http://") or raw_link.startswith("https://"):
        return raw_link
    return urljoin(base_domain, raw_link)

def scrape_all_cities():
    events_data = []
    current_id = 1
    
    # STARTUP JITTER: Stagger execution by 5 to 10 minutes (300 to 600 seconds)
    #jitter = random.randint(300, 600)
    #print(f"Applying startup jitter: Sleeping for {jitter} seconds to avoid cron footprints...")
    #time.sleep(jitter)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }

    eb_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Upgrade-Insecure-Requests": "1"
    }

    proxies = None
    proxy_server_raw = os.getenv("PROXY_SERVER")
    if proxy_server_raw:
        proxy_list = [p.strip() for p in proxy_server_raw.split(",") if p.strip()]
        selected_proxy = random.choice(proxy_list)
        if not selected_proxy.startswith("http"): 
            selected_proxy = f"http://{selected_proxy}"
        
        username = os.getenv("PROXY_USERNAME", "")
        password = os.getenv("PROXY_PASSWORD", "")
        if username and password:
            auth_proxy = selected_proxy.replace("http://", f"http://{username}:{password}@")
            proxies = {"http": auth_proxy, "https": auth_proxy}
        else:
            proxies = {"http": selected_proxy, "https": selected_proxy}

    for city in TARGET_CITIES:
        city_lower = city.lower().strip()
        city_slug = city_lower.replace(" ", "-")
        print(f"\n--- Scraping events for: {city.title()} ---")

        # ==========================================
        # 1. HEADSTART
        # ==========================================
        try:
            hs_base = "https://www.headstart.in"
            hs_url = f"{hs_base}/{city_slug}"
            res = requests.get(hs_url, headers=headers, proxies=proxies, timeout=15)
            print(f"Headstart Status Code: {res.status_code}")
            
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                cards = soup.select('div.event-card, .card, a[href*="/events/"], .event-item')
                if not cards:
                    cards = soup.find_all('a', href=True)
                    
                for card in cards:
                    href = card.get('href', '')
                    if '/events/' in href or card.name == 'div':
                        title_elem = card.select_one('h2, h3, h4, .title, .event-title')
                        if title_elem or card.name == 'h3':
                            title = title_elem.get_text(strip=True) if title_elem else card.get_text(strip=True)
                            if len(title) > 3:
                                img_elem = card.select_one('img')
                                date_elem = card.select_one('.date, .time, time')
                                venue_elem = card.select_one('.location, .venue')
                                
                                events_data.append({
                                    "id": current_id,
                                    "event name": title,
                                    "host": "Headstart India",
                                    "date and time": date_elem.get_text(strip=True) if date_elem else FALLBACK,
                                    "venue": venue_elem.get_text(strip=True) if venue_elem else city.title(),
                                    "registration link": sanitize_link(href if href else card.get('href'), hs_base),
                                    "image url": sanitize_link(img_elem.get('src') if img_elem else None, hs_base)
                                })
                                current_id += 1
        except Exception as e:
            print(f"Headstart Error ({city}): {e}")

        # ==========================================
        # 2. EVENTBRITE
        # ==========================================
        try:
            eb_base = "https://www.eventbrite.com"
            eb_url = f"{eb_base}/d/india--{city_slug}/all-events/"
            res = requests.get(eb_url, headers=eb_headers, proxies=proxies, timeout=15)
            print(f"Eventbrite Status Code: {res.status_code}")
            
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                script = soup.find('script', string=lambda t: t and 'window.__SERVER_DATA__' in t)
                if script:
                    json_str = script.string.split('window.__SERVER_DATA__ = ')[1].split(';')[0]
                    eb_data = json.loads(json_str)
                    events = eb_data.get('search_data', {}).get('events', {}).get('results', [])
                    for event in events:
                        events_data.append({
                            "id": current_id,
                            "event name": event.get('name', FALLBACK),
                            "host": event.get('primary_organizer', {}).get('name', FALLBACK),
                            "date and time": event.get('start_date', FALLBACK),
                            "venue": event.get('primary_venue', {}).get('name', FALLBACK),
                            "registration link": sanitize_link(event.get('url'), eb_base),
                            "image url": sanitize_link(event.get('image', {}).get('url') if event.get('image') else None, eb_base)
                        })
                        current_id += 1
        except Exception as e:
            print(f"Eventbrite Error ({city}): {e}")

        # ==========================================
        # 3. ALLEVENTS
        # ==========================================
        try:
            ae_base = "https://allevents.in"
            ae_url = f"{ae_base}/{city_slug}/all"
            res = requests.get(ae_url, headers=headers, proxies=proxies, timeout=15)
            print(f"AllEvents Status Code: {res.status_code}")
            
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                event_cards = soup.select('.event-card, li.card, .discover-card, div[data-event-id]')
                if not event_cards:
                    event_cards = soup.select('div.card')

                for card in event_cards:
                    title_elem = card.select_one('h3, h4, .title, .card-title')
                    if title_elem:
                        link_elem = card.select_one('a[href]')
                        img_elem = card.select_one('img')
                        date_elem = card.select_one('.date, .sub-title, time')
                        venue_elem = card.select_one('.venue, .subtitle-location')
                        
                        events_data.append({
                            "id": current_id,
                            "event name": title_elem.get_text(strip=True),
                            "host": FALLBACK,
                            "date and time": date_elem.get_text(strip=True) if date_elem else FALLBACK,
                            "venue": venue_elem.get_text(strip=True) if venue_elem else city.title(),
                            "registration link": sanitize_link(link_elem.get('href') if link_elem else None, ae_base),
                            "image url": sanitize_link(img_elem.get('src') or img_elem.get('data-src') if img_elem else None, ae_base)
                        })
                        current_id += 1
        except Exception as e:
            print(f"AllEvents Error ({city}): {e}")

        # ==========================================
        # 4. LUMA
        # ==========================================
        try:
            luma_base = "https://lu.ma"
            luma_place_ids = {
                "bengaluru": "discplace-G0tGUVYwl7T17Sb",
                "bangalore": "discplace-G0tGUVYwl7T17Sb",
                "mumbai": "discplace-KzI8u1Jq7O0E2P6",
                "delhi": "discplace-X4c9T5H1F3P4G8M",
                "new-delhi": "discplace-X4c9T5H1F3P4G8M",
                "hyderabad": "discplace-hyderabad-placeholder", # Will trigger fallback if invalid
                "chennai": "discplace-chennai-placeholder",
                "kolkata": "discplace-kolkata-placeholder"
            }
            
            place_id = luma_place_ids.get(city_slug)
            # Use universal Luma discovery search page for broad city support
            luma_search_url = f"{luma_base}/discover/india/{city_slug}"
            res = requests.get(luma_search_url, headers=headers, proxies=proxies, timeout=15)
            print(f"Luma Status Code: {res.status_code}")
            
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                next_data = soup.find('script', id='__NEXT_DATA__')
                if next_data:
                    luma_json = json.loads(next_data.string)
                    queries = luma_json.get('props', {}).get('pageProps', {}).get('dehydratedState', {}).get('queries', [])
                    for q in queries:
                        entries = q.get('state', {}).get('data', {}).get('entries', [])
                        for entry in entries:
                            event_info = entry.get('event', {})
                            if event_info:
                                slug = event_info.get('url') or event_info.get('slug') or event_info.get('api_id', '')
                                reg_link = f"{luma_base}/{slug}" if slug else FALLBACK
                                events_data.append({
                                    "id": current_id,
                                    "event name": event_info.get('name', FALLBACK),
                                    "host": event_info.get('hosts', [{'name': FALLBACK}])[0].get('name', FALLBACK),
                                    "date and time": event_info.get('start_at', FALLBACK),
                                    "venue": event_info.get('geo_address_info', {}).get('city', FALLBACK),
                                    "registration link": reg_link,
                                    "image url": sanitize_link(event_info.get('cover_url'), luma_base)
                                })
                                current_id += 1
        except Exception as e:
            print(f"Luma Error ({city}): {e}")

        # Polite delay between city requests
        time.sleep(2)

    # Output clean JSON with timestamp wrapper
    output_payload = {
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "total_events": len(events_data),
        "events": events_data
    }

    with open('events.json', 'w', encoding='utf-8') as f:
        json.dump(output_payload, f, indent=4, ensure_ascii=False)
        print(f"\nSuccessfully compiled a total of {len(events_data)} events across all cities into events.json")

if __name__ == "__main__":
    scrape_all_cities()
