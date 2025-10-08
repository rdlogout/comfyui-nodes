from .workflow_converter import register_workflow_routes
from .connect_host import register_tunnel_routes
from .custom_nodes_installer import register_custom_nodes_routes
from .model_downloader import register_model_downloader_routes
from .pull_updater import register_pull_update_routes
from .queue_prompt import register_queue_prompt_routes
from .prompt_status import register_prompt_status_routes
from .workflow_run import register_workflow_run_routes
from .dependencies import register_dependencies_routes

def register():
    register_workflow_routes()
    register_tunnel_routes()
    register_custom_nodes_routes()
    register_model_downloader_routes()
    register_pull_update_routes()
    register_queue_prompt_routes()
    register_prompt_status_routes()
    register_workflow_run_routes()
    register_dependencies_routes()
