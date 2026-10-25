#!/usr/bin/env python3
"""Capture DNS and TLS connection metadata from this K3 printer only."""

import datetime
import select
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path


def local_ipv4_addresses():
    addresses = set()
    try:
        result = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", "scope", "global"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
            check=False,
        )
        for line in result.stdout.splitlines():
            fields = line.split()
            if "inet" in fields:
                address = fields[fields.index("inet") + 1].split("/", 1)[0]
                if not address.startswith("127."):
                    addresses.add(address)
    except (OSError, subprocess.TimeoutExpired):
        pass

    if addresses:
        return addresses

    # A UDP connect selects the routing interface without sending packets.
    try:
        route_probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            route_probe.connect(("192.0.2.1", 9))
            address = route_probe.getsockname()[0]
            if address and not address.startswith("127."):
                addresses.add(address)
        finally:
            route_probe.close()
    except OSError:
        pass

    if addresses:
        return addresses

    try:
        for name in Path("/sys/class/net").iterdir():
            if name.name == "lo":
                continue
            request = struct.pack("256s", name.name.encode()[:15])
            result = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                response = __import__("fcntl").ioctl(result.fileno(), 0x8915, request)
                address = socket.inet_ntoa(response[20:24])
                if not address.startswith("127."):
                    addresses.add(address)
            finally:
                result.close()
    except (OSError, ImportError):
        pass
    if not addresses:
        raise RuntimeError("Could not determine the printer's IPv4 addresses.")
    return addresses


def dns_name(data, offset):
    labels = []
    cursor = offset
    consumed = None
    visited = set()
    while cursor < len(data):
        length = data[cursor]
        if length == 0:
            cursor += 1
            return ".".join(labels), consumed if consumed is not None else cursor
        if length & 0xC0 == 0xC0:
            if cursor + 1 >= len(data):
                raise ValueError("truncated DNS pointer")
            pointer = ((length & 0x3F) << 8) | data[cursor + 1]
            if pointer in visited:
                raise ValueError("DNS compression loop")
            visited.add(pointer)
            if consumed is None:
                consumed = cursor + 2
            cursor = pointer
            continue
        if length & 0xC0 or cursor + 1 + length > len(data):
            raise ValueError("invalid DNS label")
        labels.append(data[cursor + 1 : cursor + 1 + length].decode("ascii", "replace"))
        cursor += length + 1
    raise ValueError("truncated DNS name")


def parse_dns(data):
    if len(data) < 12:
        return []
    transaction, flags, question_count, answer_count, _, _ = struct.unpack("!HHHHHH", data[:12])
    offset = 12
    questions = []
    for _ in range(min(question_count, 32)):
        name, offset = dns_name(data, offset)
        if offset + 4 > len(data):
            return []
        qtype, qclass = struct.unpack("!HH", data[offset : offset + 4])
        offset += 4
        questions.append((name, qtype, qclass))
    if not flags & 0x800:
        return ["DNS query id=%04x %s type=%s" % (transaction, name, qtype) for name, qtype, _ in questions]

    answers = []
    for _ in range(min(answer_count, 64)):
        try:
            owner, offset = dns_name(data, offset)
        except ValueError:
            break
        if offset + 10 > len(data):
            break
        rtype, rclass, ttl, size = struct.unpack("!HHIH", data[offset : offset + 10])
        offset += 10
        record = data[offset : offset + size]
        offset += size
        if rclass == 1 and rtype == 1 and len(record) == 4:
            value = socket.inet_ntoa(record)
        elif rclass == 1 and rtype == 28 and len(record) == 16:
            value = socket.inet_ntop(socket.AF_INET6, record)
        else:
            continue
        answers.append("%s=%s ttl=%d" % (owner, value, ttl))
    rcode = flags & 0xF
    question = ",".join(name for name, _, _ in questions) or "<no-question>"
    detail = "; ".join(answers) if answers else "no address answers"
    return ["DNS response id=%04x rcode=%d %s: %s" % (transaction, rcode, question, detail)]


def tls_sni(data):
    if len(data) < 9 or data[0] != 22:
        return None
    record_size = struct.unpack("!H", data[3:5])[0]
    if len(data) < 5 + record_size:
        return None
    handshake = data[5 : 5 + record_size]
    if len(handshake) < 4 or handshake[0] != 1:
        return None
    body_size = int.from_bytes(handshake[1:4], "big")
    body = handshake[4 : 4 + body_size]
    if len(body) < body_size or len(body) < 35:
        return None
    offset = 34
    session_size = body[offset]
    offset += 1 + session_size
    if offset + 2 > len(body):
        return None
    cipher_size = struct.unpack("!H", body[offset : offset + 2])[0]
    offset += 2 + cipher_size
    if offset >= len(body):
        return None
    compression_size = body[offset]
    offset += 1 + compression_size
    if offset + 2 > len(body):
        return None
    extension_size = struct.unpack("!H", body[offset : offset + 2])[0]
    offset += 2
    end = min(offset + extension_size, len(body))
    while offset + 4 <= end:
        extension_type, size = struct.unpack("!HH", body[offset : offset + 4])
        offset += 4
        extension = body[offset : offset + size]
        offset += size
        if extension_type != 0 or len(extension) < 5:
            continue
        list_size = struct.unpack("!H", extension[:2])[0]
        cursor = 2
        while cursor + 3 <= min(2 + list_size, len(extension)):
            name_type = extension[cursor]
            name_size = struct.unpack("!H", extension[cursor + 1 : cursor + 3])[0]
            cursor += 3
            name = extension[cursor : cursor + name_size]
            cursor += name_size
            if name_type == 0 and name:
                return name.decode("ascii", "replace").lower()
    return None


