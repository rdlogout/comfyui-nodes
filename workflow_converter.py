"""
Workflow converter for ComfyUI
Converts non-API workflow format to API format for execution
Created by Seth A. Robinson - https://github.com/SethRobinson/comfyui-workflow-to-api-converter-endpoint
"""

import json
import logging
from typing import Dict, Any, List, Tuple, Optional, Union

# Set up logging
logger = logging.getLogger(__name__)

# Import ComfyUI node information - this is required
try:
    import nodes
except ImportError as e:
    raise ImportError(
        "Cannot import ComfyUI nodes module. "
        "This converter must be run within the ComfyUI environment. "
        "Make sure ComfyUI is properly initialized before using the converter."
    ) from e

# Cache for node definitions
_node_info_cache = {}

def get_node_info_for_type(node_type: str) -> Dict[str, Any]:
    """Get node information for a specific node type"""
    global _node_info_cache
    
    if node_type not in _node_info_cache:
        # Try to get the node info
        if node_type in nodes.NODE_CLASS_MAPPINGS:
            try:
                obj_class = nodes.NODE_CLASS_MAPPINGS[node_type]
                info = {}
                info['input'] = obj_class.INPUT_TYPES()
                info['input_order'] = {key: list(value.keys()) for (key, value) in obj_class.INPUT_TYPES().items()}
                _node_info_cache[node_type] = info
            except Exception as e:
                logger.debug(f"Could not get node info for {node_type}: {e}")
                _node_info_cache[node_type] = None
        else:
            _node_info_cache[node_type] = None
    
    return _node_info_cache.get(node_type)


