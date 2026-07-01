"""
qr_generator.py - QR code generation and decoding for QR Attendance System
"""

import os
import qrcode
import cv2
from pyzbar import pyzbar

QR_DIR = os.path.join("static", "qr_codes")
os.makedirs(QR_DIR, exist_ok=True)


def generate_qr(student_id, name):
    """Generate a QR code for a student and save it as a PNG. Returns the file path."""
    data     = f"{student_id}|{name}"
    qr_image = qrcode.make(data)
    filename = f"qr_{student_id}.png"
    path     = os.path.join(QR_DIR, filename)
    qr_image.save(path)
    return path


def decode_qr_from_frame(frame):
    """Decode the first QR code found in an OpenCV frame. Returns the string data or None."""
    decoded = pyzbar.decode(frame)
    if decoded:
        return decoded[0].data.decode("utf-8")
    return None
