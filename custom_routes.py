from .workflow_converter import register_workflow_routes
from .connect_host import register_tunnel_routes
from .custom_nodes_installer import register_custom_nodes_routes

def register():
    register_workflow_routes()
    register_tunnel_routes()
    register_custom_nodes_routes()