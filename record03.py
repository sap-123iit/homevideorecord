import cv2
import time
import os
import subprocess
from datetime import datetime
import tkinter as tk
import threading

# -------------------- Global variables for GUI --------------------
recording_status = False
streams_status = [False, False, False, False]

# -------------------- Configuration --------------------
output_folder = "/home/pi/homevideo"
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

RECORDED_LIST_FILE = os.path.join(output_folder, 'recordedvideolist.txt')
TARGET_WIDTH = 480
TARGET_HEIGHT = 270
FPS_CAP = 15.0
DURATION = 180          # 3 minutes
ERROR_WAIT = 120        # 2 minutes on error
FOURCC = cv2.VideoWriter_fourcc(*'mp4v')

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

# Start the GUI in a separate thread
status_thread = threading.Thread(target=run_status_window, daemon=True)
status_thread.start()

# -------------------- Helper Functions --------------------
def append_to_recorded_list(filename):
    try:
        with open(RECORDED_LIST_FILE, 'a') as f:
            f.write(f"{filename}\n")
        print(f"Appended {filename} to {RECORDED_LIST_FILE}")
    except Exception as e:
        print(f"Error appending {filename}: {e}")

def compress_with_ffmpeg(input_file):
    compressed_file = input_file.replace("_ongoing.mp4", ".mp4")
    try:
        subprocess.run([
            "/usr/bin/ffmpeg", "-y", "-i", input_file,
            "-vcodec", "libx264", "-crf", "28", "-preset", "veryfast",
            "-an",
            compressed_file
        ], check=True)

        original_size = os.path.getsize(input_file)
        compressed_size = os.path.getsize(compressed_file)

        if compressed_size < original_size:
            os.remove(input_file)
            print(f"Compression successful, renamed to {compressed_file}")
            return compressed_file
        else:
            print("Compression did not reduce file size; keeping original.")
            os.remove(compressed_file)
            return None

    except Exception as e:
        print(f"FFmpeg compression failed for {input_file}: {e}")
        if os.path.exists(compressed_file):
            os.remove(compressed_file)
        return None

def initialize_captures():
    cap1 = cv2.VideoCapture('rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/101')
    cap2 = cv2.VideoCapture('rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/201')
    cap3 = cv2.VideoCapture('rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/301')
    cap4 = cv2.VideoCapture('rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/401')
    if not (cap1.isOpened() and cap2.isOpened() and cap3.isOpened() and cap4.isOpened()):
        print("Error: Could not open one or more RTSP streams.")
        for cap in [cap1, cap2, cap3, cap4]:
            if cap.isOpened():
                cap.release()
        return None, None, None, None
    return cap1, cap2, cap3, cap4

# -------------------- Main Recording Function --------------------
def record_and_stitch():
    global recording_status, streams_status
    while True:
        cap1, cap2, cap3, cap4 = initialize_captures()
        streams = [cap1, cap2, cap3, cap4]
        streams_status = [cap.isOpened() for cap in streams]

        if not all(streams_status):
            print(f"Error: One or more streams failed.")
            recording_status = False
            for cap in streams:
                if cap and cap.isOpened():
                    cap.release()
            print(f"Waiting {ERROR_WAIT} seconds before retrying...")
            time.sleep(ERROR_WAIT)
            continue

        recording_status = True

        fps = cap1.get(cv2.CAP_PROP_FPS)
        if fps == 0 or fps > FPS_CAP:
            fps = FPS_CAP

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ongoing_filename = os.path.join(output_folder, f"recording_{timestamp}_ongoing.mp4")
        out = cv2.VideoWriter(ongoing_filename, FOURCC, fps, (TARGET_WIDTH * 2, TARGET_HEIGHT * 2))

        if not out.isOpened():
            print("Error: Unable to open VideoWriter")
            recording_status = False
            for cap in streams:
                cap.release()
            print(f"Waiting {ERROR_WAIT} seconds before retrying...")
            time.sleep(ERROR_WAIT)
            continue

        start_time = time.time()
        print(f"Starting recording: {ongoing_filename}")
        capture_success = True
        target_frame_time = 1 / fps

        while (time.time() - start_time) < DURATION:
            frame_start = time.time()

            ret1, frame1 = cap1.read()
            ret2, frame2 = cap2.read()
            ret3, frame3 = cap3.read()
            ret4, frame4 = cap4.read()
            if not (ret1 and ret2 and ret3 and ret4):
                print("Error: Failed to capture frame from one or more streams.")
                capture_success = False
                break

            frame1 = cv2.resize(frame1, (TARGET_WIDTH, TARGET_HEIGHT))
            frame2 = cv2.resize(frame2, (TARGET_WIDTH, TARGET_HEIGHT))
            frame3 = cv2.resize(frame3, (TARGET_WIDTH, TARGET_HEIGHT))
            frame4 = cv2.resize(frame4, (TARGET_WIDTH, TARGET_HEIGHT))

            top_row = cv2.hconcat([frame1, frame2])
            bottom_row = cv2.hconcat([frame3, frame4])
            combined_frame = cv2.vconcat([top_row, bottom_row])
            out.write(combined_frame)

            elapsed = time.time() - frame_start
            sleep_time = max(0, target_frame_time - elapsed)
            time.sleep(sleep_time)

        out.release()
        for cap in streams:
            cap.release()

        cv2.destroyAllWindows()
        recording_status = False

        if not capture_success:
            print(f"Capture failed, deleting {ongoing_filename}")
            if os.path.exists(ongoing_filename):
                os.remove(ongoing_filename)
            print(f"Waiting {ERROR_WAIT} seconds before retrying...")
            time.sleep(ERROR_WAIT)
            continue

        compressed_file = compress_with_ffmpeg(ongoing_filename)
        if compressed_file:
            append_to_recorded_list(os.path.basename(compressed_file))
        else:
            print(f"Compression did not succeed in reducing size; keeping {ongoing_filename}")

# -------------------- Main Entry Point --------------------
if __name__ == "__main__":
    try:
        record_and_stitch()
    except KeyboardInterrupt:
        print("Recording stopped by user.")
        cv2.destroyAllWindows()
