import json
import random
import time
import os
import re
import requests
from urllib.parse import quote

FALLBACK = "data not provided/will be shared upon signup"
TARGET_CITIES = ["bengaluru", "chennai", "kolkata", "hyderabad", "delhi"] 

# Strict tech keyword filter
TECH_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "ml", "deep learning", "genai", "llm",
    "python", "javascript", "typescript", "react", "node", "java", "c++", "golang", "rust",
    "software", "developer", "dev", "code", "coding", "programming", "tech", "technology", 
    "startup", "founder", "hackathon", "web3", "crypto", "blockchain", "cloud", "aws", "azure", 
    "gcp", "devops", "cybersecurity", "security", "data science", "data engineering", "api", 
    "full stack", "frontend", "backend", "saas", "open source", "linux", "git", "database", 
    "sql", "nosql", "product management", "ui/ux", "scaler", "gdg", "google developer"
]

def is_tech_event(event_name):
    if not event_name or event_name == FALLBACK:
        return False
    name_lower = event_name.lower()
    for kw in TECH_KEYWORDS:
        if len(kw) <= 3:
            if re.search(r'\b' + re.escape(kw) + r'\b', name_lower):
                return True
        else:
            if kw in name_lower:
                return True
    return False

def is_in_india(event_info, target_city):
    """Strictly validates that the event is located in India / target city."""
    geo = event_info.get('geo_address_info', {}) or {}
    city_str = str(geo.get('city', '')).lower()
    country_str = str(geo.get('country', '')).lower()
    address_str = str(event_info.get('address', '')).lower()
    name_str = str(event_info.get('name', '')).lower()
    
    # Explicit international exclusion guardrails
    international_markers = ['san francisco', 'sf', 'new york', 'nyc', 'london', 'tokyo', 'berlin', 'singapore', 'usa', 'united states', 'uk', 'germany', 'japan', 'canada', 'toronto', 'sydney', 'australia']
    combined_text = f"{city_str} {country_str} {address_str}"
    
    for marker in international_markers:
        # If an international city/country marker is explicitly in the address metadata, drop it unless our target city matches it
        if marker in combined_text and target_city not in combined_text:
            return False

    # Must match target city or explicitly state India
    if target_city in combined_text or 'india' in combined_text or 'ind' in country_str:
        return True
        
    # Fallback check if venue description mentions India or local tech hubs
    local_hubs = ['bengaluru', 'bangalore', 'chennai', 'kolkata', 'hyderabad', 'delhi', 'new delhi', 'gurugram', 'noida', 'mumbai', 'pune']
    if any(hub in combined_text for hub in local_hubs):
        return True
        
    return False

def sanitize_link(raw_link):
    if not raw_link or raw_link == FALLBACK or raw_link.startswith("#") or "base64" in raw_link:
        return FALLBACK
    if raw_link.startswith("//"):
        return f"https:{raw_link}"
    if raw_link.startswith("http://") or raw_link.startswith("https://"):
        return raw_link
    return raw_link

def scrape_all_cities():
    events_data = []
    current_id = 1
    
    # Startup jitter (5-10 mins)
    jitter = random.randint(300, 600)
    print(f"Applying startup jitter: Sleeping for {jitter} seconds...")
    time.sleep(jitter)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9"
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

    luma_base = "https://lu.ma"

    for city in TARGET_CITIES:
        print(f"\n--- Fetching strict India tech events for: {city.title()} ---")
        try:
            luma_api_url = f"https://api.luma.com/discover/get-paginated-events?location={quote(city.title())}&limit=50"
            res = requests.get(luma_api_url, headers=headers, proxies=proxies, timeout=15)
            
            if res.status_code == 200:
                luma_json = res.json()
                entries = luma_json.get('entries', [])
                city_count = 0
                
                for entry in entries:
                    event_info = entry.get('event', {})
                    if event_info:
                        title = event_info.get('name', FALLBACK)
                        
                        # Apply strict Tech Filter AND Strict India Location Validator
                        if is_tech_event(title) and is_in_india(event_info, city):
                            slug = event_info.get('url') or event_info.get('slug') or event_info.get('api_id', '')
                            reg_link = f"{luma_base}/{slug}" if slug else FALLBACK
                            
                            hosts_list = event_info.get('hosts', [])
                            host_name = hosts_list[0].get('name', FALLBACK) if hosts_list else FALLBACK

                            # Prevent duplicate entries across overlapping city queries
                            event_venue = event_info.get('geo_address_info', {}).get('city', city.title())
                            reg_url = reg_link
                            
                            if not any(e['registration link'] == reg_url for e in events_data):
                                events_data.append({
                                    "id": current_id,
                                    "event name": title,
                                    "host": host_name,
                                    "date and time": event_info.get('start_at', FALLBACK),
                                    "venue": event_venue,
                                    "registration link": reg_url,
                                    "image url": sanitize_link(event_info.get('cover_url'))
                                })
                                current_id += 1
                                city_count += 1
                
                print(f"Successfully added {city_count} verified local events for {city.title()}.")
        except Exception as e:
            print(f"Error fetching {city}: {e}")

        time.sleep(2)

    output_payload = {
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "total_events": len(events_data),
        "events": events_data
    }

    with open('events.json', 'w', encoding='utf-8') as f:
        json.dump(output_payload, f, indent=4, ensure_ascii=False)
        print(f"\nPipeline Complete. Compiled {len(events_data)} verified India tech events into events.json")

if __name__ == "__main__":
    scrape_all_cities()
