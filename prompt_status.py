import logging
import aiohttp
from aiohttp import web
from server import PromptServer
from .comfy_services import get_progress, get_all_progress, is_service_connected, get_comfyui_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fetch_history_data(prompt_id):
    """Fetch history data from ComfyUI for a specific prompt ID"""
    try:
        config = get_comfyui_config()
        base_url = f"http://{config['host']}:{config['port']}"
        history_url = f"{base_url}/api/history/{prompt_id}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(history_url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get(prompt_id)
                else:
                    logger.error(f"Failed to fetch history for prompt {prompt_id}: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Error fetching history data for prompt {prompt_id}: {e}")
        return None

async def fetch_queue_data():
    """Fetch queue data from ComfyUI to check running and pending prompts"""
    try:
        config = get_comfyui_config()
        base_url = f"http://{config['host']}:{config['port']}"
        queue_url = f"{base_url}/api/queue"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(queue_url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    logger.error(f"Failed to fetch queue data: {response.status}")
                    return None
    except Exception as e:
        logger.error(f"Error fetching queue data: {e}")
        return None

def check_prompt_in_queue(prompt_id, queue_data):
    """Check if a prompt is in the queue (running or pending)"""
    if not queue_data:
        return None
    
    # Check if prompt is currently running
    queue_running = queue_data.get('queue_running', [])
    for item in queue_running:
        if len(item) >= 2 and item[1] == prompt_id:
            return 'running'
    
    # Check if prompt is pending in queue
    queue_pending = queue_data.get('queue_pending', [])
    for item in queue_pending:
        if len(item) >= 2 and item[1] == prompt_id:
            return 'in-queue'
    
    return None

def parse_history_data(history_data):
    """Parse history data to extract start_time, end_time, status, error, and files"""
    if not history_data:
        return {
            'start_time': None,
            'end_time': None,
            'error': None,
            'status': 'failed',
            'files': []
        }
    
    # Extract status information
    status_info = history_data.get('status', {})
    status_str = status_info.get('status_str', 'unknown')
    messages = status_info.get('messages', [])
    
    # Find start and end times from messages
    start_time = None
    end_time = None
    error = None
    
    for message in messages:
        if len(message) >= 2:
            message_type = message[0]
            message_data = message[1]
            
            if message_type == 'execution_start':
                start_time = message_data.get('timestamp')
            elif message_type == 'execution_success':
                end_time = message_data.get('timestamp')
            elif message_type == 'execution_error':
                error = message_data.get('exception_message', 'Unknown error')
    
    # Map status_str to our status format
    status_mapping = {
        'success': 'success',
        'error': 'failed',
        'running': 'running',
        'queued': 'in-queue'
    }
    status = status_mapping.get(status_str, 'failed')
    
    # Extract files from outputs
    files = []
    outputs = history_data.get('outputs', {})
    
    for node_id, node_outputs in outputs.items():
        for output_type, output_list in node_outputs.items():
            if isinstance(output_list, list):
                for output_item in output_list:
                    if isinstance(output_item, dict) and 'filename' in output_item:
                        filename = output_item.get('filename', '')
                        file_type = output_item.get('type', 'temp')
                        subfolder = output_item.get('subfolder', '')
                        
                        # Construct the relative path
                        file_path = f"/api/view?filename={filename}&type={file_type}&subfolder={subfolder}"
                        files.append(file_path)
    
    return {
        'start_time': start_time,
        'end_time': end_time,
        'error': error,
        'status': status,
        'files': files
    }

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
            
            # Fetch history data from ComfyUI
            history_data = await fetch_history_data(prompt_id)
            
            # Fetch queue data to check if prompt is running or in queue
            queue_data = await fetch_queue_data()
            
            # Parse history data to get enhanced information
            parsed_data = parse_history_data(history_data)
            
            # Determine if task is completed based on history data presence
            is_completed = history_data is not None
            
            # Check if prompt is in queue (running or pending)
            queue_status = check_prompt_in_queue(prompt_id, queue_data)
            
            # If no history data, no progress data, and not in queue, the prompt might not exist
            if not is_completed and progress_data is None and queue_status is None:
                return web.json_response({
                    'success': False,
                    'error': f'No data found for prompt_id: {prompt_id}',
                    'prompt_id': prompt_id
                }, status=404)
            
            # Determine status based on available data
            if is_completed:
                # Task is completed, use parsed status from history
                status = parsed_data['status']
            elif queue_status:
                # Task is in queue, use queue status
                status = queue_status
            else:
                # Fallback to unknown status
                status = 'unknown'
            
            response_data = {
                'success': True,
                'prompt_id': prompt_id,
                'start_time': parsed_data['start_time'],
                'end_time': parsed_data['end_time'],
                'error': parsed_data['error'],
                'status': status,
                'files': parsed_data['files'],
                'service_status': 'connected'
            }
            
            # Always include progress data if available
            if progress_data:
                response_data['progress'] = progress_data
            
            return web.json_response(response_data)
            
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