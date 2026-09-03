import os
import re
import time
import random
import requests
from supabase import create_client, Client

# Use None for SQL NULL compatibility instead of long strings
FALLBACK = None

# Supabase Initialization
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # Use the service_role key

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials in environment variables.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TARGET_CITIES = [
    {"name": "bengaluru", "slug": "bengaluru"},
    {"name": "delhi", "slug": "delhi"},
    {"name": "mumbai", "slug": "mumbai"},
    {"name": "hyderabad", "slug": "hyderabad"},
    {"name": "chennai", "slug": "chennai"},
    {"name": "kolkata", "slug": "kolkata"}
]

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
    if not event_name:
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
    geo = event_info.get('geo_address_info', {}) or {}
    city_str = str(geo.get('city', '')).lower()
    country_str = str(geo.get('country', '')).lower()
    address_str = str(event_info.get('address', '')).lower()
    
    combined_text = f"{city_str} {country_str} {address_str}"
    
    international_markers = ['san francisco', 'new york', 'london', 'tokyo', 'berlin', 'singapore', 'toronto', 'sydney', 'dubai']
    if any(marker in combined_text for marker in international_markers) and target_city_name not in combined_text:
        return False
        
    local_hubs = ['bengaluru', 'bangalore', 'chennai', 'kolkata', 'hyderabad', 'delhi', 'new delhi', 'gurugram', 'noida', 'mumbai', 'pune', 'india']
    if any(hub in combined_text for hub in local_hubs) or not country_str:
        return True
        
    return True

def sanitize_link(raw_link):
    if not raw_link or raw_link.startswith("#") or "base64" in raw_link:
        return FALLBACK
    if raw_link.startswith("//"):
        return f"https:{raw_link}"
    if raw_link.startswith("http://") or raw_link.startswith("https://"):
        return raw_link
    return raw_link

def scrape_all_cities():
    events_data = []
    
    # Removed the 5-10 minute jitter delay to save GitHub Action minutes
    # Added a smaller, reasonable delay (5-15 seconds) to avoid immediate bot detection
    time.sleep(random.randint(5, 15))

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

    for city_obj in TARGET_CITIES:
        city_name = city_obj["name"]
        city_slug = city_obj["slug"]
        print(f"\n--- Fetching tech events for: {city_name.title()} ---")
        
        try:
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
                        title = event_info.get('name')
                        
                        if is_tech_event(title) and is_valid_location(event_info, city_name):
                            slug = event_info.get('url') or event_info.get('slug') or event_info.get('api_id', '')
                            reg_url = f"{luma_base}/{slug}" if slug else None
                            
                            if not reg_url: 
                                continue # Skip if no registration link exists
                            
                            hosts_list = event_info.get('hosts', [])
                            host_name = hosts_list[0].get('name') if hosts_list else FALLBACK

                            event_venue = event_info.get('geo_address_info', {}).get('city', city_name.title())
                            date_time = event_info.get('start_at') # Returns ISO format, perfect for SQL TIMESTAMPTZ
                            
                            # Deduplicate in memory before DB insertion
                            if not any(e['registration_link'] == reg_url for e in events_data):
                                events_data.append({
                                    "event_name": title,
                                    "host_name": host_name,
                                    "date_and_time": date_time,
                                    "venue": event_venue,
                                    "registration_link": reg_url,
                                    "image_url": sanitize_link(event_info.get('cover_url'))
                                })
                                city_count += 1
                
                print(f"Successfully collected {city_count} tech events for {city_name.title()}.")
        except Exception as e:
            print(f"Error fetching {city_name}: {e}")

        # Sleep between city requests to respect rate limits
        time.sleep(3)

    # Database Insertion (Upsert to avoid duplicates based on unique registration_link)
    if events_data:
        try:
            print(f"\nAttempting to push {len(events_data)} events to Supabase...")
            # Upsert inserts new rows and updates existing ones if the unique constraint (registration_link) matches
            response = supabase.table('tech_events').upsert(events_data).execute()
            print(f"Successfully pushed data to Supabase!")
        except Exception as e:
            print(f"Error pushing data to Supabase: {e}")
    else:
        print("No tech events found to push.")

if __name__ == "__main__":
    scrape_all_cities()
