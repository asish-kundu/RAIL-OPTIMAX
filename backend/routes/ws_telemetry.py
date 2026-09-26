from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.services.telemetry import TelemetryHub
router=APIRouter(tags=["WebSocket Telemetry"])
@router.websocket("/ws/live-telemetry")
async def websocket_telemetry_stream(websocket:WebSocket):
    await websocket.accept(); queue=await TelemetryHub.subscribe()
    try:
        while True: await websocket.send_json(await queue.get())
    except (WebSocketDisconnect,RuntimeError): pass
    finally: await TelemetryHub.unsubscribe(queue)
