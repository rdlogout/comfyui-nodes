"""
Queue Prompt Route Handler
Handles workflow processing and URL downloading for ComfyUI prompts
"""

import json
import os
import asyncio
import aiohttp
import aiofiles
import uuid
import logging
from pathlib import Path
from urllib.parse import urlparse
from typing import Dict, Any, Set, Optional
from aiohttp import web
from server import PromptServer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
COMFYUI_PATH = os.path.expanduser("~/ComfyUI")  # ComfyUI installation path
DOWNLOAD_DIR = os.path.join(COMFYUI_PATH, "input")  # ComfyUI input directory
MAX_CONCURRENT_DOWNLOADS = 3

def get_comfyui_path() -> str:
    """
    Get the ComfyUI installation path
    """
    return COMFYUI_PATH

async def get_workflow(workflow_input: Any) -> Dict[str, Any]:
    """
    Handle both string and object inputs for workflow processing
    
    Args:
        workflow_input: Either a JSON string or a dictionary object
        
    Returns:
        Processed workflow dictionary
    """
    # Handle both string and object inputs
    if isinstance(workflow_input, str):
        # Parse the workflow string to object
        workflow = json.loads(workflow_input)
    else:
        # Use the object directly
        workflow = workflow_input
    
    # Process the workflow to download and replace URLs
    processed_workflow = await process_workflow_urls(workflow)
    
    return processed_workflow

async def process_workflow_urls(obj: Any) -> Any:
    """
    Process workflow to download URLs and replace them with local filenames
    
    Args:
        obj: The workflow object to process
        
    Returns:
        Processed workflow with URLs replaced by local filenames
    """
    # First pass: collect all URLs that need to be downloaded
    urls_to_download = set()
    collect_urls(obj, urls_to_download)
    
    # Download URLs with small concurrency to avoid memory spikes
    url_map = {}
    if urls_to_download:
        urls = list(urls_to_download)
        max_concurrency = 3
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def download_worker(url: str) -> tuple:
            async with semaphore:
                filename = await download_and_replace_url(url)
                return url, filename
        
        # Download all URLs concurrently with limit
        tasks = [download_worker(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results and handle exceptions
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error downloading URL: {result}")
                continue
            url, filename = result
            url_map[url] = filename
    
    # Second pass: replace URLs with downloaded filenames
    return replace_urls(obj, url_map)

def collect_urls(obj: Any, urls_to_download: Set[str]) -> None:
    """
    Recursively collect URLs from the workflow object
    
    Args:
        obj: Object to search for URLs
        urls_to_download: Set to store found URLs
    """
    if not isinstance(obj, (dict, list)) or obj is None:
        return
    
    if isinstance(obj, list):
        for item in obj:
            collect_urls(item, urls_to_download)
        return
    
    if isinstance(obj, dict):
        for key, value in obj.items():
            if "image" in key.lower():
                logger.debug(f"Found image key: {key}, value: {value}")
            
            if isinstance(value, str) and is_target_url(value):
                urls_to_download.add(value)
            else:
                collect_urls(value, urls_to_download)

def replace_urls(obj: Any, url_map: Dict[str, str]) -> Any:
    """
    Replace URLs in the workflow object with local filenames
    
    Args:
        obj: Object to process
        url_map: Mapping of URLs to local filenames
        
    Returns:
        Processed object with URLs replaced
    """
    if not isinstance(obj, (dict, list)) or obj is None:
        return obj
    
    if isinstance(obj, list):
        return [replace_urls(item, url_map) for item in obj]
    
    if isinstance(obj, dict):
        processed_obj = {}
        for key, value in obj.items():
            if isinstance(value, str) and is_target_url(value):
                filename = url_map.get(value)
                processed_obj[key] = filename if filename else value
                if filename:
                    logger.info(f"Replaced URL {value} with {filename}")
            else:
                processed_obj[key] = replace_urls(value, url_map)
        return processed_obj
    
    return obj

def is_target_url(value: str) -> bool:
    """
    Check if a string is a target URL that should be downloaded
    
    Args:
        value: String to check
        
    Returns:
        True if the string is a target URL, False otherwise
    """
    try:
        parsed_url = urlparse(value)
        return parsed_url.scheme == "https" and parsed_url.hostname == "fussion.studio"
    except Exception:
        return False

async def download_file(url: str, filename: str) -> bool:
    """
    Download a file from URL to the ComfyUI input directory
    """
    try:
        # Ensure download directory exists
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        
        file_path = os.path.join(DOWNLOAD_DIR, filename)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                
                async with aiofiles.open(file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)
        
        return True
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return False

async def download_and_replace_url(url: str) -> str:
    """
    Download a URL and return the local filename
    
    Args:
        url: URL to download
        
    Returns:
        Local filename of the downloaded file
    """
    if not is_target_url(url):
        logger.debug(f"Skipping non-target URL: {url}")
        return url
    
    # Generate unique filename
    original_filename = url.split("/")[-1] or "input"
    file_path = Path(original_filename)
    extension = file_path.suffix
    base_name = file_path.stem
    unique_id = str(uuid.uuid4())[:8]
    unique_filename = f"{base_name}_{unique_id}{extension}"
    
    logger.info(f"Downloading file: {url} -> {unique_filename}")
    
    try:
        # Download file using streaming-friendly method
        await download_file(url, unique_filename)
        logger.info(f"Downloaded file to {unique_filename}")
        return unique_filename
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        return url  # Return original URL if download fails

def register_queue_prompt_routes():
    """Register the queue prompt routes with the PromptServer"""
    
    @PromptServer.instance.routes.post('/api/queue-prompt')
    async def queue_prompt_endpoint(request):
        """
        Handle POST requests to queue a prompt with workflow processing
        """
        try:
            # Read the request body
            body = await request.json()
            
            # Extract prompt from body
            prompt = body.get('prompt')
            if not prompt:
                return web.json_response({
                    'success': False,
                    'error': 'Missing prompt in request body'
                }, status=400)
            
            # Process the workflow
            logger.info("Processing workflow prompt")
            processed_workflow = await get_workflow(prompt)
            
            # Make POST request to ComfyUI API
            logger.info("Sending processed workflow to ComfyUI API")
            comfyui_url = "http://localhost:8188/api/prompt"
            payload = {"prompt": processed_workflow}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(comfyui_url, json=payload) as response:
                    if response.status == 200:
                        comfyui_response = await response.json()
                        logger.info("Successfully queued prompt to ComfyUI")
                        return web.json_response({
                            'success': True,
                            'comfyui_response': comfyui_response,
                            'message': 'Workflow processed and queued successfully'
                        })
                    else:
                        error_text = await response.text()
                        logger.error(f"ComfyUI API error: {response.status} - {error_text}")
                        return web.json_response({
                            'success': False,
                            'error': f'ComfyUI API error: {response.status} - {error_text}',
                            'processed_workflow': processed_workflow
                        }, status=200)
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return web.json_response({
                'success': False,
                'error': f'Invalid JSON in request body: {str(e)}'
            }, status=400)
            
        except Exception as e:
            logger.error(f"Error processing queue prompt: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)