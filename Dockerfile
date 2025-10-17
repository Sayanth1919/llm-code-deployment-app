# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# --- THIS IS THE FIX: Install git, curl, and gnupg all at once ---
RUN apt-get update && apt-get install -y git curl gnupg

# Install the GitHub CLI (gh)
RUN curl -fsSL https://cli.github.com/packages/github-cli-archive-keyring.gpg | dd of=/usr/share/keyrings/github-cli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/github-cli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/github-cli-archive-keyring.gpg] https://cli.github.com/packages stable main" | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y gh

# Copy the requirements file and install Python dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container
COPY . .

# Tell Gunicorn to run your app
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]