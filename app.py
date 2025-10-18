from flask import Flask, request, jsonify
import os, json, base64, re, requests, logging

app = Flask(__name__)

# --- Environment variables ---
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY")
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")
AZ_DEVOPS_ORG = os.getenv("AZ_DEVOPS_ORG")
AZ_DEVOPS_PROJECT = os.getenv("AZ_DEVOPS_PROJECT")
AZ_DEVOPS_REPO = os.getenv("AZ_DEVOPS_REPO")
AZ_DEVOPS_PAT = os.getenv("AZ_DEVOPS_PAT")
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"
ALLOWED_PATH_PREFIXES = os.getenv("ALLOWED_PATH_PREFIXES", "/,pipelines,apps,docs,infrastructure").split(",")

API_VERSION = "7.1"

# --- Helper: OpenAI REST call ---
def call_llm(system, user):
    url = f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_OPENAI_DEPLOYMENT}/chat/completions?api-version=2023-05-15"
    headers = {"Content-Type": "application/json", "api-key": AZURE_OPENAI_KEY}
    payload = {
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": 0,
        "max_tokens": 1500
    }
    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

# --- Helper: DevOps API ---
def _base(): 
    return f"https://dev.azure.com/{AZ_DEVOPS_ORG}/{AZ_DEVOPS_PROJECT}/_apis/git/repositories/{AZ_DEVOPS_REPO}"

def _auth(): 
    token = ":" + AZ_DEVOPS_PAT
    return {"Authorization": "Basic " + base64.b64encode(token.encode()).decode(), "Content-Type": "application/json"}

def get_branch_object_id(branch="main"):
    url = _base() + f"/refs?filter=heads/{branch}&api-version={API_VERSION}"
    data = requests.get(url, headers=_auth()).json()
    return data["value"][0]["objectId"]

def push_commit(changes, commit_message, branch="main"):
    if DRY_RUN:
        return {"dry_run": True, "changes": changes}
    base_commit = get_branch_object_id(branch)
    ref_update = {"name": f"refs/heads/{branch}", "oldObjectId": base_commit}
    commit_changes = []
    for ch in changes:
        p = "/" + ch["path"].lstrip("/")
        if not any(p.startswith(pref if pref.startswith("/") else "/" + pref) for pref in ALLOWED_PATH_PREFIXES):
            raise ValueError(f"Path {p} not allowed")
        commit_changes.append({
            "changeType": ch.get("changeType", "add"),
            "item": {"path": p},
            "newContent": {"content": ch.get("content", ""), "contentType": "rawtext"}
        })
    body = {"refUpdates": [ref_update], "commits": [{"comment": commit_message, "changes": commit_changes}]}
    resp = requests.post(_base() + f"/pushes?api-version={API_VERSION}", headers=_auth(), json=body)
    resp.raise_for_status()
    return resp.json()

# --- Helper: Extract JSON safely ---
def extract_json_from_text(text):
    """Extract and parse the first JSON object from a text string."""
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        return None
    raw = match.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # try to clean escaped newlines and quotes
        cleaned = raw.replace("\\n", "\n").replace('\\"', '"')
        try:
            return json.loads(cleaned)
        except Exception:
            return None

# --- Main instruction endpoint ---
@app.route("/instruction", methods=["POST"])
def instruction():
    data = request.get_json()
    instruction = data.get("instruction")
    if not instruction:
        return jsonify({"error": "Missing instruction"}), 400

    system_prompt = (
        "You are an autonomous DevOps agent. Produce a JSON object describing the repo file changes "
        "for the given instruction. Allowed changeTypes: add, edit, delete. "
        "Schema:\n"
        "{'changes':[{'path':'...','content':'...','changeType':'add'}],'commit_message':'msg'}"
    )
    user_prompt = f"Instruction: {instruction}\nConstraints: Allowed paths: {ALLOWED_PATH_PREFIXES}"

    llm_output = call_llm(system_prompt, user_prompt)
    parsed = extract_json_from_text(llm_output)

    if not parsed:
        return jsonify({"error": "Failed to parse LLM output", "raw": llm_output}), 500

    result = push_commit(parsed["changes"], parsed.get("commit_message", "Agent commit"))
    return jsonify({"status": "ok", "result": result})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)