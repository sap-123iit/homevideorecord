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

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DRIVE_FOLDER_ID = '1CJrUKBOuEAD7RO0TdDHp_JkvE777xeE0'
CLIENT_SECRET_FILE = os.path.join(SCRIPT_DIR, "client_secret_134126426415-qiestm7bd4t60hpp1c4a5eeicnq2u934.apps.googleusercontent.com.json")
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")
SCOPES = ['https://www.googleapis.com/auth/drive']
UPLOADED_LOG_FILE = os.path.join(SCRIPT_DIR, "uploaded_files.txt")
RECORDED_LIST_FILE = os.path.join(SCRIPT_DIR, "recordedvideolist.txt")
MIN_FILE_SIZE_KB = 700
UPLOAD_INTERVAL = 300  # every 5 minutes
FILE_PATTERN = re.compile(r'recording_(\d{8})_\d{6}\.mp4$')

# UI label reference
status_label = None

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

def verify_folder_access(service):
    try:
        folder = service.files().get(fileId=DRIVE_FOLDER_ID, fields='id, name', supportsAllDrives=True).execute()
        print(f"Folder found: {folder['name']}")
        return True
    except HttpError as e:
        print(f"Access error: {e}")
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
        print(f"Error creating folder: {e}")
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
    with open(UPLOADED_LOG_FILE, 'a') as f:
        f.write(f"{file_name}\n")

def upload_file(service, file_path, parent_id, retries=3):
    file_name = os.path.basename(file_path)
    file_metadata = {'name': file_name, 'parents': [parent_id]}
    media = MediaFileUpload(file_path, mimetype='video/mp4')
    for attempt in range(1, retries + 1):
        try:
            file = service.files().create(body=file_metadata, media_body=media, fields='id', supportsAllDrives=True).execute()
            print(f"Uploaded {file_name}")
            return file.get('id')
        except HttpError as e:
            print(f"Upload attempt {attempt} failed: {e}")
            if attempt < retries:
                time.sleep(5)
    return None

def run_upload():
    global status_label
    service = authenticate_drive()
    if not verify_folder_access(service):
        print("Cannot access folder. Exiting.")
        return

    while True:
        status_label.config(text="Uploading...", fg="green")
        recorded_set = load_recorded_list()
        uploaded_set = load_uploaded_log()

        files_uploaded = False
        for file_name in os.listdir(LOCAL_FOLDER):
            if FILE_PATTERN.match(file_name) and file_name in recorded_set and file_name not in uploaded_set:
                file_path = os.path.join(LOCAL_FOLDER, file_name)
                size_kb = os.path.getsize(file_path) / 1024
                if size_kb < MIN_FILE_SIZE_KB:
                    print(f"Deleting corrupt file: {file_name}")
                    os.remove(file_path)
                    continue

                date_str = FILE_PATTERN.match(file_name).group(1)
                subfolder_id = get_or_create_subfolder(service, DRIVE_FOLDER_ID, date_str)
                if not subfolder_id:
                    continue

                upload_id = upload_file(service, file_path, subfolder_id)
                if upload_id:
                    try:
                        os.remove(file_path)
                        append_to_log(file_name)
                        print(f"Uploaded and deleted: {file_name}")
                        files_uploaded = True
                    except Exception as e:
                        print(f"Error deleting {file_name}: {e}")
                else:
                    print(f"Upload failed for {file_name}, skipping to next cycle.")
                    break

        status_label.config(text="Waiting for next upload cycle", fg="red")
        if files_uploaded:
            print("Cycle completed, waiting for next interval.")
        time.sleep(UPLOAD_INTERVAL)

def start_ui():
    global status_label
    root = tk.Tk()
    root.title("Video Upload Status")
    root.geometry("300x100")
    status_label = tk.Label(root, text="Initializing...", font=("Arial", 14))
    status_label.pack(expand=True)
    threading.Thread(target=run_upload, daemon=True).start()
    root.mainloop()

if __name__ == "__main__":
    start_ui()
