import os
import yaml
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

# Retrieve your project endpoint from environment variables or manually
project_endpoint = "https://rimmi-mgibxtek-swedencentral.services.ai.azure.com/api/projects/Devops_Project"
credential = DefaultAzureCredential()

try:
    project_client = AIProjectClient(endpoint=project_endpoint, credential=credential)
    with open("myagent.yaml", "r") as f:
        yaml_content = yaml.safe_load(f)
    agent = project_client.agents.create_agent(
        model=yaml_content["model"]["deployment_name"],
        name=yaml_content["name"],
        instructions=yaml_content["instructions"],
    )
    print(f"Successfully deployed agent: {agent.name}")
except Exception as e:
    print(f"Deployment failed: {e}")
