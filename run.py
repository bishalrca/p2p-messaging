import socket
import threading
import tkinter as tk
from tkinter import scrolledtext,simpledialog

# Configuration
PORT = 12345  # Common port for communication
BUFFER_SIZE = 1024

class P2PChat:
    def __init__(self, root):
        self.root = root
        self.root.title("P2P LAN Chat")
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
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((self.my_ip, PORT))

        self.target_ip = simpledialog.askstring("Target IP", "Enter Peer IP:")
        self.running = True

        # Start receiving thread
        self.recv_thread = threading.Thread(target=self.receive_messages, daemon=True)
        self.recv_thread.start()

    def receive_messages(self):
        """Receive messages and display in chat"""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(BUFFER_SIZE)
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
            self.sock.sendto(msg.encode(), (self.target_ip, PORT))
            self.chat_area.config(state=tk.NORMAL)
            self.chat_area.insert(tk.END, f"[You]: {msg}\n")
            self.chat_area.yview(tk.END)
            self.chat_area.config(state=tk.DISABLED)
            self.entry.delete(0, tk.END)

    def exit_chat(self):
        """Exit the chat"""
        self.running = False
        self.sock.close()
        self.root.quit()

# Run Application
if __name__ == "__main__":
    root = tk.Tk()
    app = P2PChat(root)
    root.mainloop()
