import asyncio
import sys
import nodriver as uc
import re
from fastapi import FastAPI, Response, status
from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager

# Global browser reference
browser_instance: Optional[uc.Browser] = None

def log(msg: str):
    """Clean, professional logging without prose."""
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"\033[90m{timestamp}\033[0m \033[36m[PROD]\033[0m {msg}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manages high-level browser lifecycle on start/stop."""
    global browser_instance
    try:
        browser_instance = await uc.start(
            headless=True,
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
        log(f"CRITICAL: Engine failed to start: {e}")
    yield
    if browser_instance:
        browser_instance.stop()
        log("Engine Shutdown Safely")

app = FastAPI(lifespan=lifespan)

class ScrapeRequest(BaseModel):
    input: str
    desiredCount: int

async def run_scraper(input_val: str, count: int):
    """Linear scraping logic with early returns and minimal nesting."""
    url = input_val if input_val.startswith('http') else f"https://www.pinterest.com/search/pins/?q={input_val}"
    
    # Use new_tab=True to isolate requests and prevent StopIteration
    page = await browser_instance.get(url, new_tab=True)
    image_urls = set()
    
    try:
        log(f"Target: {input_val}")
        await asyncio.sleep(5) # Allow hydration
        
        attempts = 0
        while len(image_urls) < count and attempts < 15:
            content = await page.get_content()
            raw_links = re.findall(r'https://i\.pinimg\.com/[^\s"\'\\]+', content)
            
            initial_len = len(image_urls)
            for link in raw_links:
                if any(res in link for res in ['/236x/', '/474x/', '/736x/']):
                    # Transform to originals and clean strings
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
        # Always close the tab to free memory, keep browser alive
        await page.close()

@app.get("/health")
async def health_check():
    """Endpoint for Render health monitoring and keeping service awake."""
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
        return {
            "success": True, 
            "count": len(data), 
            "data": data
        }
    except Exception as e:
        log(f"Execution Error: {str(e)}")
        return {"success": False, "error": "Internal scraper error"}

if __name__ == "__main__":
    import uvicorn
    # Use standard Render port logic
    uvicorn.run(app, host="0.0.0.0", port=3000, log_level="error")
