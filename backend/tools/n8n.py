"""n8n workflow automation helper"""
import json
from typing import Dict, Any, Optional, List

try:
    from backend.tools import terminal, config
except ImportError:
    try:
        from tools import terminal, config
    except ImportError:
        from . import terminal, config


def _success(output):
    return {"status": "success", "output": output}


def _error(message):
    return {"status": "error", "error": message}


def draft_workflow(description: str, trigger_type: str = "webhook") -> Dict[str, Any]:
    """
    Draft an n8n workflow from a natural language description.
    
    Args:
        description: Description of what the workflow should do
        trigger_type: Type of trigger (webhook, schedule, manual)
    
    Returns:
        Dict with workflow JSON structure
    """
    try:
        if not description or not description.strip():
            return _error("Workflow description cannot be empty")
        
        # Create basic workflow structure
        workflow = {
            "name": "New Workflow",
            "nodes": [],
            "connections": {},
            "settings": {},
            "staticData": None
        }
        
        # Add trigger node
        if trigger_type == "webhook":
            trigger_node = {
                "parameters": {
                    "path": "webhook",
                    "responseMode": "onReceived",
                    "options": {}
                },
                "name": "Webhook",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 1,
                "position": [250, 300],
                "webhookId": ""
            }
        elif trigger_type == "schedule":
            trigger_node = {
                "parameters": {
                    "rule": {
                        "interval": [{"field": "hours", "hoursInterval": 1}]
                    }
                },
                "name": "Schedule Trigger",
                "type": "n8n-nodes-base.scheduleTrigger",
                "typeVersion": 1,
                "position": [250, 300]
            }
        else:  # manual
            trigger_node = {
                "parameters": {},
                "name": "Manual Trigger",
                "type": "n8n-nodes-base.manualTrigger",
                "typeVersion": 1,
                "position": [250, 300]
            }
        
        workflow["nodes"].append(trigger_node)
        
        # Parse description for common patterns
        description_lower = description.lower()
        node_position_y = 300
        node_position_x = 450
        last_node = trigger_node["name"]
        
        # HTTP Request patterns
        if any(word in description_lower for word in ["http", "api", "get", "post", "request", "fetch"]):
            http_node = {
                "parameters": {
                    "url": "https://api.example.com/endpoint",
                    "authentication": "none",
                    "options": {}
                },
                "name": "HTTP Request",
                "type": "n8n-nodes-base.httpRequest",
                "typeVersion": 3,
                "position": [node_position_x, node_position_y]
            }
            workflow["nodes"].append(http_node)
            workflow["connections"][last_node] = {"main": [[{"node": "HTTP Request", "type": "main", "index": 0}]]}
            last_node = "HTTP Request"
            node_position_x += 200
        
        # Email patterns
        if any(word in description_lower for word in ["email", "send email", "mail", "notify via email"]):
            email_node = {
                "parameters": {
                    "fromEmail": "sender@example.com",
                    "toEmail": "recipient@example.com",
                    "subject": "Notification",
                    "text": "={{ $json.message }}"
                },
                "name": "Send Email",
                "type": "n8n-nodes-base.emailSend",
                "typeVersion": 2,
                "position": [node_position_x, node_position_y]
            }
            workflow["nodes"].append(email_node)
            workflow["connections"][last_node] = {"main": [[{"node": "Send Email", "type": "main", "index": 0}]]}
            last_node = "Send Email"
            node_position_x += 200
        
        # Database patterns
        if any(word in description_lower for word in ["database", "postgres", "mysql", "sql"]):
            db_node = {
                "parameters": {
                    "operation": "executeQuery",
                    "query": "SELECT * FROM table_name LIMIT 10"
                },
                "name": "Database Query",
                "type": "n8n-nodes-base.postgres",
                "typeVersion": 2,
                "position": [node_position_x, node_position_y]
            }
            workflow["nodes"].append(db_node)
            workflow["connections"][last_node] = {"main": [[{"node": "Database Query", "type": "main", "index": 0}]]}
            last_node = "Database Query"
            node_position_x += 200
        
        # Conditional logic
        if any(word in description_lower for word in ["if", "condition", "check", "when"]):
            if_node = {
                "parameters": {
                    "conditions": {
                        "string": [
                            {
                                "value1": "={{ $json.field }}",
                                "operation": "equals",
                                "value2": "expected_value"
                            }
                        ]
                    }
                },
                "name": "IF",
                "type": "n8n-nodes-base.if",
                "typeVersion": 1,
                "position": [node_position_x, node_position_y]
            }
            workflow["nodes"].append(if_node)
            workflow["connections"][last_node] = {"main": [[{"node": "IF", "type": "main", "index": 0}]]}
            last_node = "IF"
            node_position_x += 200
        
        # Data transformation
        if any(word in description_lower for word in ["transform", "map", "format", "convert"]):
            set_node = {
                "parameters": {
                    "values": {
                        "string": [
                            {
                                "name": "output_field",
                                "value": "={{ $json.input_field }}"
                            }
                        ]
                    },
                    "options": {}
                },
                "name": "Set",
                "type": "n8n-nodes-base.set",
                "typeVersion": 2,
                "position": [node_position_x, node_position_y]
            }
            workflow["nodes"].append(set_node)
            workflow["connections"][last_node] = {"main": [[{"node": "Set", "type": "main", "index": 0}]]}
            node_position_x += 200
        
        return _success({
            "workflow": workflow,
            "nodes_count": len(workflow["nodes"]),
            "description": description,
            "note": "This is a draft workflow. Review and customize node parameters before using."
        })
        
    except Exception as e:
        return _error(f"Failed to draft workflow: {str(e)}")


