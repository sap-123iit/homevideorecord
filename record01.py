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
    """Run videoupload.py immediately, then every UPLOAD_INTERVAL seconds without overlap.
       Maintain a log of each run in videoupload_log.txt."""
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "videoupload_log.txt")

    while True:
        try:
            # Check if videoupload.py is already running
            result = subprocess.run(["pgrep", "-f", "videoupload.py"], stdout=subprocess.PIPE)
            if result.stdout:  # Some PID(s) found → already running
                print("[Uploader] videoupload.py is already running. Skipping this cycle.")
            else:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n[Uploader] Starting videoupload.py at {timestamp}...")

                # Append timestamp to log file
                try:
                    with open(log_file, "a") as log:
                        log.write(f"videoupload.py called at {timestamp}\n")
                except Exception as e:
                    print(f"[Uploader] Error writing to log file: {e}")

                # Run upload (blocking, no overlap)
                subprocess.run(["python3", "videoupload.py"], check=False)
                print(f"[Uploader] videoupload.py finished at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.\n")

        except Exception as e:
            print(f"[Uploader] Error running videoupload.py: {e}")

        # Wait 20 minutes before the next run
        time.sleep(UPLOAD_INTERVAL)



def initialize_captures():
    """Initialize RTSP stream captures with error handling for 4 channels."""
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
        # Initialize captures
        cap1, cap2, cap3, cap4 = initialize_captures()
        if cap1 is None:
            print(f"Waiting {ERROR_WAIT} seconds before retrying...")
            time.sleep(ERROR_WAIT)
            continue

        # Get FPS from the first stream
        fps = cap1.get(cv2.CAP_PROP_FPS)
        if fps == 0 or fps > FPS_CAP:
            fps = FPS_CAP

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = os.path.join(output_folder, f"recording_{timestamp}.mp4")

        # Output size = 2 × width, 2 × height (grid)
        out = cv2.VideoWriter(output_filename, FOURCC, fps, (TARGET_WIDTH * 2, TARGET_HEIGHT * 2))
        if not out.isOpened():
            print("Error: Unable to open VideoWriter")
            for cap in [cap1, cap2, cap3, cap4]:
                cap.release()
            print(f"Waiting {ERROR_WAIT} seconds before retrying...")
            time.sleep(ERROR_WAIT)
            continue

        start_time = time.time()
        capture_success = True
        print(f"Starting recording: {output_filename}")

        while (time.time() - start_time) < DURATION:
            ret1, frame1 = cap1.read()
            ret2, frame2 = cap2.read()
            ret3, frame3 = cap3.read()
            ret4, frame4 = cap4.read()
            if not (ret1 and ret2 and ret3 and ret4):
                print("Error: Failed to capture frame from one or more streams.")
                capture_success = False
                break

            # Resize all frames
            frame1 = cv2.resize(frame1, (TARGET_WIDTH, TARGET_HEIGHT))
            frame2 = cv2.resize(frame2, (TARGET_WIDTH, TARGET_HEIGHT))
            frame3 = cv2.resize(frame3, (TARGET_WIDTH, TARGET_HEIGHT))
            frame4 = cv2.resize(frame4, (TARGET_WIDTH, TARGET_HEIGHT))

            # Top row: CH101 + CH201
            top_row = cv2.hconcat([frame1, frame2])
            # Bottom row: CH301 + CH401
            bottom_row = cv2.hconcat([frame3, frame4])

            # Stack vertically → 2×2 grid
            combined_frame = cv2.vconcat([top_row, bottom_row])
            out.write(combined_frame)

            # Optional preview
            cv2.imshow('Recording', combined_frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                capture_success = False
                break

        out.release()
        cap1.release()
        cap2.release()
        cap3.release()
        cap4.release()

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
