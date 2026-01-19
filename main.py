import asyncio
import sys
import nodriver as uc
import re
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
        # Explicitly pointing to the binary installed by the Dockerfile
        browser_instance = await uc.start(
            headless=True,
            browser_executable_path="/usr/bin/google-chrome",
            browser_args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-extensions"
            ]
        )
        log("Production Engine Initialized")
    except Exception as e:
        log(f"CRITICAL: Engine failed: {e}")
    yield
    if browser_instance:
        browser_instance.stop()
        log("Engine Shutdown Safely")

app = FastAPI(lifespan=lifespan)

class ScrapeRequest(BaseModel):
    input: str
    desiredCount: int

async def run_scraper(input_val: str, count: int):
    url = input_val if input_val.startswith('http') else f"https://www.pinterest.com/search/pins/?q={input_val}"
    
    # new_tab=True prevents navigation collisions
    page = await browser_instance.get(url, new_tab=True)
    image_urls = set()
    
    try:
        log(f"Target: {input_val}")
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

            if len(image_urls) >= count:
                break
                
            if len(image_urls) == initial_len:
                attempts += 1
                log(f"Buffering... ({len(image_urls)}/{count})")
                await page.scroll_down(700)
                await asyncio.sleep(4)
                continue

            await page.scroll_down(400)
            await asyncio.sleep(2)
            
        log(f"Success: {len(image_urls)} images captured")
        return list(image_urls)
    
    finally:
        await page.close()

@app.get("/health")
async def health_check():
    if browser_instance:
        return {"status": "healthy", "engine": "running"}
    return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

@app.post("/scrape")
async def scrape_endpoint(request: ScrapeRequest):
    if request.desiredCount <= 0:
        return {"success": False, "error": "Count must be positive"}
    if not browser_instance:
        return {"success": False, "error": "Browser engine not ready"}

    try:
        data = await run_scraper(request.input, request.desiredCount)
        return {"success": True, "count": len(data), "data": data}
    except Exception as e:
        log(f"Execution Error: {str(e)}")
        return {"success": False, "error": "Internal scraper error"}

if __name__ == "__main__":
    import uvicorn
    import os
    # Render automatically sets the PORT env
    port = int(os.environ.get("PORT", 3000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="error")
    
