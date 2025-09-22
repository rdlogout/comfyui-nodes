"""
ComfyUI Cloudflare Tunnel Host Connector
Automatically creates a Cloudflare tunnel to expose ComfyUI to the internet
"""

import subprocess
import threading
import time
import re
import logging
import os
import signal
import atexit
import platform
import psutil
import json
from typing import Optional, Callable, Dict, Any
from .helper.request_function import post_data

# Set up logging
logger = logging.getLogger(__name__)

def get_system_info() -> Dict[str, Any]:
    """
    Collect comprehensive system information including RAM, CPU, disk, and GPU
    
    Returns:
        Dict containing system information
    """
    try:
        system_info = {
            'platform': {
                'system': platform.system(),
                'release': platform.release(),
                'version': platform.version(),
                'machine': platform.machine(),
                'processor': platform.processor(),
                'architecture': platform.architecture()[0]
            },
            'cpu': {
                'physical_cores': psutil.cpu_count(logical=False),
                'logical_cores': psutil.cpu_count(logical=True),
                'max_frequency': psutil.cpu_freq().max if psutil.cpu_freq() else None,
                'current_frequency': psutil.cpu_freq().current if psutil.cpu_freq() else None,
                'usage_percent': psutil.cpu_percent(interval=1)
            },
            'memory': {
                'total': psutil.virtual_memory().total,
                'available': psutil.virtual_memory().available,
                'used': psutil.virtual_memory().used,
                'percentage': psutil.virtual_memory().percent,
                'total_gb': round(psutil.virtual_memory().total / (1024**3), 2),
                'available_gb': round(psutil.virtual_memory().available / (1024**3), 2)
            },
            'disk': {},
            'gpu': []
        }
        
        # Get disk information for all mounted drives
        partitions = psutil.disk_partitions()
        for partition in partitions:
            try:
                partition_usage = psutil.disk_usage(partition.mountpoint)
                system_info['disk'][partition.device] = {
                    'mountpoint': partition.mountpoint,
                    'file_system': partition.fstype,
                    'total': partition_usage.total,
                    'used': partition_usage.used,
                    'free': partition_usage.free,
                    'percentage': round((partition_usage.used / partition_usage.total) * 100, 2),
                    'total_gb': round(partition_usage.total / (1024**3), 2),
                    'free_gb': round(partition_usage.free / (1024**3), 2)
                }
            except PermissionError:
                # Skip drives that can't be accessed
                continue
        
        # Try to get GPU information
        system_info['gpu'] = get_gpu_info()
        
        return system_info
        
    except Exception as e:
        logger.error(f"Error collecting system information: {e}")
        return {
            'error': str(e),
            'platform': {'system': platform.system()},
            'cpu': {'cores': 'unknown'},
            'memory': {'total': 'unknown'},
            'disk': {},
            'gpu': []
        }

