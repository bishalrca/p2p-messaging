import socket
import threading
import cv2
import pickle
import struct
import tkinter as tk
from tkinter import simpledialog, scrolledtext
import numpy as np

# Configuration
PORT_TEXT = 12345  # Port for text messages
PORT_VIDEO = 12346  # Port for video streaming
BUFFER_SIZE = 4096  # Maximum UDP packet size

class P2PChat:
    def __init__(self, root):
        self.root = root
        self.root.title("P2P Chat")
        self.root.geometry("400x500")

        # UI Elements
        self.chat_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, state=tk.DISABLED)
        self.chat_area.pack(padx=10, pady=10, expand=True, fill=tk.BOTH)

        self.entry = tk.Entry(root, font=("Arial", 12))
        self.entry.pack(padx=10, pady=5, fill=tk.X)

        self.send_button = tk.Button(root, text="Send", command=self.send_message)
        self.send_button.pack(padx=10, pady=5, fill=tk.X)

        self.exit_button = tk.Button(root, text="Exit", command=self.exit_chat, bg="red", fg="white")
        self.exit_button.pack(padx=10, pady=5, fill=tk.X)

        # Networking
        self.my_ip = socket.gethostbyname(socket.gethostname())  # Get local IP
        self.sock_text = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_text.bind((self.my_ip, PORT_TEXT))

        self.target_ip = simpledialog.askstring("Target IP", "Enter Peer IP:")
        self.running = True

        # Start threads
        threading.Thread(target=self.receive_messages, daemon=True).start()
        threading.Thread(target=self.send_video, daemon=True).start()
        threading.Thread(target=self.receive_video, daemon=True).start()

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

    def send_video(self):
        """Send video frames in smaller UDP packets"""
        cap = cv2.VideoCapture(0)  # Capture from webcam
        sock_video = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        while self.running:
            ret, frame = cap.read()
            if not ret:
                break

            # Compress frame to JPEG format
            _, frame_encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
            data = pickle.dumps(frame_encoded)

            # Send the length of data first (optional but helps for synchronization)
            data_length = len(data)
            sock_video.sendto(struct.pack("!I", data_length), (self.target_ip, PORT_VIDEO))

            # Split data into chunks
            for i in range(0, len(data), BUFFER_SIZE):
                sock_video.sendto(data[i:i + BUFFER_SIZE], (self.target_ip, PORT_VIDEO))

        cap.release()

    def receive_video(self):
        """Receive and reconstruct video frames"""
        sock_video = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock_video.bind((self.my_ip, PORT_VIDEO))

        data = b""

        while self.running:
            try:
                packet, _ = sock_video.recvfrom(BUFFER_SIZE)
                if not data:  # If no previous data, try receiving the length first
                    data_length = struct.unpack("!I", packet)[0]  # Get the length of the full frame
                    data = b""  # Reset for the new frame

                data += packet

                # Check if the entire frame has been received
                if len(data) >= data_length:
                    frame_encoded = pickle.loads(data)
                    frame = cv2.imdecode(frame_encoded, cv2.IMREAD_COLOR)

                    # Show video frame
                    cv2.imshow("Video Chat", frame)
                    data = b""  # Reset buffer after displaying

                if cv2.waitKey(1) == 27:  # Press 'Esc' to exit
                    break
            except:
                break

        sock_video.close()
        cv2.destroyAllWindows()

    def exit_chat(self):
        """Exit the chat"""
        self.running = False
        self.sock_text.close()
        self.root.quit()

# Run Application
if __name__ == "__main__":
    root = tk.Tk()
    app = P2PChat(root)
    root.mainloop()
