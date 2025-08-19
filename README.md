# Email Auto Categorizer and Responder

This project reads your Gmail inbox, automatically categorizes emails, generates category-based templates, and sends automatic responses.

## Setup
1. Place your Gmail API `credentials.json` in this folder.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the script:
   ```bash
   python main.py
   ```
## What it does
- Reads your inbox
- Categorizes emails using ML
- Generates response templates for each category
- Sends replies automatically

**Note:** The first run will open a browser to authenticate your Gmail account.


## Docker
- View logs: docker logs -f email-automation
- Stop the service: docker stop email-automation
- Start the service: docker start email-automation
- Remove the container: docker rm -f email-automation

- Place your Gmail API credentials.json in a credentials directory:
mkdir -p credentials
cp credentials.json credentials/

- Build the Docker image:
docker build -t email-categories .

- Run the container:
docker run -d \
  --name email-automation \
  -v $(pwd)/credentials:/app/credentials \
  email-categories