class WorkflowConverter:
    """Converts non-API workflow format to API prompt format"""
    
    @staticmethod
    def is_api_format(workflow: Dict[str, Any]) -> bool:
        """
        Check if a workflow is already in API format.
        API format has node IDs as keys with 'class_type' and 'inputs'.
        Non-API format has 'nodes', 'links', etc.
        """
        # Check for non-API format indicators
        if 'nodes' in workflow and 'links' in workflow:
            return False
        
        # Check if it looks like API format
        # API format should have numeric string keys with class_type
        for key, value in workflow.items():
            if key in ['prompt', 'extra_data', 'client_id']:
                continue
            if isinstance(value, dict) and 'class_type' in value:
                return True
        
        return False
    
    @staticmethod
    def convert_to_api(workflow: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a non-API workflow to API format.
        
        Args:
            workflow: Non-API format workflow with nodes and links
            
        Returns:
            API format workflow ready for execution
        """
        if WorkflowConverter.is_api_format(workflow):
            # Already in API format
            return workflow
        
        # Extract nodes and links
        workflow_nodes = workflow.get('nodes', [])
        links = workflow.get('links', [])
        
        # Build link map for quick lookup
        # link_id -> (source_node_id, source_slot, target_node_id, target_slot, type)
        link_map = {}
        # Also track which nodes are connected to others (have outputs that go somewhere)
        nodes_with_connected_outputs = set()
        
        for link in links:
            if len(link) >= 6:
                link_id = link[0]
                source_id = link[1]
                source_slot = link[2]
                target_id = link[3]
                target_slot = link[4]
                link_type = link[5] if len(link) > 5 else None
                link_map[link_id] = {
                    'source_id': source_id,
                    'source_slot': source_slot,
                    'target_id': target_id,
                    'target_slot': target_slot,
                    'type': link_type
                }
                # Track that this source node has connected outputs
                nodes_with_connected_outputs.add(source_id)
        
        # First pass: identify PrimitiveNodes and their values
        # Also identify nodes that should be excluded from API format
        primitive_values = {}
        nodes_to_exclude = set()
        bypassed_nodes = set()  # Track bypassed/disabled nodes
        
        for node in workflow_nodes:
            node_id = node.get('id')
            node_type = node.get('type')
            node_mode = node.get('mode', 0)
            
            # Track bypassed/disabled nodes
            if node_mode == 4:
                bypassed_nodes.add(node_id)
                logger.debug(f"Tracking bypassed node {node_id} ({node_type})")
            
            # Track primitive nodes
            if node_type == 'PrimitiveNode':
                node_id_str = str(node_id)
                widget_values = node.get('widgets_values')
                if widget_values and len(widget_values) > 0:
                    primitive_values[node_id_str] = widget_values[0]
            
            # Check if this node should be excluded from API format
            # Exclude nodes that have no connected outputs (UI-only nodes)
            outputs = node.get('outputs', [])
            has_connected_output = False
            for output in outputs:
                output_links = output.get('links', [])
                if output_links and len(output_links) > 0:
                    has_connected_output = True
                    break
            
            # Check if this is a special UI-only node type that should be excluded
            # LoadImageOutput is a special case - it's for loading from the output folder
            # which is a UI convenience that shouldn't be in the API format
            if node_type == 'LoadImageOutput':
                nodes_to_exclude.add(node_id)
                logger.debug(f"Marking node {node_id} ({node_type}) for exclusion - UI-only node type")
            # If node has no outputs or no connected outputs, it should be excluded
            # unless it's an OUTPUT_NODE (like SaveImage, PreviewImage)
            elif not outputs or not has_connected_output:
                # Check if this is an OUTPUT_NODE that should be kept
                node_class = nodes.NODE_CLASS_MAPPINGS.get(node_type) if hasattr(nodes, 'NODE_CLASS_MAPPINGS') else None
                is_output_node = node_class and hasattr(node_class, 'OUTPUT_NODE') and node_class.OUTPUT_NODE
                
                if not is_output_node:
                    nodes_to_exclude.add(node_id)
                    logger.debug(f"Marking node {node_id} ({node_type}) for exclusion - no connected outputs")
                else:
                    logger.debug(f"Keeping node {node_id} ({node_type}) - OUTPUT_NODE=True despite no connected outputs")
        
        # Helper function to trace through bypassed nodes
        def trace_through_bypassed(source_node_id, source_slot, visited=None):
            """
            Trace through bypassed nodes to find the actual source.
            Returns (actual_source_id, actual_source_slot) tuple.
            """
            if visited is None:
                visited = set()
            
            # Avoid infinite loops
            if source_node_id in visited:
                return (source_node_id, source_slot)
            visited.add(source_node_id)
            
            # If source is not bypassed, return it as-is
            if source_node_id not in bypassed_nodes:
                return (source_node_id, source_slot)
            
            # Find the input to this bypassed node
            for node in workflow_nodes:
                if node.get('id') == source_node_id:
                    # Look for the input that should be passed through
                    node_inputs = node.get('inputs', [])
                    if node_inputs:
                        # For bypassed nodes, we typically pass through the first image/latent input
                        # This matches ComfyUI's bypass behavior
                        for input_info in node_inputs:
                            input_link = input_info.get('link')
                            if input_link is not None and input_link in link_map:
                                link_data = link_map[input_link]
                                # Recursively trace through this source
                                return trace_through_bypassed(
                                    link_data['source_id'], 
                                    link_data['source_slot'],
                                    visited
                                )
                    break
            
            # If we couldn't trace further, return original
            return (source_node_id, source_slot)
        
        # Build API format prompt
        api_prompt = {}
        
        for node in workflow_nodes:
            node_id = str(node.get('id'))
            node_type = node.get('type')
            
            if not node_type:
                continue
                
            # Skip muted and bypassed/disabled nodes
            node_mode = node.get('mode', 0)
            if node_mode == 2:  # Mode 2 is muted
                logger.debug(f"Skipping muted node {node_id} ({node_type})")
                continue
            elif node_mode == 4:  # Mode 4 is bypassed/disabled
                logger.debug(f"Skipping bypassed/disabled node {node_id} ({node_type})")
                continue
            
            # Skip non-executable nodes
            # These include UI-only nodes and nodes with no connected outputs
            if node_type in ['Note', 'PrimitiveNode']:
                logger.debug(f"Skipping {node_type} node {node_id}")
                continue
            
            # Skip nodes that were identified as having no connected outputs
            if node.get('id') in nodes_to_exclude:
                logger.debug(f"Skipping {node_type} node {node_id} - no connected outputs")
                continue
            
            # Build node entry
            api_node = {
                'inputs': {},
                'class_type': node_type
            }
            
            # Add _meta field with title if available
            if 'title' in node:
                api_node['_meta'] = {'title': node['title']}
            elif hasattr(nodes, 'NODE_DISPLAY_NAME_MAPPINGS') and node_type in nodes.NODE_DISPLAY_NAME_MAPPINGS:
                # Use ComfyUI's node display name mappings
                api_node['_meta'] = {'title': nodes.NODE_DISPLAY_NAME_MAPPINGS[node_type]}
            else:
                # Use the node type as-is for the title
                api_node['_meta'] = {'title': node_type}
            
            # Process inputs (connections via links)
            link_inputs = {}
            primitive_inputs = {}  # Separate tracking for resolved primitive values
            node_inputs = node.get('inputs', [])
            
            if node_inputs:
                for input_info in node_inputs:
                    input_name = input_info.get('name')
                    input_link = input_info.get('link')
                    
                    if input_link is not None and input_link in link_map:
                        # This input is connected via a link
                        link_data = link_map[input_link]
                        source_node_id = link_data['source_id']
                        source_slot = link_data['source_slot']
                        
                        # Trace through bypassed nodes to find the actual source
                        actual_source_id, actual_source_slot = trace_through_bypassed(source_node_id, source_slot)
                        source_node_id_str = str(actual_source_id)
                        
                        # Check if the source is a PrimitiveNode or excluded node
                        if source_node_id_str in primitive_values:
                            # This is a resolved primitive value - treat as widget for ordering
                            primitive_inputs[input_name] = primitive_values[source_node_id_str]
                        elif actual_source_id in nodes_to_exclude:
                            # Source node is excluded, skip this input connection
                            logger.debug(f"Skipping input {input_name} from excluded node {source_node_id_str}")
                        else:
                            # Keep as link with the actual source (bypassing any disabled nodes)
                            if actual_source_id != source_node_id:
                                logger.debug(f"Bypassing disabled node {source_node_id}, connecting {input_name} to {actual_source_id} instead")
                            link_inputs[input_name] = [source_node_id_str, actual_source_slot]
            
            # Get the correct input order from the node class
            ordered_inputs = WorkflowConverter._get_ordered_inputs(node_type, node)
            
            # Process widget values
            widget_values = node.get('widgets_values')
            widget_inputs = {}
            
            if widget_values is not None:
                # Handle both list and dict widget values
                if isinstance(widget_values, dict):
                    # Direct dictionary mapping - use as-is
                    for key, value in widget_values.items():
                        # Skip special keys that aren't actual inputs
                        if key in ['videopreview', 'preview']:
                            continue
                        # Only add if not connected via link
                        if key not in link_inputs:
                            widget_inputs[key] = value
                            
                elif isinstance(widget_values, list):
                    # List of values - need to map to widget names
                    # First check if widget values contain dictionaries with self-describing names
                    has_dict_widgets = any(isinstance(v, dict) for v in widget_values)
                    
                    if has_dict_widgets:
                        # Handle widget values that are dictionaries
                        # These often self-describe their input names
                        WorkflowConverter._process_dict_widget_values(widget_values, widget_inputs, link_inputs)
                    else:
                        # Regular widget values - need to map to widget names
                        widget_mappings = WorkflowConverter._get_widget_mappings(node_type, node)
                        
                        # Special handling for control_after_generate values
                        filtered_values = WorkflowConverter._filter_control_values(widget_values)
                        
                        # Map values to widget names
                        if widget_mappings:
                            for i, value in enumerate(filtered_values):
                                if i < len(widget_mappings):
                                    widget_name = widget_mappings[i]
                                    # Only add if we have a valid name and it's not connected via link
                                    if widget_name and widget_name not in link_inputs:
                                        widget_inputs[widget_name] = value
                        else:
                            # If we couldn't determine mappings for an unknown node,
                            # we'll have to skip the widget values
                            if filtered_values:
                                logger.warning(f"Could not map widget values for unknown node type '{node_type}' (node {node_id})")
            
            # Build inputs in the correct order
            # The official "Save (API)" format follows this pattern:
            # ALL widget values first (in node class order), then ALL link inputs (in node class order)
            # Note: Resolved primitive values are treated as widgets for ordering
            if ordered_inputs:
                # First pass: add all widget values in order (including resolved primitives)
                for input_name in ordered_inputs:
                    if input_name in widget_inputs:
                        api_node['inputs'][input_name] = widget_inputs[input_name]
                    elif input_name in primitive_inputs:
                        api_node['inputs'][input_name] = primitive_inputs[input_name]
                
                # Second pass: add all link inputs in order
                for input_name in ordered_inputs:
                    if input_name in link_inputs and input_name not in api_node['inputs']:
                        api_node['inputs'][input_name] = link_inputs[input_name]
                
                # Add any remaining inputs that weren't in the ordered list
                for key, value in widget_inputs.items():
                    if key not in api_node['inputs']:
                        api_node['inputs'][key] = value
                for key, value in primitive_inputs.items():
                    if key not in api_node['inputs']:
                        api_node['inputs'][key] = value
                for key, value in link_inputs.items():
                    if key not in api_node['inputs']:
                        api_node['inputs'][key] = value
            else:
                # Fallback when we don't have the node class: add all inputs in order they appear
                # First add ALL widget inputs and primitives, then ALL link inputs
                for key, value in widget_inputs.items():
                    api_node['inputs'][key] = value
                for key, value in primitive_inputs.items():
                    if key not in api_node['inputs']:
                        api_node['inputs'][key] = value
                for key, value in link_inputs.items():
                    if key not in api_node['inputs']:
                        api_node['inputs'][key] = value
            
            api_prompt[node_id] = api_node
        
        return api_prompt
    
    @staticmethod
    def _process_dict_widget_values(widget_values: List[Any], widget_inputs: Dict[str, Any], link_inputs: Dict[str, Any]) -> None:
        """
        Process widget values that contain dictionaries.
        These are self-describing widgets that contain their configuration as dicts.
        """
        lora_counter = 0
        
        for value in widget_values:
            if isinstance(value, dict):
                if not value:
                    # Empty dict - skip
                    continue
                elif 'type' in value:
                    # Widget with a type field - use the type as the input name
                    widget_name = value.get('type')
                    if widget_name and widget_name not in link_inputs:
                        widget_inputs[widget_name] = value
                elif 'lora' in value:
                    # This is a lora configuration entry
                    lora_counter += 1
                    widget_name = f'lora_{lora_counter}'
                    if widget_name not in link_inputs:
                        # Remove 'strengthTwo' if it's None (not used in API format)
                        clean_value = {k: v for k, v in value.items() if k != 'strengthTwo' or v is not None}
                        widget_inputs[widget_name] = clean_value
                else:
                    # Unknown dict structure - include it as-is with a generic name
                    # This ensures we don't lose data even for unknown structures
                    logger.debug(f"Unknown dict widget value structure: {value}")
            elif isinstance(value, str):
                # String values at the end often represent buttons or special controls
                # The "➕ Add Lora" button is a common example
                if value == '':
                    # Empty string often represents the "Add" button
                    widget_inputs['➕ Add Lora'] = value
            # Skip None values and other types that don't map to widgets
    
    @staticmethod
    def _filter_control_values(widget_values: List[Any]) -> List[Any]:
        """Filter out control_after_generate values from widget list"""
        # control_after_generate values are typically strings like "fixed", "increment", "decrement", "randomize"
        # These are UI controls and not actual input values
        control_values = {"fixed", "increment", "decrement", "randomize"}
        
        filtered = []
        for value in widget_values:
            if isinstance(value, str) and value in control_values:
                # Skip control values
                continue
            filtered.append(value)
        
        return filtered
    
    @staticmethod
    def _get_widget_mappings(node_type: str, node: Dict[str, Any]) -> Optional[List[str]]:
        """
        Get the widget name mappings for a node type.
        Returns a list of widget names in the order they appear in widgets_values.
        """
        node_info = get_node_info_for_type(node_type)
        if not node_info:
            return None
        
        # Get the input types and their order
        input_types = node_info.get('input', {})
        required_inputs = input_types.get('required', {})
        optional_inputs = input_types.get('optional', {})
        
        # Build list of widget names (inputs that aren't connections)
        widget_names = []
        
        # Add required inputs that are widgets (not connections)
        for input_name, input_config in required_inputs.items():
            # Check if this input is connected via a link
            is_connected = False
            node_inputs = node.get('inputs', [])
            for input_info in node_inputs:
                if input_info.get('name') == input_name and input_info.get('link') is not None:
                    is_connected = True
                    break
            
            # If not connected, it's a widget
            if not is_connected:
                widget_names.append(input_name)
        
        # Add optional inputs that are widgets
        for input_name, input_config in optional_inputs.items():
            # Check if this input is connected via a link
            is_connected = False
            node_inputs = node.get('inputs', [])
            for input_info in node_inputs:
                if input_info.get('name') == input_name and input_info.get('link') is not None:
                    is_connected = True
                    break
            
            # If not connected, it's a widget
            if not is_connected:
                widget_names.append(input_name)
        
        return widget_names
    
    @staticmethod
    def _get_ordered_inputs(node_type: str, node: Dict[str, Any]) -> Optional[List[str]]:
        """
        Get the ordered list of all inputs for a node type.
        This includes both widget inputs and connection inputs.
        """
        node_info = get_node_info_for_type(node_type)
        if not node_info:
            return None
        
        # Get the input types and their order
        input_types = node_info.get('input', {})
        required_inputs = input_types.get('required', {})
        optional_inputs = input_types.get('optional', {})
        
        # Build ordered list of all input names
        ordered_inputs = []
        
        # Add required inputs first
        ordered_inputs.extend(required_inputs.keys())
        
        # Add optional inputs
        ordered_inputs.extend(optional_inputs.keys())
        
        return ordered_inputs