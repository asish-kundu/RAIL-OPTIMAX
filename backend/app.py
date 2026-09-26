from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from backend.routes.train import router as train_router
from backend.routes.maintenance import router as maintenance_router
from backend.routes.block import router as block_router
from backend.routes.ai import router as ai_router
from backend.routes.adapt_route import router as adapt_router
from backend.routes.ws_telemetry import router as ws_router
from backend.routes.operator import router as operator_router
from backend.routes.manage_route import router as manage_router
from backend.services.runtime import OperationalState
from backend.services.telemetry import TelemetryHub
from backend.services.ai1_plan import AI1Planner

@asynccontextmanager
async def lifespan(app:FastAPI):
    await OperationalState.initialize()
    await AI1Planner.generate(reason="STARTUP_BASELINE")
    await TelemetryHub.start()
    try: yield
    finally: await TelemetryHub.stop()

app=FastAPI(title="RAIL-OPTIMAX OCC Decision Support",version="3.0.0",lifespan=lifespan)
import os
allowed_origins=[x.strip() for x in os.getenv("RAILOPTIMAX_ALLOWED_ORIGINS", "*").split(",") if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=allowed_origins,allow_credentials=False,allow_methods=["GET","POST","OPTIONS"],allow_headers=["*"])
app.include_router(train_router);app.include_router(maintenance_router);app.include_router(block_router);app.include_router(ai_router);app.include_router(adapt_router);app.include_router(ws_router);app.include_router(operator_router);app.include_router(manage_router)

@app.get("/health",tags=["System"])
async def health():
    s=await OperationalState.read();return {"status":"ok","service":"RAIL-OPTIMAX OCC","version":app.version,"sequence":s["sequence"],"trains":len(s["trains"]),"active_blocks":sum(1 for b in s["blocks"] if b.get("status")=="Active"),"ai1_solver":s["ai1"].get("solver"),"ai3_conflicts":s["ai3"].get("active_conflicts_count",0),"ai3_controls":len(s["ai3"].get("controls",{})),"controller_mode":s["ai3"].get("controller_mode","CLOSED_LOOP_SIMULATION"),"persistence_error":s.get("persistence",{}).get("error")}

@app.get("/api/state",tags=["System"])
async def state(): return await OperationalState.snapshot()

frontend_path=Path(__file__).resolve().parent.parent/"frontend"
if frontend_path.exists(): app.mount("/",StaticFiles(directory=str(frontend_path),html=True),name="frontend")

if __name__=="__main__":
 import uvicorn;uvicorn.run("backend.app:app",host="127.0.0.1",port=8000,reload=False)
