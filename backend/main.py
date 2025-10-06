from dotenv import load_dotenv
load_dotenv()

import uuid
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
from datetime import datetime, timedelta
from bson import ObjectId
import asyncio
from config import Config

from database import (
    connect_to_mongo, close_mongo_connection, get_database,
    create_temp_work_update, get_temp_work_update, delete_temp_work_update,
    cleanup_abandoned_temp_updates, get_database_stats, verify_ttl_index
)
from ai_service import AIFollowupService
from quality_score import initialize_quality_scorer, get_quality_scorer
from models import (
    GenerateQuestionsRequest, FollowupAnswersUpdate, TestAIResponse,
    WorkUpdateCreate, SessionStatus, WorkStatus,
    QualityAnalysisRequest, QualityAnalysisResponse, 
    WeeklyReportRequest, WeeklyReportResponse
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

cleanup_task = None

async def scheduled_cleanup_task():
    while True:
        try:
            logger.info("Running scheduled cleanup...")
            ttl_working = await verify_ttl_index()
            result = await cleanup_abandoned_temp_updates(25 if ttl_working else 24)
            deleted = result.get("deleted_temp_updates", 0)
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} temp updates")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        await asyncio.sleep(3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global cleanup_task
    try:
        Config.validate_config_simplified()
        await connect_to_mongo()
        initialize_quality_scorer()
        
        cleanup_task = asyncio.create_task(scheduled_cleanup_task())
        
        config_summary = Config.get_api_key_summary()
        logger.info(f"System: {config_summary['ai_provider']}")
        logger.info(f"Cost: ${config_summary['cost_per_request']} per request")
        logger.info("Application started with LM Studio")
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise
    
    yield
    
    if cleanup_task:
        cleanup_task.cancel()
    await close_mongo_connection()

