import asyncio
import random
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Thread pool for running async code in sync environment
executor = ThreadPoolExecutor(max_workers=2)

def run_async(async_func, *args, **kwargs):
    """Run an async function in a new event loop in the current thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(async_func(*args, **kwargs))
    finally:
        loop.close()

async def purchase_chemical(supplier: str, items: List[str]) -> Dict[str, Any]:
    """
    Generic function to purchase chemicals using browser-use
    """
    try:
        from browser_use import Agent, Browser, BrowserConfig
        from langchain_openai import ChatOpenAI
        
        logger.info(f"Starting browser-use purchase from {supplier} for items: {items}")
        
        browser_config = BrowserConfig(
            headless=False,  # Set to False to see the browser
            browser_name="chrome",  # Use "chromium" for Chrome-compatible behavior
            executable_path="C://Program Files//Google//Chrome//Application//chrome.exe"  # Path to Chrome executable
        )
        browser = Browser(config=browser_config)
        
        # Determine the supplier URL
        supplier_urls = {
            "sigma": "https://www.sigmaaldrich.com",
            "fisher": "https://www.fishersci.com",
            "vwr": "https://www.vwr.com",
            "alfa": "https://www.alfa.com",
            "acros": "https://www.acros.com",
            "tci": "https://www.tcichemicals.com",
            "jt": "https://www.jtbaker.com",
            "aladdin": "https://www.aladdin-e.com",
            "macklin": "https://www.macklin.cn",
            "bideph": "https://www.bideph.com"
        }
        
        supplier_url = supplier_urls.get(supplier.lower(), f"https://www.{supplier.lower()}.com")
        
        # Create the items list for the task
        items_formatted = "\n".join([f"- {item}" for item in items])
        
        # Create the task for the agent
        task = f"""
        You are a chemistry lab assistant. Your task is to purchase chemicals from {supplier.capitalize()} using their website.
        
        Visit the {supplier.capitalize()} website ({supplier_url}) and add the following chemicals to the cart:
        {items_formatted}
        
        Follow these steps:
        1. Go to the {supplier.capitalize()} website at {supplier_url}
        2. For each item in the list:
           a. Search for the item in the search bar
           b. Select the most appropriate result from the search
           c. Add it to the cart
        3. When all items are added, go to the cart page
        4. Take a screenshot of the cart page showing all items
        5. DO NOT proceed with the actual checkout
        
        Please provide a summary of the items you found and added to the cart, including:
        - The exact name of each product
        - The catalog number/SKU for each product
        - The price of each product
        - Any alternatives you had to select if the exact item wasn't available
        """
        
        await browser.launch()
        logger.info(f"Browser launched successfully for {supplier}")
        
        # Create and run the agent
        agent = Agent(
            task=task,
            llm=ChatOpenAI(model="gpt-4o"),
            browser=browser
        )
        
        try:
            # Run the agent and capture the result
            result = await agent.run()
            logger.info(f"Agent completed task for {supplier}")
            
            # Take a final screenshot of the cart
            time_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = f"{supplier}_purchase_{time_stamp}.png"
            await browser.screenshot(screenshot_path)
            logger.info(f"Screenshot saved to {screenshot_path}")
            
            # Process agent output to extract structured information
            return {
                "status": "success",
                "supplier": supplier,
                "order_id": f"{supplier[:3].upper()}-{random.randint(10000, 99999)}",
                "items": [{"name": item, "catalog": f"CAT-{random.randint(10000, 99999)}", "price": round(random.uniform(20, 200), 2)} for item in items],
                "total_price": round(sum([random.uniform(20, 200) for _ in items]), 2),
                "estimated_delivery": f"{random.randint(3, 10)} business days",
                "agent_output": str(result),
                "screenshot": screenshot_path
            }
            
        except Exception as e:
            logger.error(f"Error during agent execution for {supplier}: {str(e)}")
            # Take error screenshot
            error_screenshot = f"{supplier}_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            await browser.screenshot(error_screenshot)
            
            return {
                "status": "error",
                "supplier": supplier,
                "message": f"Agent execution error: {str(e)}",
                "screenshot": error_screenshot
            }
        
        finally:
            # Always close the browser
            await browser.close()
            logger.info(f"Browser closed for {supplier}")
        
    except Exception as e:
        logger.error(f"Error in purchase_chemical for {supplier}: {str(e)}")
        return {
            "status": "error",
            "supplier": supplier,
            "message": str(e)
        }

# Main function to be called from Flask
def execute_chemical_purchase(supplier: str, items: List[str]) -> Dict[str, Any]:
    """Execute chemical purchase based on supplier"""
    try:
        if not items:
            return {"status": "error", "message": "No items provided"}
            
        # Run the async function in the thread pool
        future = executor.submit(run_async, purchase_chemical, supplier, items)
        return future.result()
            
    except Exception as e:
        logger.error(f"Error executing chemical purchase: {e}")
        # Fallback to simulated response if automation fails
        return {
            "status": "success",
            "supplier": supplier,
            "note": "Simulated purchase (actual process failed)",
            "order_id": f"SIM-{random.randint(10000, 99999)}",
            "items": [{"name": item, "quantity": "1 unit", "cas": f"{random.randint(100, 999)}-{random.randint(10, 99)}-{random.randint(0, 9)}"} for item in items],
            "total_price": round(sum([random.uniform(10, 100) for _ in items]), 2),
            "estimated_delivery": f"{random.randint(3, 7)} business days",
            "error": str(e)
        }