import os
import requests
import subprocess
import json
import time
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# --- SETUP ---
# Load environment variables from a .env file for local development
load_dotenv()
app = Flask(__name__)

# --- CONSTANTS ---
# Load secrets and configuration from environment variables
MY_SECRET = os.getenv("MY_SECRET")
AIPIPE_API_KEY = os.getenv("AIPIPE_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
AIPIPE_API_URL = "https://aipipe.org/openrouter/v1/chat/completions"


def generate_code_with_llm(prompt):
    """Sends a prompt to the LLM and returns the response content."""
    print(">>> Contacting LLM...")
    headers = {"Authorization": f"Bearer {AIPIPE_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "openai/gpt-4.1-nano", "messages": [{"role": "user", "content": prompt}]}
    try:
        response = requests.post(AIPIPE_API_URL, headers=headers, json=payload, timeout=180)
        response.raise_for_status()
        print("<<< LLM response received.")
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as e:
        print(f"!!! LLM API Call Failed: {e} !!!")
        return None


def create_and_push_to_github(task_id, code_json):
    """Creates a new GitHub repo and pushes the initial code."""
    repo_name = task_id
    local_repo_path = os.path.join(os.getcwd(), repo_name)
    print(f">>> Starting GitHub BUILD process for repo: {repo_name}")
    try:
        # Clean the JSON string from the LLM response
        start_index = code_json.find('{')
        end_index = code_json.rfind('}') + 1
        if start_index == -1 or end_index == 0:
            raise json.JSONDecodeError("Could not find JSON object in LLM response", code_json, 0)
        clean_json_string = code_json[start_index:end_index]

        # Create local directory and files
        if os.path.exists(local_repo_path):
            subprocess.run(f"rmdir /s /q {local_repo_path}", shell=True, check=False)
        os.makedirs(local_repo_path)
        code_data = json.loads(clean_json_string)
        for filename, content in code_data.items():
            with open(os.path.join(local_repo_path, filename), "w", encoding="utf-8") as f:
                f.write(content)
        with open(os.path.join(local_repo_path, "LICENSE"), "w") as f:
            f.write("MIT License\n\nCopyright (c) 2025\n...") # Add full MIT license text
        with open(os.path.join(local_repo_path, "README.md"), "w") as f:
            f.write(f"# {repo_name}\n\nThis project was auto-generated.")
        
        # Initialize Git and commit files
        subprocess.run(["git", "init"], cwd=local_repo_path, check=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=local_repo_path, check=True)
        subprocess.run(["git", "add", "."], cwd=local_repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Deployment Bot"], cwd=local_repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "bot@example.com"], cwd=local_repo_path, check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=local_repo_path, check=True)
        
        # Set up environment for gh command
        env = os.environ.copy()
        env["GITHUB_TOKEN"] = GITHUB_TOKEN
        
        # Use the system-wide 'gh' installed by the Dockerfile
        subprocess.run(["gh", "repo", "delete", repo_name, "--yes"], check=False, env=env)
        repo_create_command = ["gh", "repo", "create", repo_name, "--public", "--source=.", "--remote=origin"]
        subprocess.run(repo_create_command, cwd=local_repo_path, check=True, env=env)
        
        print(f"   - Created GitHub repo: {GITHUB_USERNAME}/{repo_name}")
        subprocess.run(["git", "push", "-u", "origin", "main"], cwd=local_repo_path, check=True)
        commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=local_repo_path).decode().strip()
        repo_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}"
        print(f"<<< GitHub BUILD process complete.")
        return {"repo_url": repo_url, "commit_sha": commit_sha}
    except Exception as e:
        print(f"!!! GitHub BUILD Process Failed: {e} !!!")
        return None


def update_and_redeploy_repo(task_id, brief, checks):
    """Clones, updates, and pushes changes to an existing repo."""
    print(f">>> Starting REVISE process for repo: {task_id}")
    repo_name = task_id
    local_repo_path = os.path.join(os.getcwd(), repo_name)
    repo_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}"
    try:
        if os.path.exists(local_repo_path):
            subprocess.run(f"rmdir /s /q {local_repo_path}", shell=True, check=False)
        subprocess.run(["git", "clone", f"{repo_url}.git", local_repo_path], check=True)
        current_code = {}
        for filename in ["index.html", "style.css", "script.js"]:
            with open(os.path.join(local_repo_path, filename), "r", encoding="utf-8") as f:
                current_code[filename] = f.read()
        update_prompt = f"""
        You are a JSON generation API modifying an existing web app. Respond with only a single, raw, valid JSON object.
        Modification Request: {brief}
        Requirements: {" ".join(checks)}
        CURRENT Code: {json.dumps(current_code, indent=2)}
        Return a JSON object with the complete, new code for "index.html", "style.css", and "script.js".
        """
        updated_code_json = generate_code_with_llm(update_prompt)
        if not updated_code_json: raise Exception("LLM failed to generate updated code.")
        start_index = updated_code_json.find('{')
        end_index = updated_code_json.rfind('}') + 1
        clean_json_string = updated_code_json[start_index:end_index]
        updated_code = json.loads(clean_json_string)
        for filename, content in updated_code.items():
            with open(os.path.join(local_repo_path, filename), "w", encoding="utf-8") as f:
                f.write(content)
        subprocess.run(["git", "add", "."], cwd=local_repo_path, check=True)
        subprocess.run(["git", "commit", "-m", f"Apply updates for Round 2"], cwd=local_repo_path, check=True)
        subprocess.run(["git", "push"], cwd=local_repo_path, check=True)
        commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=local_repo_path).decode().strip()
        pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"
        print(f"<<< REVISE process complete.")
        return {"repo_url": repo_url, "commit_sha": commit_sha, "pages_url": pages_url}
    except Exception as e:
        print(f"!!! REVISE Process Failed: {e} !!!")
        return None


