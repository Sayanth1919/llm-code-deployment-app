import os
import requests
import subprocess
import json
import time
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# --- SETUP (Unchanged) ---
load_dotenv()
app = Flask(__name__)

# --- CONSTANTS (Unchanged) ---
# new code
MY_SECRET = os.getenv("MY_SECRET") # Your application's secret
AIPIPE_API_KEY = os.getenv("AIPIPE_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
AIPIPE_API_URL = "https://aipipe.org/openrouter/v1/chat/completions"

# --- NOTIFICATION FUNCTION (NEW & DEDICATED) ---
def notify_evaluation_server(github_details, request_data):
    """Sends the final notification payload to the evaluation server."""
    print(f">>> Notifying evaluation server...")
    try:
        notification_payload = {
            "email": request_data["email"], "task": request_data["task"], "round": request_data["round"],
            "nonce": request_data["nonce"], "repo_url": github_details["repo_url"],
            "commit_sha": github_details["commit_sha"], "pages_url": github_details["pages_url"]
        }
        print(f"   - Sending notification to: {request_data['evaluation_url']}")
        print(f"   - Payload: {json.dumps(notification_payload, indent=2)}")

        response = requests.post(request_data["evaluation_url"], json=notification_payload)
        response.raise_for_status()
        print(f"<<< Notification sent successfully!")
        return True
    except requests.exceptions.RequestException as e:
        print(f"!!! Notification failed: {e} !!!")
        return False

# --- ENABLE PAGES FUNCTION (IMPROVED) ---
def enable_github_pages(repo_name):
    """Enables GitHub Pages for a repository. Handles the 'already enabled' error."""
    print(f">>> Enabling GitHub Pages for {repo_name}...")
    try:
        pages_command = [
            "gh", "api", "--method", "POST",
            f"repos/{GITHUB_USERNAME}/{repo_name}/pages",
            "-f", "build_type=workflow",
            "-f", "source[branch]=main", "-f", "source[path]=/"
        ]
        env = os.environ.copy()
        env["GITHUB_TOKEN"] = GITHUB_TOKEN
        # Run the command and capture its output
        subprocess.run(pages_command, check=True, env=env, capture_output=True)
        time.sleep(5) # Give GitHub a moment to process
        print(f"<<< GitHub Pages enabled successfully.")
        return True
    except subprocess.CalledProcessError as e:
        # THIS IS THE FIX: Check the error message from the command
        error_message = e.stderr.decode()
        if "is already enabled" in error_message:
            print("   - Warning: GitHub Pages is already enabled. Continuing...")
            return True # Treat this specific error as a success
        else:
            print(f"!!! Failed to enable GitHub Pages: {error_message} !!!")
            return False
    """Enables GitHub Pages for a repository. Only runs once in Round 1."""
    print(f">>> Enabling GitHub Pages for {repo_name}...")
    try:
        pages_command = ["gh", "api", "--method", "POST", f"repos/{GITHUB_USERNAME}/{repo_name}/pages", "-f", "build_type=workflow", "-f", "source[branch]=main", "-f", "source[path]=/"]
        env = os.environ.copy()
        env["GITHUB_TOKEN"] = GITHUB_TOKEN
        subprocess.run(pages_command, check=True, env=env, capture_output=True)
        time.sleep(5) # Give GitHub a moment to process
        print(f"<<< GitHub Pages enabled successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"!!! Failed to enable GitHub Pages: {e.stdout.decode()} {e.stderr.decode()} !!!")
        return False

# --- REVISE/UPDATE FUNCTION (FULL IMPLEMENTATION) ---
def update_and_redeploy_repo(task_id, brief, checks):
    """
    Clones an existing repo, uses an LLM to update the code,
    and pushes the changes to redeploy GitHub Pages.
    """
    repo_name = task_id
    local_repo_path = os.path.join(os.getcwd(), repo_name)
    repo_url = f"https://github.com/{GITHUB_USERNAME}/{repo_name}.git"

    print(f">>> Starting REVISE process for repo: {repo_name}")

    try:
        # 1. Clean up old directory and clone the existing repo from GitHub
        if os.path.exists(local_repo_path):
            subprocess.run(f"rmdir /s /q {local_repo_path}", shell=True, check=False)
        subprocess.run(["git", "clone", repo_url, local_repo_path], check=True)
        print(f"   - Cloned repo from {repo_url}")

        # 2. Read the current code from the files
        current_code = {}
        for filename in ["index.html", "style.css", "script.js"]:
            with open(os.path.join(local_repo_path, filename), "r", encoding="utf-8") as f:
                current_code[filename] = f.read()
        
        # 3. Create a new prompt for the LLM to modify the code
        update_prompt = f"""
        You are a specialized API that modifies a web application's code based on a user's request.
        Your entire response must be a single, raw, valid JSON object containing the *complete updated code* for all files.
        Do not include any conversational text, explanations, or markdown fences.

        **Modification Request:**
        {brief}

        **The updated application must satisfy these new requirements:**
        - {"\n- ".join(checks)}

        **Here is the CURRENT code for the application:**
        ```json
        {json.dumps(current_code, indent=2)}
        ```

        **JSON Output Specification:**
        - Return a JSON object with keys for "index.html", "style.css", and "script.js".
        - The value for each key must be the complete, new version of the code for that file.
        """
        
        # 4. Call the LLM to get the updated code
        print("   - Asking LLM to generate code modifications...")
        # (This uses the same generate_code_with_llm function but with a different prompt)
        updated_code_json = generate_code_with_llm(brief, checks) # Note: For simplicity, we reuse the function; the prompt is what matters.
        if not updated_code_json:
            raise Exception("LLM failed to generate updated code.")
        
        # Clean the returned JSON
        start_index = updated_code_json.find('{')
        end_index = updated_code_json.rfind('}') + 1
        clean_json_string = updated_code_json[start_index:end_index]
        updated_code = json.loads(clean_json_string)
        print("   - Received updated code from LLM.")

        # 5. Overwrite the old files with the new code
        for filename, content in updated_code.items():
            with open(os.path.join(local_repo_path, filename), "w", encoding="utf-8") as f:
                f.write(content)
        print("   - Overwrote local files with new code.")

        # 6. Commit and push the changes
        subprocess.run(["git", "add", "."], cwd=local_repo_path, check=True)
        # Check if there are any changes to commit
        status_result = subprocess.run(["git", "status", "--porcelain"], cwd=local_repo_path, capture_output=True, text=True)
        if not status_result.stdout:
            print("   - No changes detected. Skipping commit.")
            commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=local_repo_path).decode().strip()
        else:
            subprocess.run(["git", "commit", "-m", "Apply updates from Round 2 brief"], cwd=local_repo_path, check=True)
            subprocess.run(["git", "push"], cwd=local_repo_path, check=True)
            commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=local_repo_path).decode().strip()
            print(f"   - Committed and pushed changes. New commit SHA: {commit_sha}")
            
        pages_url = f"https://{GITHUB_USERNAME}.github.io/{repo_name}/"
        
        print(f"<<< REVISE process complete.")
        return {"repo_url": repo_url, "commit_sha": commit_sha, "pages_url": pages_url}

    except Exception as e:
        print(f"!!! REVISE Process Failed: {e} !!!")
        return None
    print(f">>> Starting REVISE process for repo: {task_id}")
    print(f"   - New Brief: {brief}")
    repo_url = f"https://github.com/{GITHUB_USERNAME}/{task_id}"
    commit_sha = "a_new_fake_commit_sha_for_testing" # Placeholder
    pages_url = f"https://{GITHUB_USERNAME}.github.io/{task_id}/"
    print(f"<<< REVISE process complete (simulation).")
    return {"repo_url": repo_url, "commit_sha": commit_sha, "pages_url": pages_url}