def get_gpu_info() -> list:
    """
    Attempt to get GPU information using various methods
    
    Returns:
        List of GPU information dictionaries
    """
    gpu_info = []
    
    try:
        # Try nvidia-smi for NVIDIA GPUs
        result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu', 
                               '--format=csv,noheader,nounits'], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            for i, line in enumerate(lines):
                if line.strip():
                    parts = [part.strip() for part in line.split(',')]
                    if len(parts) >= 5:
                        gpu_info.append({
                            'id': i,
                            'name': parts[0],
                            'memory_total_mb': int(parts[1]) if parts[1].isdigit() else 0,
                            'memory_used_mb': int(parts[2]) if parts[2].isdigit() else 0,
                            'memory_free_mb': int(parts[3]) if parts[3].isdigit() else 0,
                            'utilization_percent': int(parts[4]) if parts[4].isdigit() else 0,
                            'type': 'NVIDIA'
                        })
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
        pass
    
    # If no NVIDIA GPUs found, try to detect other GPUs
    if not gpu_info:
        try:
            # Try to get basic GPU info on macOS
            if platform.system() == 'Darwin':
                result = subprocess.run(['system_profiler', 'SPDisplaysDataType'], 
                                      capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    # Parse macOS system profiler output for GPU info
                    lines = result.stdout.split('\n')
                    current_gpu = {}
                    for line in lines:
                        line = line.strip()
                        if 'Chipset Model:' in line:
                            current_gpu['name'] = line.split(':', 1)[1].strip()
                            current_gpu['type'] = 'Integrated' if 'Intel' in current_gpu['name'] else 'Discrete'
                        elif 'VRAM (Total):' in line or 'VRAM (Dynamic, Max):' in line:
                            vram_str = line.split(':', 1)[1].strip()
                            # Extract memory size (e.g., "8 GB" -> 8192)
                            if 'GB' in vram_str:
                                try:
                                    gb_amount = float(vram_str.split('GB')[0].strip())
                                    current_gpu['memory_total_mb'] = int(gb_amount * 1024)
                                except:
                                    pass
                            elif 'MB' in vram_str:
                                try:
                                    mb_amount = float(vram_str.split('MB')[0].strip())
                                    current_gpu['memory_total_mb'] = int(mb_amount)
                                except:
                                    pass
                        elif line.startswith('Displays:') and current_gpu:
                            # End of current GPU section
                            if 'name' in current_gpu:
                                gpu_info.append({
                                    'id': len(gpu_info),
                                    'name': current_gpu.get('name', 'Unknown GPU'),
                                    'memory_total_mb': current_gpu.get('memory_total_mb', 0),
                                    'memory_used_mb': 0,  # Can't get this easily on macOS
                                    'memory_free_mb': current_gpu.get('memory_total_mb', 0),
                                    'utilization_percent': 0,  # Can't get this easily on macOS
                                    'type': current_gpu.get('type', 'Unknown')
                                })
                            current_gpu = {}
                    
                    # Add the last GPU if it exists
                    if current_gpu and 'name' in current_gpu:
                        gpu_info.append({
                            'id': len(gpu_info),
                            'name': current_gpu.get('name', 'Unknown GPU'),
                            'memory_total_mb': current_gpu.get('memory_total_mb', 0),
                            'memory_used_mb': 0,
                            'memory_free_mb': current_gpu.get('memory_total_mb', 0),
                            'utilization_percent': 0,
                            'type': current_gpu.get('type', 'Unknown')
                        })
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError):
            pass
    
    # If still no GPU info, add a placeholder
    if not gpu_info:
        gpu_info.append({
            'id': 0,
            'name': 'No GPU detected or unable to query',
            'memory_total_mb': 0,
            'memory_used_mb': 0,
            'memory_free_mb': 0,
            'utilization_percent': 0,
            'type': 'Unknown'
        })
    
    return gpu_info

