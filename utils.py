import threading, os, platform, subprocess

metadata_lock = threading.Lock()

def open_video_default(video_path):
    if not os.path.exists(video_path):
        print(f"Video no encontrado: {video_path}")
        return
    if platform.system() == "Darwin":
        subprocess.call(("open", video_path))
    elif platform.system() == "Windows":
        os.startfile(video_path)
    else:
        subprocess.call(("xdg-open", video_path))
