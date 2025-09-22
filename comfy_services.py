import os
import json
import uuid
import time
import threading
import websocket
import logging
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ComfyUI Global Configuration
COMFYUI_HOST = "localhost"
COMFYUI_PORT = 8188
COMFYUI_URL = f"http://{COMFYUI_HOST}:{COMFYUI_PORT}"
COMFYUI_WS_URL = f"ws://{COMFYUI_HOST}:{COMFYUI_PORT}"

# Global progress map to store progress against prompt_id
progress_map: Dict[str, Dict[str, Any]] = {}

# WebSocket connection variables
ws_connection: Optional[websocket.WebSocket] = None
client_id: str = str(uuid.uuid4())
ws_thread: Optional[threading.Thread] = None
is_connected = False
should_reconnect = True

def get_comfyui_config():
    """Get ComfyUI configuration"""
    return {
        "host": COMFYUI_HOST,
        "port": COMFYUI_PORT,
        "url": COMFYUI_URL,
        "ws_url": COMFYUI_WS_URL
    }

def get_progress(prompt_id: str) -> Optional[Dict[str, Any]]:
    """Get progress for a specific prompt ID"""
    return progress_map.get(prompt_id)

def get_all_progress() -> Dict[str, Dict[str, Any]]:
    """Get all progress data"""
    return progress_map.copy()

def clear_progress(prompt_id: str) -> None:
    """Clear progress for a specific prompt ID"""
    if prompt_id in progress_map:
        del progress_map[prompt_id]
        logger.info(f"Cleared progress for prompt_id: {prompt_id}")

def on_message(ws, message):
    """Handle WebSocket messages"""
    global progress_map
    
    try:
        if isinstance(message, str):
            data = json.loads(message)
            
            if data.get('type') == 'progress':
                progress_data = data.get('data', {})
                prompt_id = progress_data.get('prompt_id')
                max_value = progress_data.get('max', 1)
                node = progress_data.get('node')
                value = progress_data.get('value', 0)
                
                if prompt_id:
                    percentage = (value / max_value) * 100 if max_value > 0 else 0
                    progress_map[prompt_id] = {
                        'progress': percentage,
                        'nodeId': node,
                        'timestamp': int(time.time() * 1000),  # JavaScript-style timestamp
                        'value': value,
                        'max': max_value
                    }
                    logger.debug(f"Updated progress for {prompt_id}: {percentage:.1f}%")
            
            elif data.get('type') == 'executed':
                # Mark as completed when execution is done
                executed_data = data.get('data', {})
                prompt_id = executed_data.get('prompt_id')
                if prompt_id and prompt_id in progress_map:
                    progress_map[prompt_id]['progress'] = 100
                    progress_map[prompt_id]['status'] = 'completed'
                    progress_map[prompt_id]['timestamp'] = int(time.time() * 1000)
                    logger.info(f"Execution completed for prompt_id: {prompt_id}")
            
            elif data.get('type') == 'execution_error':
                # Mark as error when execution fails
                error_data = data.get('data', {})
                prompt_id = error_data.get('prompt_id')
                if prompt_id:
                    progress_map[prompt_id] = {
                        'progress': 0,
                        'status': 'error',
                        'error': error_data.get('exception_message', 'Unknown error'),
                        'timestamp': int(time.time() * 1000)
                    }
                    logger.error(f"Execution error for prompt_id: {prompt_id}")
                    
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse WebSocket message: {e}")
    except Exception as e:
        logger.error(f"Error handling WebSocket message: {e}")

def on_error(ws, error):
    """Handle WebSocket errors"""
    global is_connected
    is_connected = False
    logger.error(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    """Handle WebSocket close"""
    global is_connected
    is_connected = False
    logger.warning(f"WebSocket connection closed: {close_status_code} - {close_msg}")
    
    if should_reconnect:
        logger.info("Attempting to reconnect in 5 seconds...")
        time.sleep(5)
        # start_comfy_services()

def on_open(ws):
    """Handle WebSocket open"""
    global is_connected
    is_connected = True
    logger.info(f"WebSocket connected with client_id: {client_id}")

def connect_websocket():
    """Connect to ComfyUI WebSocket"""
    global ws_connection, client_id
    
    try:
        ws_url = f"{COMFYUI_WS_URL}/ws?clientId={client_id}"
        logger.info(f"Connecting to WebSocket: {ws_url}")
        
        ws_connection = websocket.WebSocketApp(
            ws_url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )
        
        # Run forever with auto-reconnect
        ws_connection.run_forever()
        
    except Exception as e:
        logger.error(f"Failed to connect to WebSocket: {e}")
        if should_reconnect:
            logger.info("Retrying connection in 10 seconds...")
            time.sleep(10)
            connect_websocket()

def start_comfy_services():
    """Start ComfyUI services (WebSocket connection)"""
    global ws_thread, should_reconnect
    
    if ws_thread and ws_thread.is_alive():
        logger.info("ComfyUI services already running")
        return
    
    should_reconnect = True
    logger.info("Starting ComfyUI services...")
    
    # Start WebSocket connection in a separate thread
    ws_thread = threading.Thread(target=connect_websocket, daemon=True)
    ws_thread.start()
    
    logger.info("ComfyUI services started")

def stop_comfy_services():
    """Stop ComfyUI services"""
    global ws_connection, should_reconnect, is_connected
    
    should_reconnect = False
    is_connected = False
    
    if ws_connection:
        ws_connection.close()
        logger.info("ComfyUI services stopped")

def is_service_connected() -> bool:
    """Check if WebSocket service is connected"""
    return is_connected

# Auto-start services when module is imported
# start_comfy_services()