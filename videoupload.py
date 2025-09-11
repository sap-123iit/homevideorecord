import os
import re
import time
import threading
import tkinter as tk
from tkinter import messagebox
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Resolve script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Configuration with absolute paths
LOCAL_FOLDER = os.path.join(SCRIPT_DIR, "homevideo")
DRIVE_FOLDER_ID = '1CJrUKBOuEAD7RO0TdDHp_JkvE777xeE0'
CLIENT_SECRET_FILE = os.path.join(LOCAL_FOLDER, "client_secret_134126426415-qiestm7bd4t60hpp1c4a5eeicnq2u934.apps.googleusercontent.com.json")
TOKEN_FILE = os.path.join(LOCAL_FOLDER, "token.json")
SCOPES = ['https://www.googleapis.com/auth/drive']
UPLOADED_LOG_FILE = os.path.join(SCRIPT_DIR, "uploaded_files.txt")
RECORDED_LIST_FILE = os.path.join(LOCAL_FOLDER, 'recordedvideolist.txt')
MIN_FILE_SIZE_KB = 700
FILE_PATTERN = re.compile(r'recording_(\d{8})_\d{6}\.mp4')

def authenticate_drive():
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
    try:
        folder = service.files().get(fileId=folder_id, fields='id, name', supportsAllDrives=True).execute()
        print(f"Folder found: {folder['name']} (ID: {folder['id']})")
        return True
    except HttpError as e:
        print(f"Error accessing folder {folder_id}: {e}")
        return False

def get_or_create_subfolder(service, parent_id, folder_name):
    query = f"name='{folder_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    try:
        results = service.files().list(q=query, fields="files(id, name)", supportsAllDrives=True).execute()
        folders = results.get('files', [])
        if folders:
            return folders[0]['id']
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        folder = service.files().create(body=file_metadata, fields='id', supportsAllDrives=True).execute()
        return folder.get('id')
    except HttpError as e:
        print(f"Error getting/creating folder '{folder_name}': {e}")
        return None

def load_recorded_list():
    if not os.path.exists(RECORDED_LIST_FILE):
        return set()
    with open(RECORDED_LIST_FILE, 'r') as f:
        return set(line.strip() for line in f if line.strip())

def load_uploaded_log():
    if not os.path.exists(UPLOADED_LOG_FILE):
        open(UPLOADED_LOG_FILE, 'w').close()
        return set()
    with open(UPLOADED_LOG_FILE, 'r') as f:
        return set(line.strip() for line in f if line.strip())

def append_to_log(file_name):
    try:
        with open(UPLOADED_LOG_FILE, 'a') as f:
            f.write(f"{file_name}\n")
    except Exception as e:
        print(f"Error writing log: {e}")

def upload_file(service, file_path, parent_id, retries=3):
    file_name = os.path.basename(file_path)
    file_metadata = {
        'name': file_name,
        'parents': [parent_id]
    }
    media = MediaFileUpload(file_path, mimetype='video/mp4')

    for attempt in range(1, retries + 1):
        try:
            file = service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=True).execute()
            print(f"Uploaded {file_name} (Drive ID: {file.get('id')})")
            return file.get('id')
        except HttpError as e:
            print(f"Attempt {attempt} failed for {file_name}: {e}")
            if attempt < retries:
                time.sleep(5)
            else:
                return None

def run_upload():
    service = authenticate_drive()

    if not verify_folder_access(service, DRIVE_FOLDER_ID):
        print("Cannot access Drive folder. Exiting.")
        return

    recorded_set = load_recorded_list()
    uploaded_set = load_uploaded_log()

    for file_name in os.listdir(LOCAL_FOLDER):
        match = FILE_PATTERN.match(file_name)
        if match:
            if file_name in recorded_set and file_name not in uploaded_set:
                file_path = os.path.join(LOCAL_FOLDER, file_name)
                file_size_kb = os.path.getsize(file_path) / 1024
                if file_size_kb < MIN_FILE_SIZE_KB:
                    try:
                        os.remove(file_path)
                        print(f"Deleted corrupt file: {file_name}")
                    except Exception as e:
                        print(f"Error deleting {file_name}: {e}")
                    continue

                date_str = match.group(1)
                subfolder_id = get_or_create_subfolder(service, DRIVE_FOLDER_ID, date_str)
                if not subfolder_id:
                    continue

                upload_id = upload_file(service, file_path, subfolder_id)
                if upload_id:
                    try:
                        os.remove(file_path)
                        append_to_log(file_name)
                        print(f"Uploaded and logged {file_name}, local file deleted.")
                    except Exception as e:
                        print(f"Error deleting {file_name}: {e}")
                else:
                    print(f"Upload failed for {file_name}. Exiting.")
                    return

def start_ui():
    """Start a simple Tkinter UI showing upload is running."""
    root = tk.Tk()
    root.title("Video Upload Status")
    root.geometry("250x100")
    label = tk.Label(root, text="Uploading... Running", font=("Arial", 14), fg="green")
    label.pack(expand=True)
    # Prevent resizing
    root.resizable(False, False)
    # Close window handler
    def on_close():
        if messagebox.askokcancel("Quit", "Do you want to quit the uploader?"):
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)
    return root

if __name__ == '__main__':
    try:
        # Start the Tkinter UI in the main thread
        app = start_ui()

        # Run upload in a separate thread so the UI stays responsive
        upload_thread = threading.Thread(target=run_upload, daemon=True)
        upload_thread.start()

        app.mainloop()
    except Exception as e:
        print(f"Unexpected error: {e}")
