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
from typing import Optional, Callable

# Set up logging
logger = logging.getLogger(__name__)

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
    
    def stop_tunnel(self):
        """Stop the Cloudflare tunnel"""
        if not self.is_running or not self.process:
            return
        
        logger.info("Stopping Cloudflare tunnel...")
        self._stop_event.set()
        
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

def start_tunnel_for_comfyui(port: int = 8188, on_url_ready: Optional[Callable[[str], None]] = None) -> CloudflareTunnel:
    """
    Start a Cloudflare tunnel for ComfyUI
    
    Args:
        port: The port where ComfyUI is running
        on_url_ready: Callback function to call when URL is ready
        
    Returns:
        CloudflareTunnel: The tunnel instance
    """
    tunnel = get_tunnel_instance(port)
    if on_url_ready:
        tunnel.on_url_ready = on_url_ready
    
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
    time.sleep(5)  # Wait for ComfyUI to fully initialize
    start_tunnel_background()


def init_tunnel():
    tunnel_thread = threading.Thread(target=delayed_tunnel_start, daemon=True)
    tunnel_thread.start()
    print("[CloudflareTunnel] Starting tunnel in background...")