import serial
import time
import PySimpleGUI as sg
import os

PORT = "COM3"
BAUD_RATE = 9600
TOTAL_BLOCKS = 101  # 96 main + 5 auxiliary

def enter_programming_mode(ser, window):
    magic = b"\x50\xBB\xFF\x20\x12\x07\x25"
    window["status"].update(f"Sending magic command: {magic.hex()}")
    ser.flush()
    ser.write(magic)
    time.sleep(1)
    
    response = ser.read(1)
    window["status"].update(f"Initial response: {response.hex() if response else 'Nothing'}")
    if response != b"\x06":
        raise Exception("Initial ACK not received")
    
    window["status"].update("Requesting identifier...")
    ser.write(b"\x02")
    ident = ser.read(8)
    window["status"].update(f"Identifier: {ident.hex() if ident else 'Nothing'}")
    if len(ident) != 8:
        raise Exception("Incomplete identifier")
    
    window["status"].update("Confirming clone mode...")
    ser.write(b"\x06")
    confirm = ser.read(1)
    window["status"].update(f"Confirmation: {confirm.hex() if confirm else 'Nothing'}")
    if confirm != b"\x06":
        raise Exception("Clone mode not confirmed")
    
    window["status"].update("Programming mode activated.")
    return ident

def read_block(ser, addr, nbytes=0x40, window=None):
    cmd = b"S" + bytes([addr >> 8, addr & 0xFF, nbytes])
    if window:
        window["status"].update(f"Reading block {addr:04x}: Sending {cmd.hex()}")
    ser.write(cmd)
    time.sleep(1)
    
    if addr != 0:
        ack = ser.read(1)
        if window and ack:
            window["status"].update(f"Delayed ACK: {ack.hex()}")
        if ack and ack != b"\x06":
            raise Exception(f"Invalid delayed ACK: {ack.hex()}")
    
    header = ser.read(4)
    if window:
        window["status"].update(f"Header: {header.hex() if header else 'Nothing'}")
    if not header or header[0] != ord('X'):
        raise Exception(f"Invalid header: {header.hex()}")
    if header[1] != (addr >> 8) or header[2] != (addr & 0xFF) or header[3] != nbytes:
        raise Exception(f"Header mismatch: {header.hex()}")
    
    data = ser.read(nbytes)
    if window:
        window["status"].update(f"Data: {data.hex()[:32]}... ({len(data)} bytes)")
    if len(data) != nbytes:
        raise Exception(f"Only received {len(data)} bytes of {nbytes}")
    
    time.sleep(0.5)
    return data

def download(window, filepath):
    with serial.Serial(PORT, BAUD_RATE, timeout=5) as ser:
        ident = enter_programming_mode(ser, window)
        window["status"].update(f"Radio identified: {ident.hex()}")
        
        data = ident  # Include identifier at start
        block_count = 0
        
        # Main block (0x0000 - 0x17FF, 6144 bytes)
        window["status"].update("Downloading main block...")
        for addr in range(0, 0x1800, 0x40):
            data += read_block(ser, addr, window=window)
            block_count += 1
            window["progress"].update(block_count, 96)  # 96 main blocks
            window["bytes"].update(f"Progress: {len(data)} bytes")
        
        # Auxiliary block (0x1EC0 - 0x1FFF, 320 bytes)
        window["status"].update("Downloading auxiliary block...")
        aux_data = b""
        for addr in range(0x1EC0, 0x2000, 0x40):  # Up to 0x1FFF
            remaining = min(0x40, 0x2000 - addr)  # Adjust for last block
            if remaining > 0:  # Only read if there is data
                aux_data += read_block(ser, addr, nbytes=remaining, window=window)
                block_count += 1
                window["progress"].update(block_count, 101)  # 96 + 5 blocks
                window["bytes"].update(f"Progress: {len(data) + len(aux_data)} bytes")
        data += aux_data
        
        with open(filepath, "wb") as f:
            f.write(data[:6472])  # Ensure exactly 6472 bytes
        window["status"].update(f"Saved to {filepath} (6472 bytes)")

# Graphical interface
layout = [
    [sg.Text("Turn off the UV-5R and connect the cable before continuing.")],
    [sg.Text("Save as:"), sg.Input(default_text="uv5r.bin", key="filename"), sg.FileSaveAs("Choose", file_types=(("BIN Files", "*.bin"),))],
    [sg.Text("Status:"), sg.Text("Waiting...", key="status", size=(50, 1))],
    [sg.Text("Progress:"), sg.ProgressBar(101, orientation="h", size=(20, 20), key="progress")],
    [sg.Text("Bytes downloaded:"), sg.Text("0 bytes", key="bytes")],
    [sg.Button("Download"), sg.Button("Exit")]
]

window = sg.Window("UV-5R Clone Utility", layout, finalize=True)

while True:
    event, values = window.read()
    if event in (sg.WIN_CLOSED, "Exit"):
        break
    if event == "Download":
        filepath = values["filename"]
        if not filepath:
            sg.popup_error("Please select a filename.")
            continue
        try:
            window["status"].update("Starting download...")
            download(window, filepath)
            sg.popup("Download complete", f"Saved to {filepath}")
        except Exception as e:
            sg.popup_error(f"Error: {e}")
        finally:
            window["status"].update("Disconnect the cable and turn on the radio.")

window.close()
