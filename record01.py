import cv2
import time
import os
import subprocess
from datetime import datetime

# Define the output folder
output_folder = "/home/pi/homevideo"
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Path for the recorded video list file
RECORDED_LIST_FILE = os.path.join(output_folder, 'recordedvideolist.txt')

# Constants
TARGET_WIDTH = 480
TARGET_HEIGHT = 270
FPS_CAP = 15.0
DURATION = 180          # 3 minutes per chunk
ERROR_WAIT = 120        # 2 minutes wait on error
FOURCC = cv2.VideoWriter_fourcc(*'mp4v')

def append_to_recorded_list(filename):
    """Append the completed video filename to recordedvideolist.txt."""
    try:
        with open(RECORDED_LIST_FILE, 'a') as f:
            f.write(f"{filename}\n")
        print(f"Appended {filename} to {RECORDED_LIST_FILE}")
    except Exception as e:
        print(f"Error appending {filename} to {RECORDED_LIST_FILE}: {e}")

def compress_with_ffmpeg(input_file):
    """Compress video with ffmpeg and overwrite original."""
    compressed_file = input_file.replace("_ongoing.mp4", ".mp4")
    try:
        subprocess.run([
            "/usr/bin/ffmpeg", "-y", "-i", input_file,
            "-vcodec", "libx264", "-crf", "28", "-preset", "veryfast",
            "-an",
            compressed_file
        ], check=True)
        os.remove(input_file)
        print(f"Compressed and renamed: {compressed_file}")
        return compressed_file
    except Exception as e:
        print(f"FFmpeg compression failed for {input_file}: {e}")
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

def record_and_stitch():
    while True:
        cap1, cap2, cap3, cap4 = initialize_captures()
        if cap1 is None:
            print(f"Waiting {ERROR_WAIT} seconds before retrying...")
            time.sleep(ERROR_WAIT)
            continue

        fps = cap1.get(cv2.CAP_PROP_FPS)
        if fps == 0 or fps > FPS_CAP:
            fps = FPS_CAP

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ongoing_filename = os.path.join(output_folder, f"recording_{timestamp}_ongoing.mp4")
        out = cv2.VideoWriter(ongoing_filename, FOURCC, fps, (TARGET_WIDTH * 2, TARGET_HEIGHT * 2))

        if not out.isOpened():
            print("Error: Unable to open VideoWriter")
            for cap in [cap1, cap2, cap3, cap4]:
                cap.release()
            print(f"Waiting {ERROR_WAIT} seconds before retrying...")
            time.sleep(ERROR_WAIT)
            continue

        start_time = time.time()
        print(f"Starting recording: {ongoing_filename}")
        capture_success = True

        while (time.time() - start_time) < DURATION:
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

            cv2.imshow('Recording', combined_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                capture_success = False
                break

        out.release()
        for cap in [cap1, cap2, cap3, cap4]:
            cap.release()

        cv2.destroyAllWindows()

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
            print(f"Compression failed, deleting {ongoing_filename}")
            if os.path.exists(ongoing_filename):
                os.remove(ongoing_filename)
            print(f"Waiting {ERROR_WAIT} seconds before retrying...")
            time.sleep(ERROR_WAIT)
            continue

if __name__ == "__main__":
    try:
        record_and_stitch()
    except KeyboardInterrupt:
        print("Recording stopped by user.")
        cv2.destroyAllWindows()
