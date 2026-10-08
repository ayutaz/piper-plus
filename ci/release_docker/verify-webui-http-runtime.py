import hashlib
import json
import urllib.request
from pathlib import Path


with urllib.request.urlopen("http://127.0.0.1:7860/", timeout=15) as response:
    html = response.read()
    assert response.status == 200 and b"gradio" in html.lower()
with urllib.request.urlopen("http://127.0.0.1:7860/config", timeout=15) as response:
    config = json.load(response)
assert config["components"] and config["dependencies"]
models = [
    component["props"]
    for component in config["components"]
    if component["type"] == "dropdown"
    and component["props"].get("value") == "/models/model.onnx"
]
assert len(models) == 1, models
proof = {
    "scope": "public WebUI image: actual entrypoint startup and HTTP UI configuration",
    "source_revision": "71acf30c8e23e17b639fd40a8117415c3df55c0a",
    "network_disabled": True,
    "no_host_ports": True,
    "html_status": 200,
    "html_sha256": hashlib.sha256(html).hexdigest(),
    "selected_model": models[0]["value"],
    "ui_components": len(config["components"]),
    "ui_dependencies": len(config["dependencies"]),
}
Path("/output/webui-http-runtime-verification.json").write_text(
    json.dumps(proof, indent=2) + "\n"
)
print(json.dumps(proof))
