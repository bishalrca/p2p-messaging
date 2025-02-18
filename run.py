import socket
import threading
import cv2
import pickle
import struct
import tkinter as tk
from tkinter import simpledialog, scrolledtext
from PIL import Image, ImageTk

# Configuration
PORT_TEXT = 12345
PORT_VIDEO = 12346
BUFFER_SIZE = 4096

class P2PChat:
    def __init__(self, root):
        self.root = root
        self.root.title("P2P Chat")
        self.root.geometry("800x600")

        # UI Elements
        self.chat_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, state=tk.DISABLED)
        self.chat_area.pack(padx=10, pady=10, expand=True, fill=tk.BOTH)

        self.entry = tk.Entry(root, font=("Arial", 12))
        self.entry.pack(padx=10, pady=5, fill=tk.X)

        self.send_button = tk.Button(root, text="Send", command=self.send_message)
        self.send_button.pack(padx=10, pady=5, fill=tk.X)

        self.exit_button = tk.Button(root, text="Exit", command=self.exit_chat, bg="red", fg="white")
        self.exit_button.pack(padx=10, pady=5, fill=tk.X)

        # Video frame layout (using grid to allow resizing)
        self.video_frame = tk.Frame(root)
        self.video_frame.pack(padx=10, pady=10, expand=True, fill=tk.BOTH)

        # Local Video Canvas (top-left)
        self.local_video_canvas = tk.Canvas(self.video_frame, bg="black")
        self.local_video_canvas.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        # Peer Video Canvas (top-right)
        self.peer_video_canvas = tk.Canvas(self.video_frame, bg="black")
        self.peer_video_canvas.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

        # Make the video columns resizable
        self.video_frame.grid_rowconfigure(0, weight=1)
        self.video_frame.grid_columnconfigure(0, weight=1)
        self.video_frame.grid_columnconfigure(1, weight=1)

        # Networking
        self.my_ip = socket.gethostbyname(socket.gethostname())
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

    def get_available_camera(self):
        """Find the first available camera index."""
        for i in range(5):  # Check indexes 0 to 4
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                print(f"✅ Using camera at index {i}")
                cap.release()
                return i
        print("🚨 No available cameras detected!")
        return None

    def send_video(self):
        """Send video frames and display local video."""
        camera_index = self.get_available_camera()
        if camera_index is None:
            print("[ERROR] No available camera. Exiting video thread.")
            return

        cap = cv2.VideoCapture(camera_index)
        sock_video = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

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
            sock_video.sendto(struct.pack("Q", len(data)), (self.target_ip, PORT_VIDEO))

            # Send frame in chunks
            for i in range(0, len(data), BUFFER_SIZE):
                sock_video.sendto(data[i:i + BUFFER_SIZE], (self.target_ip, PORT_VIDEO))

            # Break loop if 'Esc' is pressed
            if cv2.waitKey(1) == 27:
                break

        cap.release()
        cv2.destroyAllWindows()

    def receive_video(self):
        """Receive and display peer's video."""
        sock_video = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock_video.bind((self.my_ip, PORT_VIDEO))

        data = b""
        payload_size = struct.calcsize("Q")

        while self.running:
            try:
                # Receive frame size
                while len(data) < payload_size:
                    packet, _ = sock_video.recvfrom(BUFFER_SIZE)
                    data += packet
                    print(f"Receiving frame size: {len(data)}")

                packed_msg_size = data[:payload_size]
                data = data[payload_size:]
                msg_size = struct.unpack("Q", packed_msg_size)[0]

                # Receive frame data
                while len(data) < msg_size:
                    packet, _ = sock_video.recvfrom(BUFFER_SIZE)
                    data += packet
                    print(f"Receiving frame data: {len(data)}")

                frame_data = data[:msg_size]
                data = data[msg_size:]

                # Decode and show received video
                frame_encoded = pickle.loads(frame_data)
                frame = cv2.imdecode(frame_encoded, cv2.IMREAD_COLOR)
                print(f"Frame received: {frame.shape}")

                self.show_peer_video(frame)

            except Exception as e:
                print(f"[ERROR] Video receive error: {e}")
                break

        sock_video.close()
        cv2.destroyAllWindows()

    def show_local_video(self, frame):
        """Show local webcam feed on the Tkinter canvas."""
        # Get the canvas dimensions
        canvas_width = self.local_video_canvas.winfo_width()
        canvas_height = self.local_video_canvas.winfo_height()

        # Calculate aspect ratio
        height, width = frame.shape[:2]
        aspect_ratio = width / height

        # Resize the frame to fit within the canvas while maintaining aspect ratio
        if width > height:
            new_width = canvas_width
            new_height = int(new_width / aspect_ratio)
        else:
            new_height = canvas_height
            new_width = int(new_height * aspect_ratio)

        resized_frame = cv2.resize(frame, (new_width, new_height))

        # Convert the resized frame to RGB
        frame_rgb = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        img_tk = ImageTk.PhotoImage(image=img)

        # Display image on canvas
        self.local_video_canvas.create_image(0, 0, image=img_tk, anchor=tk.NW)
        self.local_video_canvas.image = img_tk  # Keep a reference to avoid garbage collection

    def show_peer_video(self, frame):
        """Show received video from the peer on the Tkinter canvas."""
        # Get the canvas dimensions
        canvas_width = self.peer_video_canvas.winfo_width()
        canvas_height = self.peer_video_canvas.winfo_height()

        # Calculate aspect ratio
        height, width = frame.shape[:2]
        aspect_ratio = width / height

        # Resize the frame to fit within the canvas while maintaining aspect ratio
        if width > height:
            new_width = canvas_width
            new_height = int(new_width / aspect_ratio)
        else:
            new_height = canvas_height
            new_width = int(new_height * aspect_ratio)

        resized_frame = cv2.resize(frame, (new_width, new_height))

        # Convert the resized frame to RGB
        frame_rgb = cv2.cvtColor(resized_frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(frame_rgb)
        img_tk = ImageTk.PhotoImage(image=img)

        # Display image on canvas
        self.peer_video_canvas.create_image(0, 0, image=img_tk, anchor=tk.NW)
        self.peer_video_canvas.image = img_tk  # Keep a reference to avoid garbage collection

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
