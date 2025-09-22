import logging
from aiohttp import web
from server import PromptServer
from .comfy_services import get_progress, get_all_progress, is_service_connected

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def register_prompt_status_routes():
    """Register the prompt status routes with PromptServer"""
    
    @PromptServer.instance.routes.get('/api/prompt-status')
    async def prompt_status_endpoint(request):
        """
        GET /api/prompt-status?id=<prompt_id>
        Get the status and progress of a specific prompt by ID
        """
        try:
            # Check if WebSocket service is connected
            if not is_service_connected():
                return web.json_response({
                    'success': False,
                    'error': 'ComfyUI WebSocket service is not connected',
                    'service_status': 'disconnected'
                }, status=503)
            
            # Get prompt_id from query parameters
            prompt_id = request.query.get('id')
            if not prompt_id:
                return web.json_response({
                    'success': False,
                    'error': 'Missing required query parameter: id (prompt_id)'
                }, status=400)
            
            # Get progress data for the prompt
            progress_data = get_progress(prompt_id)
            
            if progress_data is None:
                return web.json_response({
                    'success': False,
                    'error': f'No progress data found for prompt_id: {prompt_id}',
                    'prompt_id': prompt_id
                }, status=404)
            
            # Return the progress data
            return web.json_response({
                'success': True,
                'prompt_id': prompt_id,
                'data': progress_data,
                'service_status': 'connected'
            })
            
        except Exception as e:
            logger.error(f"Error getting prompt status: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @PromptServer.instance.routes.get('/api/prompt-status/all')
    async def all_prompt_status_endpoint(request):
        """
        GET /api/prompt-status/all
        Get the status and progress of all prompts
        """
        try:
            # Check if WebSocket service is connected
            if not is_service_connected():
                return web.json_response({
                    'success': False,
                    'error': 'ComfyUI WebSocket service is not connected',
                    'service_status': 'disconnected'
                }, status=503)
            
            # Get all progress data
            all_progress = get_all_progress()
            
            return web.json_response({
                'success': True,
                'data': all_progress,
                'count': len(all_progress),
                'service_status': 'connected'
            })
            
        except Exception as e:
            logger.error(f"Error getting all prompt status: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)
    
    @PromptServer.instance.routes.get('/api/service-status')
    async def service_status_endpoint(request):
        """
        GET /api/service-status
        Get the status of ComfyUI WebSocket service
        """
        try:
            connected = is_service_connected()
            
            return web.json_response({
                'success': True,
                'service_status': 'connected' if connected else 'disconnected',
                'connected': connected
            })
            
        except Exception as e:
            logger.error(f"Error getting service status: {e}")
            return web.json_response({
                'success': False,
                'error': str(e)
            }, status=500)