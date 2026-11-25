"""PyAV RTSP/TCP source. Authenticated URI never leaves this adapter's memory."""
from datetime import datetime, timezone
import queue
import subprocess
import threading
import time
from urllib.parse import quote, urlsplit, urlunsplit


def utc_iso():
    return datetime.now(timezone.utc).isoformat()


def authenticated_uri(public_uri, username, password):
    parsed = urlsplit(public_uri)
    if parsed.scheme != "rtsp" or parsed.username is not None or not parsed.hostname:
        raise ValueError("RTSP_PUBLIC_URI_INVALID")
    return urlunsplit(parsed._replace(netloc=f"{quote(username, safe='')}:{quote(password, safe='')}@{parsed.netloc}"))


def keychain_secret(service, helper=None):
    command = [helper, "read", service] if helper else ["security", "find-generic-password", "-a", "pilot", "-s", service, "-w"]
    result = subprocess.run(command,
                            capture_output=True, timeout=15)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError("CAMERA_KEYCHAIN_UNAVAILABLE")
    return result.stdout.decode().rstrip("\n")


def put_latest(frames, value):
    try:
        frames.put_nowait(value)
    except queue.Full:
        try:
            frames.get_nowait()
        except queue.Empty:
            pass
        frames.put_nowait(value)


class LiveSource:
    def __init__(self, config):
        self.config = config
        self.frames = queue.Queue(maxsize=2)
        self.stop = threading.Event()
        self.enabled = threading.Event()
        if config.get("mode", "continuous") == "continuous": self.enabled.set()
        self.lock = threading.Lock()
        self.stats = {"source_state": "starting", "reconnect_count": 0, "last_error_code": None,
            "last_frame_received_at": None, "last_frame_decoded_at": None,
            "received_packets": 0, "decoded_frames": 0, "connection_generation": 0}
        self.thread = threading.Thread(target=self._capture, name="rtsp-capture", daemon=True)

    def snapshot(self):
        with self.lock:
            return {**self.stats, "queue_depth": self.frames.qsize()}

    def _update(self, **values):
        with self.lock:
            self.stats.update(values)

    def _capture(self):
        import av
        av.logging.set_level(-8)  # AV_LOG_QUIET: libav must never print an authenticated URI.
        backoff = 1
        try:
            username = keychain_secret(self.config["username_service"], self.config.get("keychain_helper"))
            password = keychain_secret(self.config["password_service"], self.config.get("keychain_helper"))
            uri = authenticated_uri(self.config["rtsp_uri"], username, password)
        except Exception:
            self._update(source_state="error", last_error_code="CAMERA_KEYCHAIN_UNAVAILABLE")
            return
        while not self.stop.is_set():
            if not self.enabled.is_set():
                self._update(source_state="idle_unchecked")
                self.stop.wait(.1)
                continue
            container = None
            try:
                container = av.open(uri, mode="r", options={"rtsp_transport": "tcp", "timeout": "5000000"}, timeout=(5, 5))
                video = container.streams.video[0]
                video.thread_count = 2
                self._update(connection_generation=self.stats["connection_generation"] + 1,
                    codec=video.codec_context.name, width=video.codec_context.width,
                    height=video.codec_context.height, nominal_fps=float(video.average_rate) if video.average_rate else None,
                    transport="rtsp_tcp", channel=1, subtype=0)
                for packet in container.demux(video):
                    if self.stop.is_set() or not self.enabled.is_set():
                        break
                    if not packet.size:
                        continue
                    received = utc_iso()
                    self._update(last_frame_received_at=received, received_packets=self.stats["received_packets"] + 1)
                    for frame in packet.decode():
                        decoded = utc_iso()
                        self._update(source_state="receiving", last_frame_decoded_at=decoded,
                            decoded_frames=self.stats["decoded_frames"] + 1)
                        put_latest(self.frames, (frame, received, decoded, time.monotonic(), self.stats["connection_generation"]))
                        backoff = 1
                if not self.stop.is_set() and self.enabled.is_set():
                    raise EOFError()
            except Exception as error:
                # Never stringify exceptions: PyAV/FFmpeg may embed credentials.
                unauthorized = isinstance(error, av.error.HTTPUnauthorizedError)
                self._update(source_state="error" if unauthorized else "reconnecting",
                    last_error_code="RTSP_AUTH_REJECTED" if unauthorized else "RTSP_READ_INTERRUPTED",
                    reconnect_count=self.stats["reconnect_count"] + (0 if unauthorized else 1))
                if unauthorized:
                    return  # One rejected supplied account stops; no password guessing.
                self.stop.wait(backoff)
                backoff = min(30, backoff * 2)
            finally:
                if container:
                    container.close()
                container = None; video = None; packet = None; frame = None
                import gc
                gc.collect()
        self._update(source_state="stopped")

    def enable(self, active):
        if active:
            if not self.enabled.is_set() and self.snapshot()["source_state"] == "idle_unchecked":
                self._update(source_state="starting")
            self.enabled.set()
        else:
            self.enabled.clear()
            while True:
                try: self.frames.get_nowait()
                except queue.Empty: break

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=12)
        return not self.thread.is_alive()
