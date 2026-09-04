from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from soundtouch.ws import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            # Keep connection alive; client can send pings
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
