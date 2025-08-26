import os
import re
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Configuration
LOCAL_FOLDER = r"/home/pi/homevideo"  # Path to your local folder with MP4 files
DRIVE_FOLDER_ID = '1CJrUKBOuEAD7RO0TdDHp_JkvE777xeE0'  # Main shared folder ID in Shared Drive
CLIENT_SECRET_FILE = r"/home/pi/homevideo/client_secret_134126426415-qiestm7bd4t60hpp1c4a5eeicnq2u934.apps.googleusercontent.com.json"  # Path to OAuth 2.0 client secret JSON
TOKEN_FILE = r'/home/pi/homevideo/token.json'  # Path to store OAuth token
SCOPES = ['https://www.googleapis.com/auth/drive']  # Scope for Drive access
LOG_FILE = os.path.join(LOCAL_FOLDER, 'uploaded_files.log')  # Log file for uploaded files
RECORDED_LIST_FILE = os.path.join(LOCAL_FOLDER, 'recordedvideolist.txt')  # File listing recorded videos
MIN_FILE_SIZE_KB = 700  # Minimum file size in KB to consider a file valid

# File name pattern: recording_YYYYMMDD_HHMMSS.mp4
FILE_PATTERN = re.compile(r'recording_(\d{8})_\d{6}\.mp4')

def authenticate_drive():
    """Authenticate and return the Drive service using OAuth 2.0."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    
    return build('drive', 'v3', credentials=creds)

def verify_folder_access(service, folder_id):
    """Verify that the folder exists and is accessible in the Shared Drive."""
    try:
        folder = service.files().get(
            fileId=folder_id,
            fields='id, name, parents',
            supportsAllDrives=True
        ).execute()
        print(f"Folder found: {folder['name']} (ID: {folder['id']})")
        return True
    except HttpError as e:
        print(f"Error accessing folder {folder_id}: {e}")
        return False

def get_or_create_subfolder(service, parent_id, folder_name):
    """Get the ID of a subfolder if it exists, or create it if not."""
    query = f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    try:
        results = service.files().list(
            q=query,
            fields="files(id, name)",
            supportsAllDrives=True
        ).execute()
        folders = results.get('files', [])
        if folders:
            print(f"Found existing folder '{folder_name}' with ID: {folders[0]['id']}")
            return folders[0]['id']
        
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        folder = service.files().create(
            body=file_metadata,
            fields='id',
            supportsAllDrives=True
        ).execute()
        print(f"Created new folder '{folder_name}' with ID: {folder.get('id')}")
        return folder.get('id')
    except HttpError as e:
        print(f"Error getting or creating folder '{folder_name}': {e}")
        return None

def load_recorded_list():
    """Load the list of recorded videos from recordedvideolist.txt into a set."""
    if not os.path.exists(RECORDED_LIST_FILE):
        print(f"Recorded list file not found: {RECORDED_LIST_FILE}")
        return set()
    with open(RECORDED_LIST_FILE, 'r') as f:
        return set(line.strip() for line in f if line.strip())

def load_uploaded_log():
    """Load the uploaded files from the log into a set."""
    if not os.path.exists(LOG_FILE):
        print(f"Log file not found, creating new one: {LOG_FILE}")
        open(LOG_FILE, 'w').close()
        return set()
    with open(LOG_FILE, 'r') as f:
        return set(line.strip() for line in f if line.strip())

def append_to_log(file_name):
    """Append the uploaded file name to the log."""
    try:
        with open(LOG_FILE, 'a') as f:
            f.write(f"{file_name}\n")
        print(f"Appended {file_name} to {LOG_FILE}")
    except Exception as e:
        print(f"Error appending {file_name} to {LOG_FILE}: {e}")

def upload_file(service, file_path, parent_id):
    """Upload a file to Google Drive and return the file ID if successful."""
    file_name = os.path.basename(file_path)
    file_metadata = {
        'name': file_name,
        'parents': [parent_id]
    }
    media = MediaFileUpload(file_path, mimetype='video/mp4')
    try:
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()
        print(f"Uploaded {file_name} successfully to Shared Drive folder. Drive ID: {file.get('id')}")
        return file.get('id')
    except HttpError as e:
        print(f"Error uploading {file_name}: {e}")
        return None

def main():
    service = authenticate_drive()
    
    # Verify access to the main folder
    if not verify_folder_access(service, DRIVE_FOLDER_ID):
        print(f"Cannot access folder {DRIVE_FOLDER_ID}. Please check permissions or folder ID.")
        return
    
    print("Checking for files to upload...")
    recorded_set = load_recorded_list()
    uploaded_set = load_uploaded_log()
    
    for file_name in os.listdir(LOCAL_FOLDER):
        match = FILE_PATTERN.match(file_name)
        if match:
            if file_name in recorded_set and file_name not in uploaded_set:
                file_path = os.path.join(LOCAL_FOLDER, file_name)
                # Check file size (convert bytes to KB)
                file_size_kb = os.path.getsize(file_path) / 1024
                if file_size_kb < MIN_FILE_SIZE_KB:
                    print(f"File {file_name} is too small ({file_size_kb:.2f} KB < {MIN_FILE_SIZE_KB} KB), deleting as corrupt.")
                    try:
                        os.remove(file_path)
                        print(f"Deleted corrupt file: {file_name}")
                    except Exception as e:
                        print(f"Error deleting corrupt file {file_name}: {e}")
                    continue
                
                date_str = match.group(1)  # Extract YYYYMMDD
                print(f"Processing file: {file_name} for date: {date_str}")
                
                # Get or create subfolder for the date
                subfolder_id = get_or_create_subfolder(service, DRIVE_FOLDER_ID, date_str)
                if not subfolder_id:
                    print(f"Skipping upload for {file_name} due to folder creation error.")
                    continue
                
                # Upload the file
                upload_id = upload_file(service, file_path, subfolder_id)
                if upload_id:
                    try:
                        os.remove(file_path)
                        print(f"Deleted local file: {file_name}")
                        # Append to log only after successful upload and deletion
                        append_to_log(file_name)
                    except Exception as e:
                        print(f"Error deleting {file_name}: {e}")
                        # Do not append to log if deletion fails
                else:
                    print(f"Skipping {file_name}: Upload failed.")
            else:
                print(f"Skipping {file_name}: Not in recorded list or already uploaded.")

if __name__ == '__main__':
    main()
