import subprocess
import time
import os
from datetime import datetime
import tkinter as tk
import threading

# -------------------- Configuration --------------------
output_folder = "/home/pi/homevideo"
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

STREAM_URL = 'rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/101'
VIDEO_CODEC = "copy"  # copy stream directly
DURATION = 150  # 2.5 minutes
BUFFER_WAIT = 2  # seconds between recordings

# -------------------- Global state --------------------
recording_status = False
stop_flag = False

# -------------------- Tkinter GUI --------------------
def run_status_window():
    global recording_status

    window = tk.Tk()
    window.title("Recording Status")
    window.geometry("250x150")

    recording_label = tk.Label(window, text="Not Recording", fg="red", font=("Helvetica", 16))
    recording_label.pack(pady=40)

    def update_label():
        if recording_status:
            recording_label.config(text="Recording", fg="green")
        else:
            recording_label.config(text="Not Recording", fg="red")
        window.after(1000, update_label)

    update_label()
    window.mainloop()

# Start GUI in separate thread
status_thread = threading.Thread(target=run_status_window, daemon=True)
status_thread.start()

# -------------------- Recording logic --------------------
def get_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def get_output_filename(timestamp):
    return os.path.join(output_folder, f"recording_{timestamp}_ongoing.ts")

def record_stream():
    global recording_status, stop_flag
    while not stop_flag:
        timestamp = get_timestamp()
        output_file = get_output_filename(timestamp)
        recording_status = True
        print(f"Starting recording: {output_file}")

        command = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-i", STREAM_URL,
            "-c:v", VIDEO_CODEC,
            "-t", str(DURATION),
            "-f", "mpegts",
            output_file
        ]

        try:
            subprocess.run(command, check=True)
            print(f"Finished recording: {output_file}")
        except subprocess.CalledProcessError as e:
            print(f"Recording failed: {e}")

        recording_status = False
        print(f"Waiting {BUFFER_WAIT} seconds before next recording...")
        time.sleep(BUFFER_WAIT)

# -------------------- Main --------------------
if __name__ == "__main__":
    try:
        record_stream()
    except KeyboardInterrupt:
        print("Recording stopped by user.")
        stop_flag = True
        time.sleep(1)
