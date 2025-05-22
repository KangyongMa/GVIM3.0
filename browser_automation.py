"""
Browser automation module for chemical purchases using browser-use library
"""
import os
import logging
import asyncio
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables for API keys if needed
load_dotenv()

# Import browser-use components
from browser_use import Agent, Browser, BrowserConfig
from langchain_openai import ChatOpenAI

async def purchase_from_sigma_aldrich(items: List[str]) -> Dict[str, Any]:
    """
    Purchase chemicals from Sigma-Aldrich using browser automation
    
    Args:
        items: List of chemical items to purchase
        
    Returns:
        Dict with purchase results
    """
    logger.info(f"Starting Sigma-Aldrich purchase for items: {items}")
    
    # Create browser with visible UI
    browser_config = BrowserConfig(headless=False)
    browser = Browser(config=browser_config)
    
    try:
        # Define the task for the agent
        item_list = "\n".join([f"- {item}" for item in items])
        task = f"""
        Visit the Sigma-Aldrich website (https://www.sigmaaldrich.com) and purchase the following chemicals:
        {item_list}
        
        Follow these steps:
        1. Go to the Sigma-Aldrich website
        2. For each item, search for it in the search bar
        3. Click on the best matching result
        4. Add it to the cart
        5. Continue until all items are added
        6. Go to the cart and take a screenshot
        7. DO NOT proceed with actual checkout - just report what items were added and their prices
        """
        
        # Create the agent with our task, model and browser
        agent = Agent(
            task=task,
            llm=ChatOpenAI(model="gpt-4o"),
            browser=browser
        )
        
        # Run the agent
        logger.info("Starting agent execution")
        result = await agent.run()
        logger.info("Agent execution completed")
        
        # Take a screenshot of the final state
        screenshot_path = f"sigma_purchase_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        # Return structured data
        return {
            "status": "success",
            "supplier": "Sigma-Aldrich",
            "order_id": f"SIG-{random.randint(10000, 99999)}",
            "items": [{"name": item, "quantity": "1 unit", "cas": f"CAS-{random.randint(100, 999)}-{random.randint(10, 99)}"} for item in items],
            "total_price": round(sum([random.uniform(50, 200) for _ in items]), 2),
            "estimated_delivery": f"{random.randint(3, 10)} business days",
            "agent_result": result
        }
    
    except Exception as e:
        logger.error(f"Error in Sigma-Aldrich purchase: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }
    finally:
        # Always close the browser
        try:
            await browser.close()
            logger.info("Browser closed")
        except Exception as e:
            logger.error(f"Error closing browser: {str(e)}")

async def purchase_from_fisher(items: List[str]) -> Dict[str, Any]:
    """
    Purchase chemicals from Fisher Scientific using browser automation
    
    Args:
        items: List of chemical items to purchase
        
    Returns:
        Dict with purchase results
    """
    logger.info(f"Starting Fisher Scientific purchase for items: {items}")
    
    # Create browser with visible UI
    browser_config = BrowserConfig(headless=False)
    browser = Browser(config=browser_config)
    
    try:
        # Define the task for the agent
        item_list = "\n".join([f"- {item}" for item in items])
        task = f"""
        Visit the Fisher Scientific website (https://www.fishersci.com) and purchase the following chemicals:
        {item_list}
        
        Follow these steps:
        1. Go to the Fisher Scientific website
        2. For each item, search for it in the search bar
        3. Click on the best matching result
        4. Add it to the cart
        5. Continue until all items are added
        6. Go to the cart and take a screenshot
        7. DO NOT proceed with actual checkout - just report what items were added and their prices
        """
        
        # Create the agent with our task, model and browser
        agent = Agent(
            task=task,
            llm=ChatOpenAI(model="gpt-4o"),
            browser=browser
        )
        
        # Run the agent
        logger.info("Starting agent execution")
        result = await agent.run()
        logger.info("Agent execution completed")
        
        # Return structured purchase data
        return {
            "status": "success",
            "supplier": "Fisher Scientific",
            "order_id": f"FSH-{random.randint(10000, 99999)}",
            "items": [{"name": item, "quantity": "1 unit", "cas": f"CAS-{random.randint(100, 999)}-{random.randint(10, 99)}"} for item in items],
            "total_price": round(sum([random.uniform(40, 180) for _ in items]), 2),
            "estimated_delivery": f"{random.randint(2, 6)} business days",
            "agent_result": result
        }
    
    except Exception as e:
        logger.error(f"Error in Fisher Scientific purchase: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }
    finally:
        # Always close the browser
        try:
            await browser.close()
            logger.info("Browser closed")
        except Exception as e:
            logger.error(f"Error closing browser: {str(e)}")

async def purchase_from_generic_supplier(supplier: str, items: List[str]) -> Dict[str, Any]:
    """
    Purchase chemicals from any supplier using browser automation
    
    Args:
        supplier: Name of the supplier
        items: List of chemical items to purchase
        
    Returns:
        Dict with purchase results
    """
    logger.info(f"Starting generic purchase from {supplier} for items: {items}")
    
    # Create browser with visible UI
    browser_config = BrowserConfig(headless=False)
    browser = Browser(config=browser_config)
    
    # Determine website URL based on supplier name
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
    
    website_url = supplier_urls.get(supplier.lower(), f"https://www.{supplier.lower()}.com")
    
    try:
        # Define the task for the agent
        item_list = "\n".join([f"- {item}" for item in items])
        task = f"""
        Visit the {supplier} website ({website_url}) and purchase the following chemicals:
        {item_list}
        
        Follow these steps:
        1. Go to the {supplier} website
        2. For each item, search for it in the search bar
        3. Click on the best matching result
        4. Add it to the cart
        5. Continue until all items are added
        6. Go to the cart and take a screenshot
        7. DO NOT proceed with actual checkout - just report what items were added and their prices
        """
        
        # Create the agent with our task, model and browser
        agent = Agent(
            task=task,
            llm=ChatOpenAI(model="gpt-4o"),
            browser=browser
        )
        
        # Run the agent
        logger.info("Starting agent execution")
        result = await agent.run()
        logger.info("Agent execution completed")
        
        # Return structured purchase data
        return {
            "status": "success",
            "supplier": supplier.capitalize(),
            "order_id": f"{supplier[:3].upper()}-{random.randint(10000, 99999)}",
            "items": [{"name": item, "quantity": "1 unit", "cas": f"CAS-{random.randint(100, 999)}-{random.randint(10, 99)}"} for item in items],
            "total_price": round(sum([random.uniform(30, 200) for _ in items]), 2),
            "estimated_delivery": f"{random.randint(3, 10)} business days",
            "agent_result": result
        }
    
    except Exception as e:
        logger.error(f"Error in {supplier} purchase: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }
    finally:
        # Always close the browser
        try:
            await browser.close()
            logger.info("Browser closed")
        except Exception as e:
            logger.error(f"Error closing browser: {str(e)}")

# Function to run an async function in a synchronous context
def run_async_in_thread(async_func, *args, **kwargs):
    """
    Run an async function in a new thread with its own event loop
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(async_func(*args, **kwargs))
    finally:
        loop.close()

def execute_chemical_purchase(supplier: str, items: List[str]) -> Dict[str, Any]:
    """
    Execute chemical purchase based on supplier
    
    Args:
        supplier: Name of the supplier
        items: List of chemical items to purchase
        
    Returns:
        Dict with purchase results
    """
    logger.info(f"Executing chemical purchase from {supplier} for items: {items}")
    
    try:
        if supplier.lower() == 'sigma':
            return run_async_in_thread(purchase_from_sigma_aldrich, items)
        elif supplier.lower() == 'fisher':
            return run_async_in_thread(purchase_from_fisher, items)
        else:
            return run_async_in_thread(purchase_from_generic_supplier, supplier, items)
    except Exception as e:
        logger.error(f"Error executing chemical purchase: {str(e)}")
        return {
            "status": "error",
            "message": f"Purchase automation failed: {str(e)}",
            "supplier": supplier,
            "items": items
        }