app = FastAPI(
    title="Intern Management AI Service - LM Studio",
    description="AI-powered follow-up with LM Studio (Local, Free)",
    version="3.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_ai_service() -> AIFollowupService:
    try:
        return AIFollowupService()
    except Exception as e:
        logger.error(f"AI service init failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {
        "message": "Intern Management AI - LM Studio Edition",
        "version": "3.0.0",
        "ai_provider": "LM Studio (Local)",
        "cost": 0.0,
        "requirements": {
            "lm_studio": "Running on localhost:1234",
            "model": "Phi-3-Mini loaded"
        }
    }

@app.get("/health")
async def health_check():
    try:
        db = get_database()
        await db.command("ping")
        
        ai_service = AIFollowupService()
        lmstudio_test = await ai_service.test_ai_connection()
        lmstudio_ok = lmstudio_test.get("summary", {}).get("lmstudio_working", False)
        
        return {
            "status": "healthy" if lmstudio_ok else "degraded",
            "database": "connected",
            "lm_studio": "connected" if lmstudio_ok else "offline",
            "lm_studio_url": Config.LMSTUDIO_URL,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

@app.post("/api/work-updates")
async def create_work_update(
    work_update: WorkUpdateCreate,
    ai_service: AIFollowupService = Depends(get_ai_service)
):
    try:
        intern_id = work_update.user_id.strip()
        
        if work_update.status in [WorkStatus.WORKING, WorkStatus.WFH]:
            if not work_update.task or not work_update.task.strip():
                raise HTTPException(status_code=400, detail="Task required for working/wfh status")
        
        db = get_database()
        today = datetime.now().strftime('%Y-%m-%d')
        
        if work_update.status == WorkStatus.LEAVE:
            daily_records = db["dailyrecords"]
            existing = await daily_records.find_one({"internId": intern_id, "date": today})
            
            record = {
                "internId": intern_id,
                "date": today,
                "stack": work_update.stack,
                "task": work_update.task or "On Leave",
                "progress": "On Leave",
                "blockers": "On Leave",
                "status": "leave"
            }
            
            if existing:
                await daily_records.replace_one({"_id": existing["_id"]}, record)
                record_id = str(existing["_id"])
            else:
                result = await daily_records.insert_one(record)
                record_id = str(result.inserted_id)
            
            return {
                "success": True,
                "message": "Leave status saved",
                "user_id": intern_id,
                "recordId": record_id,
                "redirectToFollowup": False,
                "status": "completed"
            }
        
        else:
            quality_result = await ai_service.process_work_update_with_quality_check(
                work_update.task, intern_id, today
            )
            
            score = quality_result.get("quality_score", 0)
            needs_followup = quality_result.get("needs_followup", False)
            
            if needs_followup:
                temp_record = {
                    "internId": intern_id,
                    "date": today,
                    "stack": work_update.stack,
                    "task": work_update.task,
                    "progress": work_update.progress,
                    "blockers": work_update.blockers,
                    "status": work_update.status,
                    "submittedAt": datetime.now(),
                    "followupCompleted": False,
                    "temp_status": "pending_followup",
                    "qualityScore": score
                }
                
                temp_id = await create_temp_work_update(temp_record)
                
                return {
                    "success": True,
                    "message": f"Requires follow-up (Score: {score}/10)",
                    "user_id": intern_id,
                    "tempWorkUpdateId": temp_id,
                    "redirectToFollowup": True,
                    "qualityScore": score,
                    "status": "pending_followup"
                }
            else:
                daily_records = db["dailyrecords"]
                existing = await daily_records.find_one({"internId": intern_id, "date": today})
                
                record = {
                    "internId": intern_id,
                    "date": today,
                    "stack": work_update.stack,
                    "task": work_update.task,
                    "progress": work_update.progress,
                    "blockers": work_update.blockers,
                    "status": work_update.status,
                    "qualityScore": score,
                    "followupSkipped": True
                }
                
                if existing:
                    await daily_records.replace_one({"_id": existing["_id"]}, record)
                    record_id = str(existing["_id"])
                else:
                    result = await daily_records.insert_one(record)
                    record_id = str(result.inserted_id)
                
                return {
                    "success": True,
                    "message": f"High quality (Score: {score}/10) - No follow-up needed",
                    "user_id": intern_id,
                    "recordId": record_id,
                    "redirectToFollowup": False,
                    "qualityScore": score,
                    "status": "completed"
                }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/followups/start")
async def start_followup(
    request: GenerateQuestionsRequest,
    ai_service: AIFollowupService = Depends(get_ai_service)
):
    try:
        intern_id = request.user_id.strip()
        db = get_database()
        
        temp_collection = db[Config.TEMP_WORK_UPDATES_COLLECTION]
        temp_update = await temp_collection.find_one(
            {"internId": intern_id, "temp_status": "pending_followup"},
            sort=[("submittedAt", -1)]
        )
        
        if not temp_update:
            raise HTTPException(status_code=404, detail="No pending work update found")
        
        temp_id = str(temp_update["_id"])
        today = datetime.now().strftime('%Y-%m-%d')
        session_id = f"{intern_id}_{uuid.uuid4().hex}"
        
        quality_result = await ai_service.process_work_update_with_quality_check(
            temp_update.get("task", ""), intern_id, today
        )
        
        questions = quality_result.get("followup_data", {}).get("questions", 
                                                                 ai_service._get_default_questions())
        
        followup_collection = db[Config.FOLLOWUP_SESSIONS_COLLECTION]
        session = {
            "_id": session_id,
            "internId": intern_id,
            "tempWorkUpdateId": temp_id,
            "session_date": today,
            "questions": questions,
            "answers": [""] * len(questions),
            "status": SessionStatus.PENDING,
            "createdAt": datetime.now(),
            "completedAt": None
        }
        
        await followup_collection.replace_one({"_id": session_id}, session, upsert=True)
        
        return {
            "success": True,
            "message": "Follow-up session started",
            "user_id": intern_id,
            "sessionId": session_id,
            "questions": questions
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/followup/{session_id}/complete")
async def complete_followup(session_id: str, answers_update: FollowupAnswersUpdate):
    try:
        intern_id = answers_update.user_id.strip()
        
        if not answers_update.answers or len(answers_update.answers) != 3:
            raise HTTPException(status_code=400, detail="Need exactly 3 answers")
        
        db = get_database()
        followup_collection = db[Config.FOLLOWUP_SESSIONS_COLLECTION]
        
        session = await followup_collection.find_one({"_id": session_id})
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        if str(session.get("internId")) != str(intern_id):
            raise HTTPException(status_code=403, detail="Access denied")
        
        temp_update = await get_temp_work_update(session["tempWorkUpdateId"])
        if not temp_update:
            raise HTTPException(status_code=404, detail="Temp update not found")
        
        await followup_collection.update_one(
            {"_id": session_id},
            {"$set": {
                "answers": answers_update.answers,
                "status": SessionStatus.COMPLETED,
                "completedAt": datetime.now()
            }}
        )
        
        daily_records = db[Config.DAILY_RECORDS_COLLECTION]
        record = {
            "internId": intern_id,
            "date": temp_update["date"],
            "stack": temp_update["stack"],
            "task": temp_update["task"],
            "progress": temp_update.get("progress", ""),
            "blockers": temp_update.get("blockers", ""),
            "status": temp_update["status"],
            "qualityScore": temp_update.get("qualityScore", 0),
            "followupCompleted": True,
            "followupAnswers": answers_update.answers
        }
        
        existing = await daily_records.find_one({
            "internId": intern_id,
            "date": temp_update["date"]
        })
        
        if existing:
            await daily_records.replace_one({"_id": existing["_id"]}, record)
            record_id = str(existing["_id"])
        else:
            result = await daily_records.insert_one(record)
            record_id = str(result.inserted_id)
        
        await delete_temp_work_update(session["tempWorkUpdateId"])
        
        return {
            "success": True,
            "message": "Follow-up completed",
            "user_id": intern_id,
            "sessionId": session_id,
            "dailyRecordId": record_id,
            "status": "completed"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/quality/analyze", response_model=QualityAnalysisResponse)
async def analyze_quality(request: QualityAnalysisRequest):
    try:
        quality_scorer = get_quality_scorer()
        needs_followup, details = await quality_scorer.should_trigger_followup(
            request.work_description, request.user_id
        )
        
        return QualityAnalysisResponse(
            user_id=request.user_id,
            quality_score=details.get("quality_score", 0),
            needs_followup=needs_followup,
            analysis={
                "word_count": details.get("word_count", 0),
                "keyword_found": details.get("keyword_found", False),
                "sentiment_label": details.get("sentiment_label", "neutral"),
                "sentiment_polarity": details.get("sentiment_polarity", 0),
                "is_repetition": details.get("is_repetition", False),
                "has_structure": details.get("has_structure", False),
                "flagged": details.get("flagged", False),
                "flag_reasons": details.get("flag_reasons", [])
            },
            recommendation="Follow-up recommended" if needs_followup else "Good quality",
            threshold=Config.QUALITY_SCORE_THRESHOLD
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/reports/weekly", response_model=WeeklyReportResponse)
async def weekly_report(
    request: WeeklyReportRequest,
    ai_service: AIFollowupService = Depends(get_ai_service)
):
    try:
        if request.start_date and request.end_date:
            start = datetime.strptime(request.start_date, '%Y-%m-%d')
            end = datetime.strptime(request.end_date, '%Y-%m-%d')
        else:
            end = datetime.now()
            start = end - timedelta(days=7)
        
        result = await ai_service.generate_weekly_report(request.user_id, start, end)
        
        if result.get("success"):
            return WeeklyReportResponse(
                success=True,
                user_id=request.user_id,
                report=result["report"],
                metadata={
                    "user_id": request.user_id,
                    "date_range": {
                        "start": start.strftime('%Y-%m-%d'),
                        "end": end.strftime('%Y-%m-%d')
                    },
                    "data_summary": result.get("data_summary", {}),
                    "generated_at": datetime.now().isoformat()
                }
            )
        else:
            return WeeklyReportResponse(
                success=False,
                user_id=request.user_id,
                message=result.get("message", "Failed"),
                metadata={"user_id": request.user_id}
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/followup-sessions/list")
async def list_sessions(request: GenerateQuestionsRequest, limit: int = 50):
    try:
        db = get_database()
        followup_collection = db[Config.FOLLOWUP_SESSIONS_COLLECTION]
        
        cursor = followup_collection.find(
            {"internId": request.user_id.strip()}
        ).sort("createdAt", -1).limit(limit)
        
        sessions = await cursor.to_list(length=limit)
        
        for session in sessions:
            if "_id" in session:
                session["sessionId"] = session["_id"]
                del session["_id"]
        
        return {
            "success": True,
            "user_id": request.user_id,
            "sessions": sessions,
            "count": len(sessions)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ai/test", response_model=TestAIResponse)
async def test_ai():
    try:
        ai_service = AIFollowupService()
        test_results = await ai_service.test_ai_connection()
        
        return TestAIResponse(
            success=test_results.get("summary", {}).get("overall_status") == "healthy",
            message="LM Studio test completed",
            test_results={
                "timestamp": datetime.now().isoformat(),
                "test_results": test_results,
                "provider": "LM Studio",
                "server_url": Config.LMSTUDIO_URL
            }
        )
    except Exception as e:
        return TestAIResponse(
            success=False,
            message="Test failed - Is LM Studio running on port 1234?",
            test_results={"error": str(e)}
        )

@app.get("/stats")
async def get_stats():
    try:
        stats = await get_database_stats()
        
        ai_service = AIFollowupService()
        lmstudio_test = await ai_service.test_ai_connection()
        lmstudio_ok = lmstudio_test.get("summary", {}).get("lmstudio_working", False)
        
        if stats:
            stats["ai_provider"] = {
                "type": "local",
                "name": "LM Studio",
                "status": "connected" if lmstudio_ok else "offline",
                "cost_per_request": 0.0
            }
        
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("Starting LM Studio Edition")
    print("Make sure LM Studio is running on port 1234!")
    print("=" * 60)
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=Config.DEBUG)