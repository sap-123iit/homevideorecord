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

STREAM_URLS = [
    'rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/101',
    'rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/201',
    'rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/301',
    'rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/401'
]

VIDEO_CODEC = "h264_omx"  # or "h264_v4l2m2m"
BITRATE = "1M"
DURATION = 150  # 2.5 minutes
BUFFER_WAIT = 2  # seconds to wait between rounds if something fails

# -------------------- Global state --------------------
recording_status = False
streams_status = [False, False, False, False]
stop_flag = False

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

# Start GUI thread
status_thread = threading.Thread(target=run_status_window, daemon=True)
status_thread.start()

# -------------------- Helper functions --------------------
def get_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def get_chunk_folder(timestamp):
    path = os.path.join(output_folder, timestamp)
    if not os.path.exists(path):
        os.makedirs(path)
    return path

def get_output_filename(timestamp):
    return os.path.join(output_folder, f"recording_{timestamp}_ongoing.mp4")

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

def stitch_videos(video_files, output_file):
    # Create a temporary file list for ffmpeg
    list_file = os.path.join(output_folder, "files.txt")
    with open(list_file, "w") as f:
        for file in video_files:
            f.write(f"file '{file}'\n")

    command = [
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-i", list_file,
        "-c", "copy",
        output_file
    ]
    try:
        subprocess.run(command, check=True)
        print(f"Stitched video saved to {output_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error stitching videos: {e}")
    finally:
        if os.path.exists(list_file):
            os.remove(list_file)

# -------------------- Recording logic --------------------
def record_all_streams():
    global recording_status, streams_status, stop_flag
    while not stop_flag:
        timestamp = get_timestamp()
        chunk_folder = get_chunk_folder(timestamp)
        output_file = get_output_filename(timestamp)

        # Prepare file names for each stream
        stream_files = []
        for i in range(4):
            file_path = os.path.join(chunk_folder, f"stream{i+1}_{timestamp}.mp4")
            stream_files.append(file_path)

        processes = []
        streams_status = [False, False, False, False]
        recording_status = True

        # Start recording all streams
        for i, url in enumerate(STREAM_URLS):
            try:
                proc = start_recording(url, stream_files[i])
                processes.append(proc)
                streams_status[i] = True
                print(f"Started recording stream {i+1} -> {stream_files[i]}")
            except Exception as e:
                print(f"Failed to start stream {i+1}: {e}")
                streams_status[i] = False

        if not any(streams_status):
            print("All streams failed to start. Retrying after wait.")
            recording_status = False
            time.sleep(BUFFER_WAIT)
            continue

        # Wait for all processes to finish
        for i, proc in enumerate(processes):
            proc.wait()
            if proc.returncode != 0:
                print(f"Stream {i+1} ended with error code {proc.returncode}")
                streams_status[i] = False
            else:
                print(f"Stream {i+1} completed recording.")

        # Stitch the videos together
        print("Stitching videos...")
        stitch_videos(stream_files, output_file)
        print(f"Saved stitched video: {output_file}")

        recording_status = False

        # Wait before starting the next chunk
        time.sleep(BUFFER_WAIT)

# -------------------- Main --------------------
if __name__ == "__main__":
    try:
        record_all_streams()
    except KeyboardInterrupt:
        print("Recording stopped by user.")
        stop_flag = True
        time.sleep(1)
