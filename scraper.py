import json
import random
import time
import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

FALLBACK = "data not provided/will be shared upon signup"
TARGET_CITY = "bengaluru" 

def sanitize_link(raw_link, base_domain):
    """Ensures registration links are absolute and avoids empty/malformed values."""
    if not raw_link or raw_link == FALLBACK or raw_link.startswith("#"):
        return FALLBACK
    if raw_link.startswith("http://") or raw_link.startswith("https://"):
        return raw_link
    return urljoin(base_domain, raw_link)

def scrape_events(city):
    events_data = []
    current_id = 1
    city_lower = city.lower().strip()
    city_slug = city_lower.replace(" ", "-")
    
    jitter = random.randint(300, 600)
    print(f"Applying {jitter}s jitter to avoid detection...")
    time.sleep(jitter)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "en-US,en;q=0.9"
    }

    proxies = None
    proxy_server_raw = os.getenv("PROXY_SERVER")
    if proxy_server_raw:
        proxy_list = [p.strip() for p in proxy_server_raw.split(",") if p.strip()]
        selected_proxy = random.choice(proxy_list)
        if not selected_proxy.startswith("http"): selected_proxy = f"http://{selected_proxy}"
        
        username = os.getenv("PROXY_USERNAME", "")
        password = os.getenv("PROXY_PASSWORD", "")
        if username and password:
            auth_proxy = selected_proxy.replace("http://", f"http://{username}:{password}@")
            proxies = {"http": auth_proxy, "https": auth_proxy}
        else:
            proxies = {"http": selected_proxy, "https": selected_proxy}

    # ==========================================
    # 1. HEADSTART
    # ==========================================
    try:
        print(f"Fetching Headstart for {city}...")
        hs_base = "https://www.headstart.in"
        hs_url = f"{hs_base}/{city_slug}"
        res = requests.get(hs_url, headers=headers, proxies=proxies, timeout=15)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            scripts = soup.find_all('script', type='application/ld+json')
            found_json = False
            
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if item.get('@type') == 'Event':
                            events_data.append({
                                "id": current_id,
                                "event name": item.get('name', FALLBACK),
                                "host": item.get('organizer', {}).get('name', 'Headstart India'),
                                "date and time": item.get('startDate', FALLBACK),
                                "venue": item.get('location', {}).get('name', city.title()),
                                "registration link": sanitize_link(item.get('url'), hs_base),
                                "image url": sanitize_link(item.get('image'), hs_base)
                            })
                            current_id += 1
                            found_json = True
                except:
                    continue
            
            if not found_json:
                cards = soup.select('a[href*="/events/"]')
                for card in cards:
                    title_elem = card.select_one('h3, h4, .title')
                    if title_elem:
                        link = card.get('href', hs_url)
                        img_elem = card.select_one('img')
                        events_data.append({
                            "id": current_id,
                            "event name": title_elem.get_text(strip=True),
                            "host": "Headstart India",
                            "date and time": FALLBACK,
                            "venue": city.title(),
                            "registration link": sanitize_link(link, hs_base),
                            "image url": sanitize_link(img_elem.get('src') if img_elem else None, hs_base)
                        })
                        current_id += 1
    except Exception as e:
        print(f"Headstart Error: {e}")

    # ==========================================
    # 2. EVENTBRITE
    # ==========================================
    try:
        print(f"Fetching Eventbrite for {city}...")
        eb_base = "https://www.eventbrite.com"
        eb_url = f"{eb_base}/d/india--{city_slug}/all-events/"
        res = requests.get(eb_url, headers=headers, proxies=proxies, timeout=15)
        
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
        print(f"Eventbrite Error: {e}")

    # ==========================================
    # 3. ALLEVENTS
    # ==========================================
    try:
        print(f"Fetching AllEvents for {city}...")
        ae_base = "https://allevents.in"
        ae_url = f"{ae_base}/{city_slug}/all"
        res = requests.get(ae_url, headers=headers, proxies=proxies, timeout=15)
        
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            next_data = soup.find('script', id='__NEXT_DATA__')
            if next_data:
                ae_json = json.loads(next_data.string)
                events = ae_json.get('props', {}).get('pageProps', {}).get('initialState', {}).get('events', [])
                for event in events:
                    events_data.append({
                        "id": current_id,
                        "event name": event.get('eventname', FALLBACK),
                        "host": event.get('organizer', FALLBACK),
                        "date and time": event.get('start_time', FALLBACK),
                        "venue": event.get('venue', {}).get('city', FALLBACK),
                        "registration link": sanitize_link(event.get('event_url'), ae_base),
                        "image url": sanitize_link(event.get('banner_url'), ae_base)
                    })
                    current_id += 1
    except Exception as e:
        print(f"AllEvents Error: {e}")

    # ==========================================
    # 4. LUMA (Fixed URL Parsing)
    # ==========================================
    try:
        print(f"Fetching Luma for {city}...")
        luma_base = "https://lu.ma"
        luma_place_ids = {
            "bengaluru": "discplace-G0tGUVYwl7T17Sb",
            "bangalore": "discplace-G0tGUVYwl7T17Sb",
            "mumbai": "discplace-KzI8u1Jq7O0E2P6",
            "delhi": "discplace-X4c9T5H1F3P4G8M",
            "new-delhi": "discplace-X4c9T5H1F3P4G8M"
        }
        
        place_id = luma_place_ids.get(city_slug)
        if place_id:
            luma_url = f"https://api.lu.ma/discover/get-paginated-events?discover_place_api_id={place_id}&limit=30"
            res = requests.get(luma_url, headers=headers, proxies=proxies, timeout=15)
            if res.status_code == 200:
                for entry in res.json().get('entries', []):
                    event_info = entry.get('event', {})
                    # Prioritize the short slug/url key (e.g., 'r80gqn49') provided by Luma API
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
        else:
            luma_search_url = f"{luma_base}/discover/india/{city_slug}"
            res = requests.get(luma_search_url, headers=headers, proxies=proxies, timeout=15)
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
        print(f"Luma Error: {e}")

    # Wrapped JSON output with timestamp to force clean Git diff updates every day
    output_payload = {
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "total_events": len(events_data),
        "events": events_data
    }

    with open('events.json', 'w', encoding='utf-8') as f:
        json.dump(output_payload, f, indent=4, ensure_ascii=False)
        print(f"Successfully saved {len(events_data)} events for {city.title()} to events.json")

if __name__ == "__main__":
    scrape_events(TARGET_CITY)
