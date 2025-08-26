import cv2
import time
import os
from datetime import datetime

# Define the output folder
output_folder = r"/home/pi/homevideo"
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Define the path for the recorded video list file
RECORDED_LIST_FILE = os.path.join(output_folder, 'recordedvideolist.txt')

# Open both RTSP streams
cap1 = cv2.VideoCapture('rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/102')
cap2 = cv2.VideoCapture('rtsp://admin:Stoploss%231@192.168.0.100:554/Streaming/channels/202')

# Check if cameras opened successfully
if not (cap1.isOpened() and cap2.isOpened()):
    print("Error: Could not open one or both RTSP streams.")
    exit()

# Target resolution (reduced size for smaller file)
target_width = 640     # reduce width
target_height = 360    # reduce height

# Get FPS from the first stream
fps = cap1.get(cv2.CAP_PROP_FPS)
if fps == 0:
    fps = 15.0  # Default FPS if stream doesn't provide it (reduce FPS to lower size)

# Video writer codec (H.264 usually smaller than mp4v)
fourcc = cv2.VideoWriter_fourcc(*'avc1')  # or use 'mp4v'
recording = True

def append_to_recorded_list(filename):
    """Append the completed video filename to recordedvideolist.txt."""
    try:
        with open(RECORDED_LIST_FILE, 'a') as f:
            f.write(f"{filename}\n")
        print(f"Appended {filename} to {RECORDED_LIST_FILE}")
    except Exception as e:
        print(f"Error appending {filename} to {RECORDED_LIST_FILE}: {e}")

print("Press 'q' to stop recording.")

while recording:
    # Generate filename with date and timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = os.path.join(output_folder, f"recording_{timestamp}.mp4")
    
    # Output resolution is doubled in width (side by side)
    out = cv2.VideoWriter(output_filename, fourcc, fps, (target_width * 2, target_height))
    
    start_time = time.time()
    print(f"Starting recording: {output_filename}")
    
    while True:
        ret1, frame1 = cap1.read()
        ret2, frame2 = cap2.read()
        
        if not (ret1 and ret2):
            print("Error: Failed to capture frame from one or both streams.")
            break

        # Resize both frames to smaller target resolution
        frame1 = cv2.resize(frame1, (target_width, target_height))
        frame2 = cv2.resize(frame2, (target_width, target_height))
        
        # Stitch horizontally
        combined_frame = cv2.hconcat([frame1, frame2])
        
        # Write the combined frame
        out.write(combined_frame)
        
        # Display the frame (optional, for live preview)
        cv2.imshow('Recording', combined_frame)
        
        # Check for 'q' key press to stop
        if cv2.waitKey(1) & 0xFF == ord('q'):
            recording = False
            break
        
        # Split recording into 5-min chunks (300 sec)
        if time.time() - start_time >= 300:
            break
    
    # Release the video writer to finalize the file
    out.release()
    print(f"Saved: {output_filename}")
    
    # Append the filename to recordedvideolist.txt after recording is complete
    append_to_recorded_list(os.path.basename(output_filename))

# Release resources
cap1.release()
cap2.release()
cv2.destroyAllWindows()
print("Recording stopped.")
