"""Create a GitHub Release for the current SemVer tag."""

import json
import os
import urllib.error
import urllib.request

api = os.environ["CI_API_V4_URL"]
project = os.environ["CI_PROJECT_ID"]
tag = os.environ["CI_COMMIT_TAG"]
url = f"{api}/projects/{project}/releases"
payload = json.dumps(
    {
        "name": f"Release {tag}",
        "tag_name": tag,
        "description": f"SemVer release {tag}. Signed images and SBOM are produced by CI.",
    }
).encode()
request = urllib.request.Request(
    url,
    data=payload,
    method="POST",
    headers={"JOB-TOKEN": os.environ["CI_JOB_TOKEN"], "Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(request) as response:
        print(response.read().decode())
except urllib.error.HTTPError as error:
    if error.code == 409:
        print(f"Release {tag} already exists")
    else:
        raise
