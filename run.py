import socket
import threading
import pyaudio
import struct
import queue
import time
import numpy as np
import noisereduce as nr
import tkinter as tk
from tkinter import simpledialog, scrolledtext
from PIL import Image, ImageTk
import cv2
import pickle

# Configuration
PORT_TEXT = 12345
PORT_VIDEO = 12346
PORT_AUDIO = 5000  # Port for audio, updated to match the provided example
BUFFER_SIZE = 4096 * 10
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100

# Create a queue for audio data
audio_queue = queue.PriorityQueue()  # Priority queue for audio packet handling

# Sequence number tracking for audio
latest_sequence = -1

class P2PChat:
    def __init__(self, root):
        self.root = root
        self.root.title("P2P Chat")
        self.root.geometry("800x600")
        
        # UI Elements for Chat and Video
        self.chat_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, state=tk.DISABLED)
        self.chat_area.pack(padx=10, pady=10, expand=True, fill=tk.BOTH)

        self.entry = tk.Entry(root, font=("Arial", 12))
        self.entry.pack(padx=10, pady=5, fill=tk.X)

        self.send_button = tk.Button(root, text="Send", command=self.send_message)
        self.send_button.pack(padx=10, pady=5, fill=tk.X)

        self.exit_button = tk.Button(root, text="Exit", command=self.exit_chat, bg="red", fg="white")
        self.exit_button.pack(padx=10, pady=5, fill=tk.X)

        self.video_frame = tk.Frame(root)
        self.video_frame.pack(padx=10, pady=10, expand=True, fill=tk.BOTH)

        # Local and Peer Video Canvas
        self.local_video_canvas = tk.Canvas(self.video_frame, bg="black")
        self.local_video_canvas.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")
        
        self.peer_video_canvas = tk.Canvas(self.video_frame, bg="black")
        self.peer_video_canvas.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

        # Make the video columns resizable
        self.video_frame.grid_rowconfigure(0, weight=1)
        self.video_frame.grid_columnconfigure(0, weight=1)
        self.video_frame.grid_columnconfigure(1, weight=1)

        # Audio configurations
        self.audio = pyaudio.PyAudio()

        # Networking setup for text, video, and audio
        self.my_ip = socket.gethostbyname(socket.gethostname())
        self.sock_text = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_text.bind((self.my_ip, PORT_TEXT))

        self.sock_video = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        # User input for peer IP
        self.target_ip = simpledialog.askstring("Target IP", "Enter Peer IP:")
        
        self.running = True

        # Start threads for message, video, and audio
        threading.Thread(target=self.receive_messages, daemon=True).start()
        threading.Thread(target=self.send_video, daemon=True).start()
        threading.Thread(target=self.receive_video, daemon=True).start()
        threading.Thread(target=self.send_audio, daemon=True).start()
        threading.Thread(target=self.receive_audio, daemon=True).start()

    def send_audio(self):
        """Capture and send audio data with sequence numbers."""
        stream = self.audio.open(format=FORMAT,
                                channels=CHANNELS,
                                rate=RATE,
                                frames_per_buffer=CHUNK,
                                input=True)
        
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        sequence_number = 0  
        print("Streaming audio...")
        
        while self.running:
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
                packet = struct.pack("!I", sequence_number) + data  # Pack sequence number and audio data
                server.sendto(packet, (self.target_ip, PORT_AUDIO))  # Send packet to the peer
                sequence_number += 1
                time.sleep(CHUNK / RATE)  # Ensure proper sending rate
            except Exception as e:
                print(f"[ERROR] Audio send error: {e}")
                break

    def receive_audio(self):
        """Receive audio, apply noise reduction, and play it back."""
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receiver.bind((self.my_ip, PORT_AUDIO))

        stream = self.audio.open(format=FORMAT,
                                 channels=CHANNELS,
                                 rate=RATE,
                                 output=True,
                                 frames_per_buffer=CHUNK)

        global latest_sequence

        while self.running:
            try:
                packet, _ = receiver.recvfrom(CHUNK + 4)  # 4 bytes for sequence number
                sequence_number = struct.unpack("!I", packet[:4])[0]  # Extract sequence number
                audio_data = packet[4:]  # Extract actual audio data

                audio_queue.put((sequence_number, audio_data))  # Add to queue for processing

                if audio_queue.qsize() > 0:  # Play the audio as it comes in
                    sequence_number, data = audio_queue.get()
                    if sequence_number == latest_sequence + 1 or latest_sequence == -1:
                        # Apply noise reduction on audio data
                        audio_array = np.frombuffer(data, dtype=np.int16)
                        reduced_audio = nr.reduce_noise(y=audio_array, sr=RATE)
                        cleaned_data = reduced_audio.astype(np.int16).tobytes()
                        stream.write(cleaned_data)  # Play the cleaned audio
                        latest_sequence = sequence_number
                    elif sequence_number > latest_sequence + 1:
                        print(f"Packet loss detected! Expected {latest_sequence + 1}, got {sequence_number}")
                        latest_sequence = sequence_number

            except Exception as e:
                print(f"[ERROR] Audio receive error: {e}")
                break

    def send_video(self):
        """Send video frames and display local video."""
        camera_index = self.get_available_camera()
        if camera_index is None:
            print("[ERROR] No available camera. Exiting video thread.")
            return

        cap = cv2.VideoCapture(camera_index)

        while self.running:
            ret, frame = cap.read()
            if not ret:
                print("[ERROR] Failed to read video frame.")
                break

            # Show my video (IN THIS FUNCTION)
            self.show_local_video(frame)

            # Encode and send
            _, frame_encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            data = pickle.dumps(frame_encoded)

            # Send frame size first
            self.sock_video.sendto(struct.pack("Q", len(data)), (self.target_ip, PORT_VIDEO))

            # Send frame in chunks
            for i in range(0, len(data), BUFFER_SIZE):
                self.sock_video.sendto(data[i:i + BUFFER_SIZE], (self.target_ip, PORT_VIDEO))

        cap.release()

    def receive_video(self):
        """Receive and display peer's video."""
        sock_video_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock_video_recv.bind((self.my_ip, PORT_VIDEO))

        data = b""
        payload_size = struct.calcsize("Q")

        while self.running:
            try:
                while len(data) < payload_size:
                    packet, _ = sock_video_recv.recvfrom(BUFFER_SIZE)
                    data += packet

                packed_msg_size = data[:payload_size]
                data = data[payload_size:]
                msg_size = struct.unpack("Q", packed_msg_size)[0]

                while len(data) < msg_size:
                    packet, _ = sock_video_recv.recvfrom(BUFFER_SIZE)
                    data += packet

                frame_data = data[:msg_size]
                data = data[msg_size:]

                frame_encoded = pickle.loads(frame_data)
                frame = cv2.imdecode(frame_encoded, cv2.IMREAD_COLOR)

                self.show_peer_video(frame)

            except Exception as e:
                print(f"[ERROR] Video receive error: {e}")

        sock_video_recv.close()

    def show_local_video(self, frame):
        """Show local webcam feed on the Tkinter canvas."""
        canvas_width = self.local_video_canvas.winfo_width()
        canvas_height = self.local_video_canvas.winfo_height()

        height, width = frame.shape[:2]
        aspect_ratio = width / height

        if width > height:
            new_width = canvas_width
            new_height = int(new_width / aspect_ratio)
        else:
            new_height = canvas_height
            new_width = int(new_height * aspect_ratio)

        resized_frame = cv2.resize(frame, (new_width, new_height))

        frame_rgb = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        img_tk = ImageTk.PhotoImage(image=img)

        self.local_video_canvas.create_image(0, 0, image=img_tk, anchor=tk.NW)
        self.local_video_canvas.image = img_tk  # Keep a reference to avoid garbage collection

    def show_peer_video(self, frame):
        """Show received video from the peer on the Tkinter canvas."""
        canvas_width = self.peer_video_canvas.winfo_width()
        canvas_height = self.peer_video_canvas.winfo_height()

        height, width = frame.shape[:2]
        aspect_ratio = width / height

        if width > height:
            new_width = canvas_width
            new_height = int(new_width / aspect_ratio)
        else:
            new_height = canvas_height
            new_width = int(new_height * aspect_ratio)

        resized_frame = cv2.resize(frame, (new_width, new_height))

        frame_rgb = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        img_tk = ImageTk.PhotoImage(image=img)

        self.peer_video_canvas.create_image(0, 0, image=img_tk, anchor=tk.NW)
        self.peer_video_canvas.image = img_tk  # Keep a reference to avoid garbage collection

    def get_available_camera(self):
        """Find the first available camera index."""
        for i in range(5):  # Check indexes 0 to 4
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cap.release()
                return i
        print("🚨 No available cameras detected!")
        return None

    def send_message(self):
        """Send message to peer"""
        msg = self.entry.get()
        if msg:
            self.sock_text.sendto(msg.encode(), (self.target_ip, PORT_TEXT))
            self.chat_area.config(state=tk.NORMAL)
            self.chat_area.insert(tk.END, f"[You]: {msg}\n")
            self.chat_area.yview(tk.END)
            self.chat_area.config(state=tk.DISABLED)
            self.entry.delete(0, tk.END)

    def receive_messages(self):
        """Receive messages and display in chat"""
        while self.running:
            try:
                data, addr = self.sock_text.recvfrom(BUFFER_SIZE)
                msg = f"[{addr[0]}]: {data.decode()}\n"
                self.chat_area.config(state=tk.NORMAL)
                self.chat_area.insert(tk.END, msg)
                self.chat_area.yview(tk.END)
                self.chat_area.config(state=tk.DISABLED)
            except:
                break

    def exit_chat(self):
        """Exit the chat"""
        self.running = False
        self.sock_text.close()
        self.sock_video.close()
        # self.sock_audio.close()  # Close audio socket
        self.audio.terminate()   # Clean up PyAudio resources
        self.root.quit()

# Run Application
if __name__ == "__main__":
    root = tk.Tk()
    app = P2PChat(root)
    root.mainloop()
