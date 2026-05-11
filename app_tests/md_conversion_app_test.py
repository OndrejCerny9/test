import requests
from datetime import datetime

APP_URL = "https://agent-md-conversion-app-3863256616093854.14.azure.databricksapps.com"

token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

payload = {
    "filename": "test_volume_report",
    "content": f"""# Test Volume Report

This is a test markdown file created from Databricks notebook.

Created at: {datetime.now().isoformat()}
""",
}

response = requests.post(
    f"{APP_URL}/save-markdown",
    json=payload,
    headers={
        "Authorization": f"Bearer {token}",
    },
    timeout=60,
)

print("Status code:", response.status_code)
print("Content type:", response.headers.get("content-type"))
print(response.text[:1000])