def validate_workflow(workflow_json: str) -> Dict[str, Any]:
    """
    Validate n8n workflow JSON structure.
    
    Args:
        workflow_json: Workflow JSON string to validate
    
    Returns:
        Dict with validation results
    """
    try:
        if not workflow_json or not workflow_json.strip():
            return _error("Workflow JSON cannot be empty")
        
        # Parse JSON
        try:
            workflow = json.loads(workflow_json)
        except json.JSONDecodeError as e:
            return _error(f"Invalid JSON syntax: {str(e)}")
        
        issues = []
        warnings = []
        
        # Check required fields
        if not isinstance(workflow, dict):
            return _error("Workflow must be a JSON object")
        
        if "nodes" not in workflow:
            issues.append("Missing required field: 'nodes'")
        elif not isinstance(workflow["nodes"], list):
            issues.append("'nodes' must be an array")
        
        if "connections" not in workflow:
            warnings.append("Missing 'connections' field - nodes won't be connected")
        
        # Check nodes
        if "nodes" in workflow and isinstance(workflow["nodes"], list):
            node_names = set()
            
            for i, node in enumerate(workflow["nodes"]):
                if not isinstance(node, dict):
                    issues.append(f"Node {i} is not a valid object")
                    continue
                
                # Check required node fields
                if "name" not in node:
                    issues.append(f"Node {i} missing 'name' field")
                else:
                    name = node["name"]
                    if name in node_names:
                        issues.append(f"Duplicate node name: '{name}'")
                    node_names.add(name)
                
                if "type" not in node:
                    issues.append(f"Node '{node.get('name', i)}' missing 'type' field")
                
                if "position" not in node:
                    warnings.append(f"Node '{node.get('name', i)}' missing 'position' (visual layout)")
        
        # Check connections reference valid nodes
        if "connections" in workflow and isinstance(workflow["connections"], dict):
            for source_node, connections in workflow["connections"].items():
                if source_node not in node_names:
                    issues.append(f"Connection references non-existent node: '{source_node}'")
        
        result = {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "nodes_count": len(workflow.get("nodes", [])),
            "connections_count": len(workflow.get("connections", {}))
        }
        
        return _success(result)
        
    except Exception as e:
        return _error(f"Validation failed: {str(e)}")


def trigger_workflow(workflow_id: str, data: Optional[dict] = None) -> Dict[str, Any]:
    """
    Trigger an n8n workflow execution via webhook.
    
    Args:
        workflow_id: n8n workflow ID or webhook path
        data: Optional data to send with the trigger
    
    Returns:
        Dict with execution result
    """
    try:
        # Get n8n configuration
        url_result = config.get_config("n8n.url")
        if url_result.get("status") != "success":
            return _error("n8n URL not configured. Use: config.set('n8n.url', 'https://your-n8n-url')")
        
        n8n_url = url_result.get("output", {}).get("value", "").rstrip('/')
        
        # Build webhook URL
        webhook_url = f"{n8n_url}/webhook/{workflow_id}"
        
        # Prepare data
        if data:
            data_json = json.dumps(data)
            curl_cmd = f'''curl -s -X POST "{webhook_url}" -H "Content-Type: application/json" -d '{data_json}' '''
        else:
            curl_cmd = f'curl -s -X POST "{webhook_url}"'
        
        result = terminal.run(curl_cmd, timeout_seconds=30)
        
        if result.get("status") != "success":
            return _error(f"Failed to trigger workflow: {result.get('error')}")
        
        response = result.get("output", "")
        
        # Try to parse response as JSON
        try:
            response_data = json.loads(response) if response else {}
        except:
            response_data = {"raw_response": response}
        
        return _success({
            "triggered": True,
            "workflow_id": workflow_id,
            "response": response_data
        })
        
    except Exception as e:
        return _error(f"Failed to trigger workflow: {str(e)}")