def parse_ipv4(frame):
    if len(frame) < 34:
        return None
    ethertype = struct.unpack("!H", frame[12:14])[0]
    offset = 14
    while ethertype in (0x8100, 0x88A8):
        if len(frame) < offset + 4:
            return None
        ethertype = struct.unpack("!H", frame[offset + 2 : offset + 4])[0]
        offset += 4
    if ethertype != 0x0800 or len(frame) < offset + 20:
        return None
    header_size = (frame[offset] & 0x0F) * 4
    if frame[offset] >> 4 != 4 or header_size < 20 or len(frame) < offset + header_size:
        return None
    total_size = struct.unpack("!H", frame[offset + 2 : offset + 4])[0]
    protocol = frame[offset + 9]
    source = socket.inet_ntoa(frame[offset + 12 : offset + 16])
    destination = socket.inet_ntoa(frame[offset + 16 : offset + 20])
    packet = frame[offset + header_size : offset + total_size]
    return protocol, source, destination, packet


def record(file, message):
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    line = "%s %s" % (stamp, message)
    file.write(line + "\n")
    file.flush()
    print(line, flush=True)


def netstat_connections():
    try:
        result = subprocess.run(
            ["netstat", "-ntp"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=3, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return {
        line.strip() for line in result.stdout.splitlines()
        if "ESTABLISHED" in line and "127.0.0.1:" not in line
    }


def main():
    if len(sys.argv) != 3:
        print("Usage: cloud_trace.py DURATION_SECONDS LOG_FILE", file=sys.stderr)
        return 2
    duration = int(sys.argv[1])
    log_path = Path(sys.argv[2])
    try:
        local_addresses = local_ipv4_addresses()
        capture = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
        capture.setblocking(False)
    except (AttributeError, OSError, RuntimeError) as error:
        print("Packet capture unavailable: %s" % error, file=sys.stderr)
        return 1

    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    deadline = started + duration
    previous_connections = set()
    flows = {}
    logged_syns = set()
    next_connections_poll = started
    with log_path.open("w", encoding="utf-8") as log_file:
        record(log_file, "START duration=%ds local_ipv4=%s" % (duration, ",".join(sorted(local_addresses))))
        record(log_file, "Metadata only: DNS names, endpoints, TCP process rows, and visible TLS SNI; no payload saved.")
        try:
            while time.monotonic() < deadline:
                ready, _, _ = select.select([capture], [], [], min(1, deadline - time.monotonic()))
                if ready:
                    try:
                        frame = capture.recv(65535)
                    except BlockingIOError:
                        frame = b""
                    parsed = parse_ipv4(frame)
                    if parsed:
                        protocol, source, destination, packet = parsed
                        if protocol == 17 and len(packet) >= 8:
                            source_port, destination_port, size = struct.unpack("!HHH", packet[:6])
                            if source in local_addresses and destination_port == 53:
                                try:
                                    for message in parse_dns(packet[8:size]):
                                        record(log_file, "%s -> %s:53 %s" % (source, destination, message))
                                except (ValueError, struct.error):
                                    pass
                            elif destination in local_addresses and source_port == 53:
                                try:
                                    for message in parse_dns(packet[8:size]):
                                        record(log_file, "%s:53 -> %s %s" % (source, destination, message))
                                except (ValueError, struct.error):
                                    pass
                        elif protocol == 6 and len(packet) >= 20:
                            source_port, destination_port, sequence = struct.unpack("!HHI", packet[:8])
                            header_size = (packet[12] >> 4) * 4
                            flags = packet[13]
                            if header_size < 20 or len(packet) < header_size or source not in local_addresses:
                                continue
                            payload = packet[header_size:]
                            flow = (source, destination, source_port, destination_port)
                            if flags & 0x02:
                                syn = (source, destination, source_port, destination_port)
                                if syn not in logged_syns:
                                    logged_syns.add(syn)
                                    record(
                                        log_file,
                                        "TCP SYN %s:%d -> %s:%d" % (
                                            source, source_port, destination, destination_port
                                        ),
                                    )
                            if payload:
                                expected, data = flows.get(flow, (sequence, b""))
                                if sequence == expected:
                                    data += payload
                                elif sequence < expected and sequence + len(payload) > expected:
                                    data += payload[expected - sequence :]
                                else:
                                    continue
                                data = data[:16384]
                                flows[flow] = (sequence + len(payload), data)
                                host = tls_sni(data)
                                if host:
                                    record(
                                        log_file,
                                        "TLS SNI %s:%d -> %s:%d host=%s" % (
                                            source, source_port, destination, destination_port, host
                                        ),
                                    )
                                    del flows[flow]
                            if flags & 0x01 or flags & 0x04:
                                flows.pop(flow, None)

                now = time.monotonic()
                if now >= next_connections_poll:
                    current = netstat_connections()
                    for connection in sorted(current - previous_connections):
                        record(log_file, "NETSTAT " + connection)
                    previous_connections = current
                    next_connections_poll = now + 5
        except KeyboardInterrupt:
            record(log_file, "STOP interrupted by user")
        finally:
            capture.close()
            record(log_file, "STOP capture finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
