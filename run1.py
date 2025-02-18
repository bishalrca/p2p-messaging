import socket
import threading
import pyaudio
import numpy as np
import queue
import opuslib  # Low-latency Opus codec for compression

# Configuration
PORT_AUDIO = 12347  # UDP port for audio
BUFFER_SIZE = 1024  # Smaller buffer for low latency
AUDIO_QUEUE_SIZE = 5  # Reduce queue size for lower latency
SILENCE_THRESHOLD = 1000  # RMS threshold to detect silence

# Opus settings
FRAME_SIZE = 960  # Opus works best with 20ms (960 samples at 48kHz)
OPUS_BITRATE = 64000  # 64 kbps for good quality

# Create a queue for audio data
audio_queue = queue.Queue(maxsize=AUDIO_QUEUE_SIZE)

class AudioHandler:
    def __init__(self, target_ip):
        self.target_ip = target_ip
        self.my_ip = socket.gethostbyname(socket.gethostname())

        self.running = True

        # Initialize UDP sockets
        self.sock_audio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_audio_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock_audio_recv.bind((self.my_ip, PORT_AUDIO))

        # PyAudio settings
        self.pyaudio_instance = pyaudio.PyAudio()
        self.stream = self.pyaudio_instance.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=48000,  # Higher quality
            frames_per_buffer=FRAME_SIZE,
            input=True,
            output=True
        )

        # Opus encoder & decoder
        self.encoder = opuslib.Encoder(48000, 1, 'voip')
        self.encoder.bitrate = OPUS_BITRATE
        self.decoder = opuslib.Decoder(48000, 1)

        # Start threads
        threading.Thread(target=self.capture_audio, daemon=True).start()
        threading.Thread(target=self.receive_audio, daemon=True).start()
        threading.Thread(target=self.play_audio_from_queue, daemon=True).start()

    def capture_audio(self):
        """Capture and send audio with silence detection and Opus encoding."""
        while self.running:
            audio_data = self.stream.read(FRAME_SIZE, exception_on_overflow=False)
            samples = np.frombuffer(audio_data, dtype=np.int16)
            rms = np.sqrt(np.mean(samples**2))

            if rms > SILENCE_THRESHOLD:
                compressed_audio = self.encoder.encode(audio_data, FRAME_SIZE)
                self.sock_audio.sendto(compressed_audio, (self.target_ip, PORT_AUDIO))
            else:
                print("🔇 Silence detected, not sending audio.")

    def receive_audio(self):
        """Receive and queue audio data."""
        while self.running:
            try:
                packet, _ = self.sock_audio_recv.recvfrom(400)  # Opus compressed packets are small
                if not audio_queue.full():
                    audio_queue.put(packet)
            except Exception as e:
                print(f"[ERROR] Audio receive error: {e}")

    def play_audio_from_queue(self):
        """Dequeue and play audio data smoothly."""
        while self.running:
            if not audio_queue.empty():
                packet = audio_queue.get_nowait()
                decompressed_audio = self.decoder.decode(packet, FRAME_SIZE)
                self.stream.write(decompressed_audio)
                audio_queue.task_done()
            else:
                threading.Event().wait(0.01)  # Reduce CPU usage

    def stop(self):
        """Stop all audio processes."""
        self.running = False
        self.sock_audio.close()
        self.sock_audio_recv.close()
        self.stream.stop_stream()
        self.stream.close()
        self.pyaudio_instance.terminate()

# Example usage
if __name__ == "__main__":
    target_ip = input("Enter peer's IP: ")
    audio_handler = AudioHandler(target_ip)

    try:
        while True:
            pass  # Keep main thread alive
    except KeyboardInterrupt:
        audio_handler.stop()
        print("\nExiting...")
