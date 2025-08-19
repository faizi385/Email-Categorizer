import os
import pickle
import base64
import json
import pandas as pd
import google.generativeai as genai
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from email.mime.text import MIMEText
import time
from datetime import datetime

GEMINI_API_KEY = ""

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
TEMPLATE_FILE = 'templates.json'

def gmail_authenticate():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=8080)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return build('gmail', 'v1', credentials=creds)

def get_part(parts, mime_type='text/plain'):
    for part in parts:
        if part.get('mimeType') == mime_type and part.get('body') and part.get('body').get('data'):
            return part.get('body').get('data')
        if 'parts' in part:
            data = get_part(part['parts'], mime_type)
            if data:
                return data
    return None

def get_email_body(msg_payload):
    if 'parts' in msg_payload:
        data = get_part(msg_payload['parts'], 'text/plain')
        if data:
            return base64.urlsafe_b64decode(data).decode('utf-8', 'ignore')
    elif 'body' in msg_payload and 'data' in msg_payload['body']:
        data = msg_payload['body']['data']
        return base64.urlsafe_b64decode(data).decode('utf-8', 'ignore')
    return ""

def get_emails(service, max_results=10):
    results = service.users().messages().list(userId='me', labelIds=['INBOX'], q="is:unread", maxResults=max_results).execute()
    messages = results.get('messages', [])
    if not messages:
        return pd.DataFrame()

    email_data = []
    for msg in messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
        headers = msg_data['payload'].get('headers', [])
        subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
        sender = next((h['value'] for h in headers if h['name'] == 'From'), '')
        body = get_email_body(msg_data['payload'])
        if body:
            email_data.append({'id': msg['id'], 'threadId': msg_data['threadId'], 'subject': subject, 'from': sender, 'body': body})
    return pd.DataFrame(email_data)




def load_templates():
    if os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_templates(templates):
    with open(TEMPLATE_FILE, 'w') as f:
        json.dump(templates, f, indent=2)
def generate_ai_response(email_subject, email_body):
    if GEMINI_API_KEY == "YOUR_GEMINI_API_KEY":
        print("ERROR: Please add your Gemini API key to the script.")
        return None

    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

    templates = load_templates()

    prompt = f"""
    You are an intelligent email classification and reply assistant.

    Analyze the email content carefully and choose a **category that best describes this email**.
    Do not limit yourself to predefined categories; create a meaningful category name if needed.

    Generate a professional reply.
    Suggest a reply subject starting with "Re:".

    Respond ONLY in valid JSON format:

    {{
      "category": "AI-decided category name",
      "reply_subject": "Re: ...",
      "reply_body": "Full reply here"
    }}

    Email Subject: {email_subject}
    Email Body: {email_body}
    """

    try:
        response = model.generate_content(prompt)
        cleaned_response = response.text.strip().replace('```json', '').replace('```', '').strip()
        ai_data = json.loads(cleaned_response)

        category = ai_data.get("category")

        if category not in templates:
            new_template = {
                "subject": ai_data.get("reply_subject", f"Re: {email_subject}"),
                "body": ai_data.get("reply_body", "Thank you for your email. We will get back to you shortly.")
            }
            templates[category] = new_template
            save_templates(templates)
            print(f"🆕 New template created for category: {category}")

        return ai_data

    except Exception as e:
        print(f"Error generating AI response: {e}")
        return None

def create_draft(service, thread_id, to, subject, body):
    """Create a Gmail draft instead of sending the email directly."""
    message = MIMEText(body)
    message['to'] = to
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    draft = {
        'message': {
            'raw': raw,
            'threadId': thread_id
        }
    }

    try:
        draft_response = service.users().drafts().create(userId='me', body=draft).execute()
        print(f"✅ Draft created: {draft_response['id']}")
        return True
    except Exception as e:
        print(f"❌ Could not create draft for {to}: {e}")
        return False

def main():
    service = gmail_authenticate()
    df = get_emails(service)
    
    if df.empty:
        print('No new unread emails found.')
        return

    print(f"Found {len(df)} new emails to process.")

    for _, row in df.iterrows():
        print(f"\n--- Processing email from: {row['from']} ---")
        ai_response = generate_ai_response(row['subject'], row['body'])

        if ai_response:
            category = ai_response.get('category', 'Uncategorized')
            subject = ai_response.get('reply_subject', f"Re: {row['subject']}")
            body = ai_response.get('reply_body', "Sorry, I could not generate a response.")
            
            print(f"AI Category: {category}")
            success = create_draft(service, row['threadId'], row['from'], subject, body)

            if success:
                print("Draft created successfully. Please review and send it manually.")
                service.users().messages().modify(
                    userId='me',
                    id=row['id'],
                    body={'removeLabelIds': ['UNREAD']}
                ).execute()
                print("Marked email as read.")
        else:
            print("Could not generate AI response for this email.")


def schedule_email_check():
    check_interval = 300 
    
    print("Starting email checking service...")
    print(f"Will check for new emails every {check_interval//60} minutes")
    
    while True:
        try:
            print(f"\n{'='*50}")
            print(f"Checking emails at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*50}")
            

            main()
            

            time.sleep(check_interval)
            
        except KeyboardInterrupt:
            print("\nStopping email checking service...")
            break
        except Exception as e:
            print(f"An error occurred: {str(e)}")
            print("Will retry in 1 minute...")
            time.sleep(60)  

if __name__ == '__main__':
    schedule_email_check()
