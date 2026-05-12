import socket
import struct


class RemoteIOError(Exception):
    pass


class RemoteIOClient:
    def __init__(self, config):
        self.host = config.get("host", "")
        self.port = int(config.get("port", 502))
        self.unit_id = int(config.get("unit_id", 1))
        self.timeout = max(0.1, int(config.get("timeout_ms", 1000)) / 1000)
        self._transaction_id = 0

    def read_di(self, address):
        response = self._request(2, struct.pack(">HH", int(address), 1))
        if len(response) < 3 or response[1] < 1:
            raise RemoteIOError("Invalid DI response.")
        return bool(response[2] & 0x01)

    def write_do(self, address, enabled):
        value = 0xFF00 if enabled else 0x0000
        response = self._request(5, struct.pack(">HH", int(address), value))
        if len(response) < 5:
            raise RemoteIOError("Invalid DO response.")

    def pulse_do(self, address, seconds, on_done=None):
        self.write_do(address, True)
        return int(seconds * 1000), lambda: self._reset_output(address, on_done)

    def _reset_output(self, address, on_done):
        try:
            self.write_do(address, False)
        finally:
            if on_done:
                on_done()

    def _request(self, function_code, payload):
        self._transaction_id = (self._transaction_id + 1) % 65536
        pdu = bytes([function_code]) + payload
        header = struct.pack(">HHHB", self._transaction_id, 0, len(pdu) + 1, self.unit_id)
        packet = header + pdu

        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
                sock.settimeout(self.timeout)
                sock.sendall(packet)
                response_header = self._recv_exact(sock, 7)
                _tid, protocol_id, length, _unit_id = struct.unpack(">HHHB", response_header)
                if protocol_id != 0:
                    raise RemoteIOError("Invalid Modbus protocol id.")
                response_pdu = self._recv_exact(sock, length - 1)
        except OSError as exc:
            raise RemoteIOError(f"Remote I/O connection failed: {exc}") from exc

        if not response_pdu:
            raise RemoteIOError("Empty Modbus response.")
        if response_pdu[0] == function_code + 0x80:
            code = response_pdu[1] if len(response_pdu) > 1 else "unknown"
            raise RemoteIOError(f"Modbus exception code: {code}")
        if response_pdu[0] != function_code:
            raise RemoteIOError("Unexpected Modbus function response.")
        return response_pdu

    def _recv_exact(self, sock, size):
        data = b""
        while len(data) < size:
            chunk = sock.recv(size - len(data))
            if not chunk:
                raise RemoteIOError("Remote I/O closed the connection.")
            data += chunk
        return data
