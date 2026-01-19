import asyncio
import sys
import nodriver as uc
import re
from fastapi import FastAPI
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager

browser_instance: Optional[uc.Browser] = None

def log(msg: str):
    print(f"\033[90m{datetime.now().strftime('%H:%M:%S')}\033[0m \033[36m[PROD]\033[0m {msg}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global browser_instance
    # Essential flags for Docker environments
    browser_instance = await uc.start(
        headless=True,
        browser_args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
    )
    log("Production Engine Started")
    yield
    if browser_instance:
        browser_instance.stop()

app = FastAPI(lifespan=lifespan)

class ScrapeRequest(BaseModel):
    input: str
    desiredCount: int

async def run_scraper(input_val: str, count: int):
    url = input_val if input_val.startswith('http') else f"https://www.pinterest.com/search/pins/?q={input_val}"
    
    page = await browser_instance.get(url, new_tab=True)
    image_urls = set()
    
    try:
        log(f"Hydrating: {input_val}")
        await asyncio.sleep(5) 
        
        attempts = 0
        while len(image_urls) < count and attempts < 15:
            content = await page.get_content()
            raw_links = re.findall(r'https://i\.pinimg\.com/[^\s"\'\\]+', content)
            
            initial_len = len(image_urls)
            for link in raw_links:
                if any(res in link for res in ['/236x/', '/474x/', '/736x/']):
                    clean = re.sub(r'\/(236x|474x|564x|736x)\/', '/originals/', link)
                    clean = clean.split('"')[0].split("'")[0].split(' ')[0].replace(')', '')
                    if len(image_urls) < count:
                        image_urls.add(clean)

            log(f"Progress: {len(image_urls)}/{count}")
            
            if len(image_urls) >= count:
                break
                
            if len(image_urls) == initial_len:
                attempts += 1
                await page.scroll_down(700)
                await asyncio.sleep(4)
            else:
                await page.scroll_down(400)
                await asyncio.sleep(2)
            
        return list(image_urls)
    
    finally:
        await page.close()

@app.post("/scrape")
async def scrape_endpoint(request: ScrapeRequest):
    if request.desiredCount <= 0:
        return {"success": False, "error": "Invalid count"}
        
    try:
        data = await run_scraper(request.input, request.desiredCount)
        return {"success": True, "count": len(data), "data": data}
    except Exception as e:
        log(f"Error: {str(e)}")
        return {"success": False, "error": "Execution failed"}
      
