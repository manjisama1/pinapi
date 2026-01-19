import asyncio
import sys
import nodriver as uc
import re
import os
from fastapi import FastAPI, Response, status
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager

browser_instance: Optional[uc.Browser] = None

def log(msg: str):
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"\033[90m{timestamp}\033[0m \033[36m[PROD]\033[0m {msg}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global browser_instance
    try:
        browser_instance = await uc.start(
            headless=True,
            browser_executable_path="/usr/bin/google-chrome",
            browser_args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",
                "--no-zygote",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                "--disable-browser-side-navigation",
                "--disable-features=VizDisplayCompositor",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ]
        )
        log("Production Engine Initialized")
    except Exception as e:
        log(f"CRITICAL: Engine failed: {e}")
    yield
    if browser_instance:
        try:
            browser_instance.stop()
        except:
            pass
        log("Engine Shutdown Safely")

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
        await asyncio.sleep(8) 
        
        attempts = 0
        while len(image_urls) < count and attempts < 10:
            content = await page.get_content()
            
            # Robust regex for escaped and clean Pinterest URLs
            found = re.findall(r'https(?::|\\:)(?://|\\/\\/)i\.pinimg\.com(?:/|\\/)[^\s"\'<>]+', content)
            
            initial_len = len(image_urls)
            for link in found:
                link = link.replace('\\/', '/').replace('\\:', ':')
                if any(res in link for res in ['/236x/', '/474x/', '/564x/', '/736x/']):
                    clean = re.sub(r'\/(236x|474x|564x|736x)\/', '/originals/', link)
                    clean = clean.split('"')[0].split("'")[0].split('\\')[0]
                    if len(image_urls) < count:
                        image_urls.add(clean)

            log(f"Progress: {len(image_urls)}/{count}")
            
            if len(image_urls) >= count:
                break
                
            await page.scroll_down(1500)
            await asyncio.sleep(4)
            
            if len(image_urls) == initial_len:
                attempts += 1
            
        return list(image_urls)
    finally:
        await page.close()

@app.get("/health")
async def health_check():
    return {"status": "ok"} if browser_instance else Response(status_code=503)

@app.post("/scrape")
async def scrape_endpoint(request: ScrapeRequest):
    if not browser_instance:
        return {"success": False, "error": "Engine Not Ready"}
    try:
        data = await run_scraper(request.input, request.desiredCount)
        return {"success": True, "count": len(data), "data": data}
    except Exception as e:
        log(f"Scrape Error: {str(e)}")
        return {"success": False, "error": "Execution failed"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 3000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="error")
