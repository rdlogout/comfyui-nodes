"""
ComfyUI Workflow to API Converter - Custom Node
Adds a global API endpoint for converting workflows to API format
Created by Seth A. Robinson - https://github.com/SethRobinson/comfyui-workflow-to-api-converter-endpoint
"""

import json
import logging
import threading
import time
import asyncio
from aiohttp import web
from .workflow_converter import WorkflowConverter
from .connect_host import start_tunnel_for_comfyui, get_tunnel_url, stop_tunnel, get_tunnel_instance

# Set up logging
logger = logging.getLogger(__name__)

# Import ComfyUI's PromptServer to register our endpoint
try:
    from server import PromptServer
except ImportError as e:
    logger.error("Could not import PromptServer. Make sure this is installed in ComfyUI's custom_nodes directory.")
    raise e

# Register the API endpoint when the custom node is loaded
@PromptServer.instance.routes.post('/workflow/convert')
async def convert_workflow_endpoint(request):
    """
    API endpoint to convert a non-API workflow to API format.
    
    Accepts POST request with JSON body containing the workflow.
    Returns the converted API format workflow.
    """
    try:
        # Get the workflow from the request
        json_data = await request.json()
        
        # Check if this is already in API format
        if WorkflowConverter.is_api_format(json_data):
            # Already in API format, return as-is with nice formatting
            return web.json_response(json_data, dumps=lambda x: json.dumps(x, ensure_ascii=False, indent=2))
        
        # Convert to API format
        if 'nodes' in json_data and 'links' in json_data:
            api_format = WorkflowConverter.convert_to_api(json_data)
            
            # Return just the converted API format with proper Unicode encoding
            # This matches what "Save (API)" produces - just the nodes
            # Format with nice indentation for readability
            return web.json_response(api_format, dumps=lambda x: json.dumps(x, ensure_ascii=False, indent=2))
        else:
            return web.json_response({
                "error": "Invalid workflow format - missing nodes or links"
            }, status=400)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in request: {e}")
        return web.json_response({
            'success': False,
            'error': f'Invalid JSON: {str(e)}'
        }, status=400)
        
    except Exception as e:
        import traceback
        error_msg = f"Error converting workflow: {str(e)}"
        logger.error(error_msg)
        logger.error(f"Traceback: {traceback.format_exc()}")
        return web.json_response({
            "success": False,
            "error": str(e),
            "details": traceback.format_exc()
        }, status=500)

# Also add a GET endpoint that provides information about the converter
@PromptServer.instance.routes.get('/workflow/convert')
async def converter_info(request):
    """
    GET endpoint that provides information about the workflow converter.
    """
    return web.json_response({
        'name': 'ComfyUI Workflow to API Converter',
        'version': '2.0.0',
        'description': 'Converts non-API workflow format to API format for execution',
        'usage': 'POST a workflow JSON to this endpoint to convert it to API format',
        'author': 'Seth A. Robinson',
        'repository': 'https://github.com/SethRobinson/comfyui-workflow-to-api-converter-endpoint'
    })

# Cloudflare Tunnel Status Endpoint
@PromptServer.instance.routes.get('/tunnel/status')
async def tunnel_status_endpoint(request):
    """
    Get the current tunnel status and URL
    """
    try:
        tunnel_url = get_tunnel_url()
        tunnel = get_tunnel_instance()
        
        return web.json_response({
            'success': True,
            'url': tunnel_url,
            'running': tunnel.is_tunnel_running() if tunnel else False,
            'port': tunnel.port if tunnel else None
        })
        
    except Exception as e:
        logger.error(f"Error getting tunnel status: {e}")
        return web.json_response({
            'success': False,
            'error': str(e)
        }, status=500)

# Auto-start Cloudflare tunnel in background
def on_tunnel_url_ready(url):
    """Callback function called when tunnel URL is ready"""
    print(f"\n🌐 ComfyUI is now accessible via Cloudflare tunnel:")
    print(f"🔗 {url}")
    print(f"📡 Tunnel status available at: /tunnel/status\n")

def start_tunnel_background():
    """Start the tunnel in background thread"""
    try:
        # Start tunnel with callback to print URL
        tunnel = start_tunnel_for_comfyui(port=8188, on_url_ready=on_tunnel_url_ready)
        logger.info("Cloudflare tunnel started in background")
    except Exception as e:
        logger.error(f"Failed to start Cloudflare tunnel: {e}")
        print(f"[CloudflareTunnel] Failed to start tunnel: {e}")

# Start tunnel in background thread after a short delay
def delayed_tunnel_start():
    time.sleep(2)  # Wait for ComfyUI to fully initialize
    start_tunnel_background()

tunnel_thread = threading.Thread(target=delayed_tunnel_start, daemon=True)
tunnel_thread.start()

# Log that the endpoints have been registered
logger.info("Workflow to API converter endpoint registered at /workflow/convert")
logger.info("Cloudflare tunnel status endpoint registered at /tunnel/status")
print("[WorkflowToAPIConverter] API endpoint registered at /workflow/convert")
print("[CloudflareTunnel] Starting tunnel in background...")