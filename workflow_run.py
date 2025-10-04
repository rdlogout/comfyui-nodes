"""
Workflow Run Endpoint Handler
Handles fetching workflow items from backend and processing them through ComfyUI
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from aiohttp import web
from server import PromptServer

# Import from existing modules
from .helper.request_function import get_data_async, post_data_async
from .helper.queue_prompt import queue_prompt

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



async def process_workflow_items(workflow_items: list) -> Dict[str, Any]:
    """
    Process a list of workflow items
    
    Args:
        workflow_items: List of workflow items with 'id' and 'prompt' keys
        
    Returns:
        Summary of processing results
    """
    results = {
        'total': len(workflow_items),
        'processed': 0,
        'queued': 0,
        'failed': 0,
        'skipped': 0,
        'errors': []
    }
    
    for item in workflow_items:
        try:
            item_id = item.get('id')
            prompt = item.get('prompt')
            
            if not item_id:
                results['errors'].append('Missing item ID')
                results['failed'] += 1
                continue
            
            if not prompt:
                results['errors'].append(f'Missing prompt for item {item_id}')
                results['failed'] += 1
                continue
             
            # Queue the workflow using the new helper function
            queue_result = await queue_prompt(prompt, item_id)
            results['processed'] += 1
            
            if queue_result['success']:
                results['queued'] += 1
                logger.info(f"Successfully queued workflow item {item_id}")
            else:
                results['failed'] += 1
                results['errors'].append(f"Failed to queue item {item_id}: {queue_result.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Error processing workflow item: {e}")
            results['failed'] += 1
            results['errors'].append(str(e))
    
    return results

def register_workflow_run_routes():
    """Register the workflow run routes with the PromptServer"""
    
    @PromptServer.instance.routes.get('/api/workflow-run')
    @PromptServer.instance.routes.post('/api/workflow-run')
    async def workflow_run_endpoint(request):
        """
        Handle POST requests to process workflow items from backend
        """
        try:
            logger.info("Received workflow run request")
            
            # Fetch workflow items from backend
            workflow_items = await get_data_async('api/machine/workflow-run')
            
            if not workflow_items:
                logger.error("Failed to fetch workflow items from backend")
                return web.json_response({
                    'success': False,
                    'error': 'Failed to fetch workflow items from backend'
                }, status=500)
            
            if not isinstance(workflow_items, list):
                logger.error("Invalid workflow items format from backend")
                return web.json_response({
                    'success': False,
                    'error': 'Invalid workflow items format from backend'
                }, status=500)
            
            logger.info(f"Fetched {len(workflow_items)} workflow items from backend")
            
            # Process workflow items
            results = await process_workflow_items(workflow_items)
            
            logger.info(f"Workflow processing completed: {results}")
            
            return web.json_response({
                'success': True,
                'results': results,
                'message': f'Processed {results["processed"]} workflow items'
            })
            
        except Exception as e:
            logger.error(f"Error in workflow run endpoint: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    