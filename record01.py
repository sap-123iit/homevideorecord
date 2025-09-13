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

# RTSP URLs for each stream
STREAM_URLS = [
    'rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/101',
    'rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/201',
    'rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/301',
    'rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/401'
]

# Use hardware encoder if available: "h264_omx", "h264_v4l2m2m", etc.
VIDEO_CODEC = "h264_omx"
BITRATE = "1M"  # Adjust as needed

# Duration for each recording chunk in seconds
DURATION = 180  # 3 minutes

# -------------------- Global state for GUI --------------------
recording_status = False
streams_status = [False, False, False, False]

# -------------------- Tkinter GUI --------------------
def run_status_window():
    global recording_status, streams_status

    window = tk.Tk()
    window.title("Recording Status")
    window.geometry("300x250")

    recording_label = tk.Label(window, text="Not Recording", fg="red", font=("Helvetica", 16))
    recording_label.pack(pady=10)

    stream_labels = []
    for i in range(4):
        lbl = tk.Label(window, text=f"Stream {i+1}: Unknown", font=("Helvetica", 12))
        lbl.pack()
        stream_labels.append(lbl)

    def update_labels():
        if recording_status:
            recording_label.config(text="Recording", fg="green")
        else:
            recording_label.config(text="Not Recording", fg="red")

        for i in range(4):
            if streams_status[i]:
                stream_labels[i].config(text=f"Stream {i+1}: OK", fg="green")
            else:
                stream_labels[i].config(text=f"Stream {i+1}: Disconnected", fg="red")

        window.after(1000, update_labels)

    update_labels()
    window.mainloop()

# Start GUI in a separate thread
status_thread = threading.Thread(target=run_status_window, daemon=True)
status_thread.start()

# -------------------- Recording logic --------------------
def get_output_filename(index):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(output_folder, f"stream{index+1}_{timestamp}.mp4")

def start_recording(stream_url, output_file):
    command = [
        "ffmpeg",
        "-rtsp_transport", "tcp",
        "-i", stream_url,
        "-c:v", VIDEO_CODEC,
        "-b:v", BITRATE,
        "-t", str(DURATION),
        "-f", "mp4",
        output_file
    ]
    return subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def record_all_streams():
    global recording_status, streams_status
    while True:
        processes = []
        output_files = []

        # Start processes for all streams
        for i, url in enumerate(STREAM_URLS):
            output_file = get_output_filename(i)
            try:
                proc = start_recording(url, output_file)
                processes.append(proc)
                output_files.append(output_file)
                streams_status[i] = True
                print(f"Started recording stream {i+1} -> {output_file}")
            except Exception as e:
                print(f"Failed to start stream {i+1}: {e}")
                streams_status[i] = False

        if not any(streams_status):
            print("All streams failed. Retrying in 10 seconds...")
            recording_status = False
            time.sleep(10)
            continue

        recording_status = True

        # Wait for all processes to complete
        for i, proc in enumerate(processes):
            proc.wait()
            if proc.returncode != 0:
                print(f"Stream {i+1} ended with error code {proc.returncode}")
                streams_status[i] = False
            else:
                print(f"Stream {i+1} recording completed.")

        recording_status = False

        print("All streams completed. Waiting before next round...")
        time.sleep(5)

# -------------------- Main --------------------
if __name__ == "__main__":
    try:
        record_all_streams()
    except KeyboardInterrupt:
        print("Recording stopped by user.")
