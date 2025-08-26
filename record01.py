import cv2
import time
import os
import subprocess
import threading
from datetime import datetime

# Define the output folder
output_folder = r"/home/pi/homevideo"
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Define the path for the recorded video list file
RECORDED_LIST_FILE = os.path.join(output_folder, 'recordedvideolist.txt')

# Constants
TARGET_WIDTH = 480
TARGET_HEIGHT = 270
FPS_CAP = 15.0
DURATION = 180        # 3 minutes per chunk
ERROR_WAIT = 120      # 2 minutes wait on error
UPLOAD_INTERVAL = 1200  # 20 minutes
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
    compressed_file = input_file.replace(".mp4", "_compressed.mp4")
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", input_file,
            "-vcodec", "libx264", "-crf", "28", "-preset", "veryfast",
            "-an",  # no audio
            compressed_file
        ], check=True)
        os.replace(compressed_file, input_file)
        print(f"Compressed: {input_file}")
        return True
    except Exception as e:
        print(f"FFmpeg compression failed for {input_file}: {e}")
        return False

def uploader_loop():
    """Run videoupload.py immediately, then every UPLOAD_INTERVAL seconds without overlap."""
    while True:
        try:
            print("\n[Uploader] Starting videoupload.py...")
            # Wait until upload finishes (no overlap) and show logs in terminal
            subprocess.run(["python3", "videoupload.py"], check=False)
            print("[Uploader] videoupload.py finished.\n")
        except Exception as e:
            print(f"[Uploader] Error running videoupload.py: {e}")
        
        # Wait 20 minutes before the next run
        time.sleep(UPLOAD_INTERVAL)

def initialize_captures():
    """Initialize RTSP stream captures with error handling."""
    cap1 = cv2.VideoCapture('rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/102')
    cap2 = cv2.VideoCapture('rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/202')
    if not (cap1.isOpened() and cap2.isOpened()):
        print("Error: Could not open one or both RTSP streams.")
        if cap1.isOpened():
            cap1.release()
        if cap2.isOpened():
            cap2.release()
        return None, None
    return cap1, cap2

def record_and_stitch():
    while True:
        # Initialize captures
        cap1, cap2 = initialize_captures()
        if cap1 is None or cap2 is None:
            print(f"Waiting {ERROR_WAIT} seconds before retrying...")
            time.sleep(ERROR_WAIT)
            continue

        # Get FPS from the first stream
        fps = cap1.get(cv2.CAP_PROP_FPS)
        if fps == 0 or fps > FPS_CAP:
            fps = FPS_CAP

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = os.path.join(output_folder, f"recording_{timestamp}.mp4")

        out = cv2.VideoWriter(output_filename, FOURCC, fps, (TARGET_WIDTH * 2, TARGET_HEIGHT))
        if not out.isOpened():
            print("Error: Unable to open VideoWriter")
            cap1.release()
            cap2.release()
            print(f"Waiting {ERROR_WAIT} seconds before retrying...")
            time.sleep(ERROR_WAIT)
            continue

        start_time = time.time()
        capture_success = True
        print(f"Starting recording: {output_filename}")

        while (time.time() - start_time) < DURATION:
            ret1, frame1 = cap1.read()
            ret2, frame2 = cap2.read()
            if not (ret1 and ret2):
                print("Error: Failed to capture frame from one or both streams.")
                capture_success = False
                break

            # Resize both frames
            frame1 = cv2.resize(frame1, (TARGET_WIDTH, TARGET_HEIGHT))
            frame2 = cv2.resize(frame2, (TARGET_WIDTH, TARGET_HEIGHT))

            # Stitch horizontally
            combined_frame = cv2.hconcat([frame1, frame2])
            out.write(combined_frame)

            # Optional: live preview
            cv2.imshow('Recording', combined_frame)

            # Stop with 'q'
            if cv2.waitKey(1) & 0xFF == ord('q'):
                capture_success = False
                break

        out.release()
        cap1.release()
        cap2.release()

        if not capture_success:
            print(f"Capture failed, deleting {output_filename} if it exists")
            if os.path.exists(output_filename):
                os.remove(output_filename)
            cv2.destroyAllWindows()
            print(f"Waiting {ERROR_WAIT} seconds before retrying...")
            time.sleep(ERROR_WAIT)
            continue

        # Compress video
        compression_success = compress_with_ffmpeg(output_filename)
        if not compression_success:
            print(f"Compression failed, deleting {output_filename} if it exists")
            if os.path.exists(output_filename):
                os.remove(output_filename)
            cv2.destroyAllWindows()
            print(f"Waiting {ERROR_WAIT} seconds before retrying...")
            time.sleep(ERROR_WAIT)
            continue

        # Append to recorded list only if both capture and compression are successful
        append_to_recorded_list(os.path.basename(output_filename))

        # Destroy preview window after each chunk
        cv2.destroyAllWindows()

if __name__ == "__main__":
    try:
        # Start uploader thread in background
        uploader_thread = threading.Thread(target=uploader_loop, daemon=True)
        uploader_thread.start()

        # Start recording loop
        record_and_stitch()
    except KeyboardInterrupt:
        print("Recording stopped by user.")
        cv2.destroyAllWindows()
