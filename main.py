from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn
import os
import qrcode 
import emojis
import uuid

app = FastAPI()

# Create required directories
os.makedirs("logs", exist_ok=True)
os.makedirs("voices", exist_ok=True)

# Store connected clients as (WebSocket, username)
clients = []

from fastapi import Request

@app.get("/", response_class=HTMLResponse)
async def get(request: Request):
    user_agent = request.headers.get("user-agent", "").lower()
    if "mobile" in user_agent or "android" in user_agent or "iphone" in user_agent:
        return HTMLResponse('<script>window.location.href="/mobile";</script>')
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/mobile")
async def mobile():
    with open("mobile.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/voice/{filename}")
async def get_voice(filename: str):
    file_path = os.path.join("voices", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, media_type="audio/webm")
    return {"error": "File not found"}, 404

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    name = await websocket.receive_text()
    clients.append((websocket, name))
    print(f"🔵 {name} joined the chat")

    try:
        # Load chat history
        log_dir = "logs"
        seen_logs = set()
        for fname in sorted(os.listdir(log_dir)):
            if name.lower() in fname.lower():
                log_file = os.path.join(log_dir, fname)
                if log_file not in seen_logs:
                    with open(log_file, "r", encoding="utf-8") as f:
                        for line in f:
                            await websocket.send_text(line.strip())
                    seen_logs.add(log_file)

        await broadcast(f"🟢 {name} joined the chat")

        while True:
            try:
                message = await websocket.receive()

                # Client disconnected manually or via browser
                if message.get("type") == "websocket.disconnect":
                    raise WebSocketDisconnect

                # 🟡 Voice Note
                if "bytes" in message:
                    voice_id = str(uuid.uuid4()) + ".webm"
                    voice_path = os.path.join("voices", voice_id)
                    with open(voice_path, "wb") as f:
                        f.write(message["bytes"])

                    voice_url = f"/voice/{voice_id}"
                    voice_msg = f"{name} sent a voice note: {voice_url}"

                    for other_ws, other_name in clients:
                        if other_name != name:
                            log_file = get_log_file(name, other_name)
                            save_to_log(log_file, voice_msg)
                            await other_ws.send_text(voice_msg)

                    await websocket.send_text(voice_msg)
                    continue

                # 🟢 Text Message
                if "text" in message:
                    msg = message["text"].strip()

                    if msg.lower().startswith(f"{name.lower()}:"):
                        msg = msg[len(name)+1:].strip()

                    formatted_msg = f"{name}: {msg}"

                    sent_to = set()
                    for other_ws, other_name in clients:
                        if other_name == name:
                            continue

                        log_file = get_log_file(name, other_name)
                        if log_file not in sent_to:
                            save_to_log(log_file, formatted_msg)
                            sent_to.add(log_file)

                        await other_ws.send_text(formatted_msg)

                    await websocket.send_text(formatted_msg)
                else:
                    print(f"⚠️ Unknown message format received: {message}")

            except WebSocketDisconnect:
                break

    finally:
        if (websocket, name) in clients:
            clients.remove((websocket, name))
        print(f"🔴 {name} left the chat")
        await broadcast(f"🔻 {name} left the chat")

async def broadcast(message: str):
    for ws, _ in clients:
        try:
            await ws.send_text(message)
        except:
            pass

def get_log_file(user1, user2):
    users = sorted([user1.lower(), user2.lower()])
    filename = f"{users[0]}-{users[1]}.txt"
    return os.path.join("logs", filename)

def save_to_log(log_file, message):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(message + "\n")

def show_qr(link):
    print("\n📱 Scan this QR code to open mobile chat:\n")
    qr = qrcode.QRCode()
    qr.add_data(link)
    qr.make()
    qr.print_ascii(invert=True)

if __name__ == "__main__":
    ip_info = os.popen("ipconfig").read()
    ip_lines = [line.split(":")[1].strip() for line in ip_info.splitlines()
                if "IPv4 Address" in line and "169." not in line]
    if ip_lines:
        link = f"http://{ip_lines[0]}:8000/mobile"
        print(f"🌐 Mobile Chat (LAN): {link}")
        show_qr(link)

    uvicorn.run("main:app", host="0.0.0.0", port=10000, reload=True)