def enable_github_pages(repo_name):
    """Enables GitHub Pages for a repository."""
    print(f">>> Enabling GitHub Pages for {repo_name}...")
    try:
        # Use the system-wide 'gh' installed by the Dockerfile
        pages_command = ["gh", "api", "--method", "POST", f"repos/{GITHUB_USERNAME}/{repo_name}/pages", "-f", "build_type=workflow", "-f", "source[branch]=main", "-f", "source[path]=/"]
        env = os.environ.copy()
        env["GITHUB_TOKEN"] = GITHUB_TOKEN
        subprocess.run(pages_command, check=True, env=env, capture_output=True)
        time.sleep(5)
        print(f"<<< GitHub Pages enabled successfully.")
        return True
    except subprocess.CalledProcessError as e:
        if "is already enabled" in e.stderr.decode():
            print("   - Warning: GitHub Pages is already enabled. Continuing...")
            return True
        else:
            print(f"!!! Failed to enable GitHub Pages: {e.stderr.decode()} !!!")
            return False


def notify_evaluation_server(github_details, request_data):
    """Sends the final notification payload."""
    print(f">>> Notifying evaluation server...")
    try:
        payload = {
            "email": request_data["email"], "task": request_data["task"], "round": request_data["round"],
            "nonce": request_data["nonce"], "repo_url": github_details["repo_url"],
            "commit_sha": github_details["commit_sha"], "pages_url": github_details["pages_url"]
        }
        response = requests.post(request_data["evaluation_url"], json=payload)
        response.raise_for_status()
        print(f"<<< Notification sent successfully!")
        return True
    except requests.exceptions.RequestException as e:
        print(f"!!! Notification failed: {e} !!!")
        return False


@app.route('/api-endpoint', methods=['POST'])
def handle_request():
    """Main webhook to handle both 'Build' and 'Revise' requests."""
    data = request.get_json()
    if not data or data.get("secret") != MY_SECRET:
        return jsonify({"status": "error", "message": "Invalid or missing secret"}), 403

    try:
        if data["round"] == 1:
            print("\n--- Received ROUND 1 (Build) Request ---")
            build_prompt = f"""
            You are a JSON generation API. Respond with only a single, raw, valid JSON object.
            Application Brief: {data['brief']}
            Requirements: {" ".join(data['checks'])}
            Return a JSON object with keys for "index.html", "style.css", and "script.js" containing the complete code.
            """
            code_json = generate_code_with_llm(build_prompt)
            if not code_json: return jsonify({"status": "error", "message": "Failed to generate code"}), 500
            
            github_details = create_and_push_to_github(data["task"], code_json)
            if not github_details: return jsonify({"status": "error", "message": "Failed to create GitHub repo"}), 500
            
            if not enable_github_pages(data["task"]):
                return jsonify({"status": "error", "message": "Failed to enable GitHub Pages"}), 500
            
            github_details["pages_url"] = f"https://{GITHUB_USERNAME}.github.io/{data['task']}/"
            if not notify_evaluation_server(github_details, data):
                return jsonify({"status": "error", "message": "Failed to send notification"}), 500

            return jsonify({"status": "success", "message": "Build complete and notification sent!"}), 200
        else: # Handle Round 2
            print("\n--- Received ROUND 2 (Revise) Request ---")
            github_details = update_and_redeploy_repo(data["task"], data["brief"], data["checks"])
            if not github_details: return jsonify({"status": "error", "message": "Failed to update GitHub repo"}), 500

            if not notify_evaluation_server(github_details, data):
                return jsonify({"status": "error", "message": "Failed to send revision notification"}), 500

            return jsonify({"status": "success", "message": "Revise complete and notification sent!"}), 200
    except Exception as e:
        print(f"An unexpected error occurred in handle_request: {e}")
        return jsonify({"status": "error", "message": "An internal server error occurred"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)