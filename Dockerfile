# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# --- THIS IS THE FIX ---
# Install git and curl, which are essential prerequisites.
RUN apt-get update && apt-get install -y git curl

# Manually download, extract, and install the GitHub CLI (gh) binary.
# This is a much more reliable method than the official script.
RUN curl -sSL https://github.com/cli/cli/releases/download/v2.50.0/gh_2.50.0_linux_amd64.tar.gz -o gh.tar.gz \
    && tar -xf gh.tar.gz \
    && mv gh_2.50.0_linux_amd64/bin/gh /usr/local/bin/gh \
    && rm -rf gh.tar.gz gh_2.50.0_linux_amd64

# Copy the requirements file and install Python dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container
COPY . .

# Tell Gunicorn to run your app
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "app:app"]