def format_system_info_for_db(system_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format system information to match database schema
    
    Args:
        system_info: Raw system information from get_system_info()
        
    Returns:
        Dict with keys: gpu, vram, cpu, ram, total_disk, available_disk
    """
    try:
        # Extract GPU information
        gpu_name = "Unknown"
        vram_mb = 0
        
        if system_info.get('gpu') and len(system_info['gpu']) > 0:
            primary_gpu = system_info['gpu'][0]  # Use first GPU
            gpu_name = primary_gpu.get('name', 'Unknown')
            vram_mb = primary_gpu.get('memory_total_mb', 0)
        
        # Extract CPU information
        cpu_info = system_info.get('cpu', {})
        cpu_name = f"{cpu_info.get('physical_cores', 'Unknown')} cores"
        if system_info.get('platform', {}).get('processor'):
            cpu_name = system_info['platform']['processor']
        
        # Extract RAM information (convert to GB)
        memory_info = system_info.get('memory', {})
        ram_gb = memory_info.get('total_gb', 0)
        
        # Extract disk information (sum all disks)
        disk_info = system_info.get('disk', {})
        total_disk_gb = 0
        available_disk_gb = 0
        
        for device, info in disk_info.items():
            if isinstance(info, dict):
                total_disk_gb += info.get('total_gb', 0)
                available_disk_gb += info.get('free_gb', 0)
        
        return {
            "gpu": gpu_name,
            "vram": float(vram_mb / 1024),  # Convert MB to GB
            "cpu": cpu_name,
            "ram": float(ram_gb),
            "total_disk": float(total_disk_gb),
            "available_disk": float(available_disk_gb)
        }
        
    except Exception as e:
        logger.error(f"Error formatting system info for database: {e}")
        return {
            "gpu": "Error collecting GPU info",
            "vram": 0.0,
            "cpu": "Error collecting CPU info", 
            "ram": 0.0,
            "total_disk": 0.0,
            "available_disk": 0.0
        }

def get_connect_data(url: str) -> Dict[str, Any]:
    """
    Collect and format system information for sending to the server
    
    Args:
        url: The tunnel URL endpoint
        
    Returns:
        Dict containing formatted connect data
    """
    # Collect system information
    raw_system_info = get_system_info()
    
    # Format system info for database schema
    formatted_system_info = format_system_info_for_db(raw_system_info)
    
    # Prepare data to send to server (flattened structure matching DB schema)
    connect_data = {
        "endpoint": url,
        "gpu": formatted_system_info["gpu"],
        "vram": formatted_system_info["vram"],
        "cpu": formatted_system_info["cpu"],
        "ram": formatted_system_info["ram"],
        "total_disk": formatted_system_info["total_disk"],
        "available_disk": formatted_system_info["available_disk"],
        "timestamp": time.time()
    }
    
    return connect_data

class CloudflareTunnel:
    """Manages Cloudflare tunnel connection for ComfyUI"""
    
    def __init__(self, port: int = 8188, on_url_ready: Optional[Callable[[str], None]] = None):
        """
        Initialize the Cloudflare tunnel manager
        
        Args:
            port: The local port where ComfyUI is running (default: 8188)
            on_url_ready: Callback function to call when tunnel URL is ready
        """
        self.port = port
        self.process = None
        self.tunnel_url = None
        self.is_running = False
        self.on_url_ready = on_url_ready
        self._stop_event = threading.Event()
        self._heartbeat_timer = None
        
        # Register cleanup on exit
        atexit.register(self.stop_tunnel)
    
    def start_tunnel(self) -> bool:
        """
        Start the Cloudflare tunnel in a background thread
        
        Returns:
            bool: True if tunnel started successfully, False otherwise
        """
        if self.is_running:
            logger.info("Tunnel is already running")
            return True
        
        # Check if cloudflared is available
        if not self._check_cloudflared():
            logger.error("cloudflared is not installed or not in PATH")
            return False
        
        # Start tunnel in background thread
        tunnel_thread = threading.Thread(target=self._run_tunnel, daemon=True)
        tunnel_thread.start()
        
        # Wait a bit for the tunnel to establish
        time.sleep(3)
        
        return self.is_running
    
    def _check_cloudflared(self) -> bool:
        """Check if cloudflared is installed and available"""
        try:
            result = subprocess.run(['cloudflared', '--version'], 
                                  capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False
    
    def _run_tunnel(self):
        """Run the cloudflared tunnel process"""
        try:
            local_url = f"http://localhost:{self.port}"
            cmd = ['cloudflared', 'tunnel', '--url', local_url]
            
            logger.info(f"Starting Cloudflare tunnel for {local_url}")
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            self.is_running = True
            
            # Monitor output for the tunnel URL
            for line in iter(self.process.stdout.readline, ''):
                if self._stop_event.is_set():
                    break
                    
                line = line.strip()
                if line:
                    logger.debug(f"Cloudflared output: {line}")
                    
                    # Look for the tunnel URL in the output
                    url_match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                    if url_match and not self.tunnel_url:
                        self.tunnel_url = url_match.group(0)
                        logger.info(f"Tunnel URL ready: {self.tunnel_url}")
                        
                        # Start heartbeat timer
                        self._start_heartbeat()
                        
                        # Call the callback if provided
                        if self.on_url_ready:
                            try:
                                self.on_url_ready(self.tunnel_url)
                            except Exception as e:
                                logger.error(f"Error in URL ready callback: {e}")
            
            # Process ended
            self.is_running = False
            if self.process.returncode != 0:
                logger.error(f"Cloudflared process ended with code: {self.process.returncode}")
            
        except Exception as e:
            logger.error(f"Error running tunnel: {e}")
            self.is_running = False
    
    def _start_heartbeat(self):
        """Start the heartbeat timer to send periodic updates"""
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
        
        self._heartbeat_timer = threading.Timer(30.0, self._send_heartbeat)
        self._heartbeat_timer.daemon = True
        self._heartbeat_timer.start()
    
    def _send_heartbeat(self):
        """Send heartbeat data to the server"""
        if self.tunnel_url and self.is_running:
            try:
                connect_data = get_connect_data(self.tunnel_url)
                logger.debug(f"Sending heartbeat: {connect_data['endpoint']}")
                post_data("api/machines/connect", connect_data)
                
                # Schedule next heartbeat
                self._start_heartbeat()
            except Exception as e:
                logger.error(f"Error sending heartbeat: {e}")
                # Still schedule next heartbeat even if this one failed
                self._start_heartbeat()
    
    def stop_tunnel(self):
        """Stop the Cloudflare tunnel"""
        if not self.is_running or not self.process:
            return
        
        logger.info("Stopping Cloudflare tunnel...")
        self._stop_event.set()
        
        # Stop heartbeat timer
        if self._heartbeat_timer:
            self._heartbeat_timer.cancel()
            self._heartbeat_timer = None
        
        try:
            # Terminate the process gracefully
            self.process.terminate()
            
            # Wait for process to end, with timeout
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't terminate gracefully
                self.process.kill()
                self.process.wait()
            
            self.is_running = False
            self.tunnel_url = None
            logger.info("Tunnel stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping tunnel: {e}")
    
    def get_tunnel_url(self) -> Optional[str]:
        """Get the current tunnel URL"""
        return self.tunnel_url
    
    def is_tunnel_running(self) -> bool:
        """Check if the tunnel is currently running"""
        return self.is_running and self.process and self.process.poll() is None


# Global tunnel instance
_tunnel_instance = None

def get_tunnel_instance(port: int = 8188) -> CloudflareTunnel:
    """Get or create the global tunnel instance"""
    global _tunnel_instance
    if _tunnel_instance is None:
        _tunnel_instance = CloudflareTunnel(port=port)
    return _tunnel_instance

def init_tunnel(port: int = 8188, on_url_ready: Optional[Callable[[str], None]] = None) -> CloudflareTunnel:
    """
    Start a Cloudflare tunnel for ComfyUI
    
    Args:
        port: The port where ComfyUI is running
        on_url_ready: Callback function to call when URL is ready
        
    Returns:
        CloudflareTunnel: The tunnel instance
    """
    def on_url_ready_wrapper(url):
        # Use the reusable function to get connect data
        connect_data = get_connect_data(url)
        
        logger.info(f"Sending connection data to server: endpoint={url}, gpu={connect_data['gpu']}, "
                   f"vram={connect_data['vram']}GB, cpu={connect_data['cpu']}, "
                   f"ram={connect_data['ram']}GB, total_disk={connect_data['total_disk']}GB")
        post_data("api/machines/connect", connect_data)
        
        if on_url_ready:
            on_url_ready(url)

    tunnel = get_tunnel_instance(port)
    tunnel.on_url_ready = on_url_ready_wrapper
    
    if not tunnel.is_tunnel_running():
        tunnel.start_tunnel()
    
    return tunnel

def get_tunnel_url() -> Optional[str]:
    """Get the current tunnel URL if available"""
    global _tunnel_instance
    if _tunnel_instance:
        return _tunnel_instance.get_tunnel_url()
    return None

def stop_tunnel():
    """Stop the current tunnel"""
    global _tunnel_instance
    if _tunnel_instance:
        _tunnel_instance.stop_tunnel()


from aiohttp import web
from server import PromptServer

def register_tunnel_routes():
    @PromptServer.instance.routes.get('/api/sync-host')
    async def sync_host_endpoint(request):
        try:
            tunnel_url = get_tunnel_url()
            tunnel = get_tunnel_instance()
            
            if tunnel_url:
                # Send connect data to the server
                connect_data = get_connect_data(tunnel_url)
                logger.info(f"Syncing host data: endpoint={tunnel_url}")
                response = post_data("api/machines/connect", connect_data)
                
                return web.json_response({
                    'success': True,
                    'url': tunnel_url,
                    'running': tunnel.is_tunnel_running() if tunnel else False,
                    'port': tunnel.port if tunnel else None,
                    'sync_response': response
                })
            else:
                return web.json_response({
                    'success': False,
                    'error': 'No tunnel URL available',
                    'running': tunnel.is_tunnel_running() if tunnel else False,
                    'port': tunnel.port if tunnel else None
                })
        except Exception as e:
            logger.error(f"Error syncing host: {e}")
            return web.json_response({'success': False, 'error': str(e)}, status=500)