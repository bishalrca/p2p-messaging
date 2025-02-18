import socket
import threading

# Configuration
PORT = 12345  # Common port for all peers
BUFFER_SIZE = 1024

def receive_messages(sock):
    """Function to receive messages"""
    while True:
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            print(f"\n[{addr[0]}]: {data.decode()}")
        except:
            break

def send_messages(sock, target_ip):
    """Function to send messages"""
    while True:
        msg = input(">>")
        if msg.lower() == "exit":
            print("Exiting chat...")
            break
        sock.sendto(msg.encode(), (target_ip, PORT))

def main():
    """Main function to start the chat"""
    my_ip = socket.gethostbyname(socket.gethostname())  # Get local IP
    print(f"Your IP: {my_ip}")

    target_ip = input("Enter target peer IP: ")

    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((my_ip, PORT))

    # Start threads for sending and receiving messages
    recv_thread = threading.Thread(target=receive_messages, args=(sock,))
    send_thread = threading.Thread(target=send_messages, args=(sock, target_ip))

    recv_thread.start()
    send_thread.start()

    send_thread.join()
    sock.close()

if __name__ == "__main__":
    main()
