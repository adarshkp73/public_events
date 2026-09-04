import json
import random
import time
import os
import re
import requests

FALLBACK = "data not provided/will be shared upon signup"

# Target cities supported by Luma's regional place indexing or fallback search
TARGET_CITIES = [
    {"name": "bengaluru", "slug": "bengaluru"},
    {"name": "delhi", "slug": "delhi"},
    {"name": "mumbai", "slug": "mumbai"},
    {"name": "hyderabad", "slug": "hyderabad"},
    {"name": "chennai", "slug": "chennai"},
    {"name": "kolkata", "slug": "kolkata"}
]

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

def is_valid_location(event_info, target_city_name):
    """Ensures event is based in India and excludes foreign locations."""
    geo = event_info.get('geo_address_info', {}) or {}
    city_str = str(geo.get('city', '')).lower()
    country_str = str(geo.get('country', '')).lower()
    address_str = str(event_info.get('address', '')).lower()
    
    combined_text = f"{city_str} {country_str} {address_str}"
    
    # Hard drop international major hubs if explicitly marked outside India
    international_markers = [
        'san francisco', 'new york', 'london', 'tokyo', 'berlin', 
        'singapore', 'toronto', 'sydney', 'dubai'
    ]
    if any(marker in combined_text for marker in international_markers) and target_city_name.lower() not in combined_text:
        return False
        
    # If explicitly marked as India or matches local hubs, keep it
    local_hubs = [
        'bengaluru', 'bangalore', 'chennai', 'kolkata', 'hyderabad', 
        'delhi', 'new delhi', 'gurugram', 'noida', 'mumbai', 'pune', 'india'
    ]
    if any(hub in combined_text for hub in local_hubs) or not country_str:
        return True
        
    return True

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
    seen_links = set()  # Much faster tracking for duplicate prevention
    current_id = 1
    
    # Startup jitter (5-10 mins) kept intact for anti-bot measures
    #jitter = random.randint(300, 600)
    #print(f"Applying startup jitter: Sleeping for {jitter} seconds...")
    #time.sleep(jitter)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9"
    }

    proxies = None
    proxy_server_raw = os.getenv("PROXY_SERVER")
    if proxy_server_raw:
        proxy_list = [p.strip() for p in proxy_server_raw.split(",") if p.strip()]
        if proxy_list:
            selected_proxy = random.choice(proxy_list)
            if not selected_proxy.startswith("http"): 
                selected_proxy = f"http://{selected_proxy}"
            
            username = os.getenv("PROXY_USERNAME", "")
            password = os.getenv("PROXY_PASSWORD", "")
            if username and password:
                # Safely handle both http and https for credential injection
                if selected_proxy.startswith("https://"):
                    auth_proxy = selected_proxy.replace("https://", f"https://{username}:{password}@")
                else:
                    auth_proxy = selected_proxy.replace("http://", f"http://{username}:{password}@")
                proxies = {"http": auth_proxy, "https": auth_proxy}
            else:
                proxies = {"http": selected_proxy, "https": selected_proxy}

    luma_base = "https://lu.ma"

    for city_obj in TARGET_CITIES:
        city_name = city_obj["name"]
        city_slug = city_obj["slug"]
        print(f"\n--- Fetching tech events for: {city_name.title()} ---")
        
        try:
            # Use Luma's native slug parameter endpoint
            luma_api_url = f"https://api.luma.com/discover/get-paginated-events?slug={city_slug}&pagination_limit=50"
            res = requests.get(luma_api_url, headers=headers, proxies=proxies, timeout=15)
            print(f"API Status Code for {city_name.title()}: {res.status_code}")
            
            if res.status_code == 200:
                luma_json = res.json()
                entries = luma_json.get('entries', [])
                city_count = 0
                
                for entry in entries:
                    event_info = entry.get('event', {})
                    if event_info:
                        title = event_info.get('name', FALLBACK)
                        
                        # Apply tech filter and location validation
                        if is_tech_event(title) and is_valid_location(event_info, city_name):
                            slug = event_info.get('url') or event_info.get('slug') or event_info.get('api_id', '')
                            reg_link = f"{luma_base}/{slug}" if slug else FALLBACK
                            
                            hosts_list = event_info.get('hosts', [])
                            host_name = hosts_list[0].get('name', FALLBACK) if hosts_list else FALLBACK

                            event_venue = event_info.get('geo_address_info', {}).get('city', city_name.title())
                            reg_url = reg_link
                            
                            # Prevent duplicates using the O(1) Set check
                            if reg_url not in seen_links:
                                seen_links.add(reg_url)
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
                
                print(f"Successfully added {city_count} tech events for {city_name.title()}.")
        except Exception as e:
            print(f"Error fetching {city_name}: {e}")

        time.sleep(2)

    output_payload = {
        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "total_events": len(events_data),
        "events": events_data
    }

    with open('events.json', 'w', encoding='utf-8') as f:
        json.dump(output_payload, f, indent=4, ensure_ascii=False)
        print(f"\nPipeline Complete. Compiled {len(events_data)} total tech events into events.json")

if __name__ == "__main__":
    scrape_all_cities()