# --- GITHUB & LLM FUNCTIONS (Keep your working versions) ---
def generate_code_with_llm(brief, checks):
    # Your working function here...
    return "{\"index.html\":\"...\"}"

def create_and_push_to_github(task_id, code_json):
    # Your working function here...
    return {"repo_url": "...", "commit_sha": "..."}

# --- MAIN API ENDPOINT (MODIFIED LOGIC) ---
@app.route('/api-endpoint', methods=['POST'])
def handle_request():
    data = request.get_json()
    if not data or data.get("secret") != MY_SECRET:
        return jsonify({"status": "error", "message": "Invalid or missing secret"}), 403

    try:
        if data["round"] == 1:
            print("\n--- Received ROUND 1 (Build) Request ---")
            code_json = generate_code_with_llm(data["brief"], data["checks"])
            if not code_json: return jsonify({"status": "error", "message": "Failed to generate code"}), 500
            
            github_details = create_and_push_to_github(data["task"], code_json)
            if not github_details: return jsonify({"status": "error", "message": "Failed to create GitHub repo"}), 500
            
            if not enable_github_pages(data["task"]):
                return jsonify({"status": "error", "message": "Failed to enable GitHub Pages"}), 500
            
            github_details["pages_url"] = f"https://{GITHUB_USERNAME}.github.io/{data['task']}/"
            if not notify_evaluation_server(github_details, data):
                return jsonify({"status": "error", "message": "Failed to send notification"}), 500

            return jsonify({"status": "success", "message": "Build complete and notification sent!"}), 200

        elif data["round"] == 2:
            print("\n--- Received ROUND 2 (Revise) Request ---")
            github_details = update_and_redeploy_repo(data["task"], data["brief"], data["checks"])
            if not github_details: return jsonify({"status": "error", "message": "Failed to update GitHub repo"}), 500

            if not notify_evaluation_server(github_details, data):
                return jsonify({"status": "error", "message": "Failed to send revision notification"}), 500

            return jsonify({"status": "success", "message": "Revise complete and notification sent!"}), 200

        else:
            return jsonify({"status": "error", "message": f"Invalid round number"}), 400

    except KeyError as e:
        return jsonify({"status": "error", "message": f"Missing key: {e}"}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)