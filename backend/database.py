from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import DESCENDING, ASCENDING
from config import Config
import logging
from datetime import datetime, timedelta
from bson import ObjectId

logger = logging.getLogger(__name__)

class Database:
    client: AsyncIOMotorClient = None
    database = None

database = Database()

# Collection names
TEMP_WORK_UPDATES_COLLECTION = "temp_work_updates"

async def connect_to_mongo():
    """Create database connection"""
    try:
        database.client = AsyncIOMotorClient(Config.MONGODB_URL)
        database.database = database.client[Config.DATABASE_NAME]
        
        # Test the connection
        await database.client.admin.command('ping')
        logger.info("Connected to MongoDB successfully")
        
        # FIXED: Clean up problematic indexes first, then create proper ones
        await cleanup_problematic_indexes()
        
        # Create clean indexes
        await create_clean_indexes()
        
        # Run cleaned data migration
        await run_clean_migration()
        
        # Setup TTL indexes for automatic cleanup
        await setup_ttl_indexes()
        
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise

async def close_mongo_connection():
    """Close database connection"""
    if database.client:
        database.client.close()
        logger.info("Disconnected from MongoDB")

async def cleanup_problematic_indexes():
    """Remove problematic indexes that cause conflicts"""
    try:
        collections_to_clean = [
            (Config.WORK_UPDATES_COLLECTION, "work_updates"),
            (TEMP_WORK_UPDATES_COLLECTION, "temp_work_updates"),
            (Config.FOLLOWUP_SESSIONS_COLLECTION, "followup_sessions")
        ]
        
        for collection_name, display_name in collections_to_clean:
            collection = database.database[collection_name]
            
            try:
                existing_indexes = await collection.list_indexes().to_list(length=None)
                
                for index in existing_indexes:
                    index_name = index.get('name', '')
                    index_key = index.get('key', {})
                    
                    # Drop problematic userId-based indexes
                    if ('userId' in index_key and index_name != '_id_'):
                        try:
                            await collection.drop_index(index_name)
                            logger.info(f"Dropped problematic index '{index_name}' from {display_name}")
                        except Exception as e:
                            logger.warning(f"Could not drop index '{index_name}' from {display_name}: {e}")
                
                logger.info(f"Cleaned problematic indexes from {display_name}")
                
            except Exception as e:
                logger.warning(f"Could not clean indexes from {display_name}: {e}")
        
    except Exception as e:
        logger.warning(f"Index cleanup failed: {e}")



async def create_clean_indexes():
    """Create clean indexes without conflicts"""
    try:
        # Work updates indexes (using internId)
        work_updates = database.database[Config.WORK_UPDATES_COLLECTION]
        
        await work_updates.create_index("internId", sparse=True, name="internId_1_clean")
        await work_updates.create_index([("internId", 1), ("submittedAt", DESCENDING)], sparse=True, name="internId_submittedAt_clean")
        await work_updates.create_index([("internId", 1), ("date", 1)], sparse=True, name="internId_date_clean")
        await work_updates.create_index([("internId", 1), ("followupCompleted", 1)], sparse=True, name="internId_followupCompleted_clean")
        await work_updates.create_index([("followupCompleted", 1), ("submittedAt", DESCENDING)], name="followupCompleted_submittedAt_clean")
        
        # Temporary work updates indexes
        temp_work_updates = database.database[TEMP_WORK_UPDATES_COLLECTION]
        await temp_work_updates.create_index("internId", sparse=True, name="temp_internId_1_clean")
        await temp_work_updates.create_index([("internId", 1), ("date", 1)], sparse=True, name="temp_internId_date_clean")
        await temp_work_updates.create_index([("submittedAt", 1), ("status", 1)], name="temp_submittedAt_status_clean")
        
        # Followup sessions indexes (using internId)
        followup_sessions = database.database[Config.FOLLOWUP_SESSIONS_COLLECTION]
        await followup_sessions.create_index("internId", sparse=True, name="sessions_internId_1_clean")
        await followup_sessions.create_index([("internId", 1), ("status", 1)], sparse=True, name="sessions_internId_status_clean")
        await followup_sessions.create_index([("internId", 1), ("createdAt", DESCENDING)], sparse=True, name="sessions_internId_createdAt_clean")
        await followup_sessions.create_index([("internId", 1), ("session_date", 1)], sparse=True, name="sessions_internId_session_date_clean")
        
        # Linking indexes
        await followup_sessions.create_index("workUpdateId", name="sessions_workUpdateId_clean")
        await followup_sessions.create_index("tempWorkUpdateId", name="sessions_tempWorkUpdateId_clean")
        await followup_sessions.create_index([("workUpdateId", 1), ("status", 1)], name="sessions_workUpdateId_status_clean")
        
        # Compound index for efficient pending session queries
        await followup_sessions.create_index([
            ("internId", 1), 
            ("status", 1), 
            ("createdAt", DESCENDING)
        ], sparse=True, name="sessions_internId_status_createdAt_clean")
        
        logger.info("Clean database indexes created successfully")
        
    except Exception as e:
        logger.warning(f"Failed to create some clean indexes: {e}")

async def run_clean_migration():
    """
    Run clean migration without deleting existing data
    PRESERVES all followup sessions and work updates
    """
    try:
        # Step 1: Add followupCompleted field to documents missing it
        work_updates = database.database[Config.WORK_UPDATES_COLLECTION]
        
        sample_doc = await work_updates.find_one()
        if sample_doc and "followupCompleted" not in sample_doc:
            logger.info("Adding followupCompleted field to existing work updates...")
            
            result = await work_updates.update_many(
                {"followupCompleted": {"$exists": False}},
                {"$set": {"followupCompleted": True}}
            )
            
            logger.info(f"Added followupCompleted field to {result.modified_count} documents")
        
        # Step 2: SAFE migration from userId to internId
        # DO NOT DELETE - only migrate field names
        collections_to_migrate = [
            (Config.WORK_UPDATES_COLLECTION, "work_updates"),
            (TEMP_WORK_UPDATES_COLLECTION, "temp_work_updates"), 
            (Config.FOLLOWUP_SESSIONS_COLLECTION, "followup_sessions")
        ]
        
        for collection_name, display_name in collections_to_migrate:
            collection = database.database[collection_name]
            
            # Find documents that have userId but not internId
            docs_to_migrate = await collection.find({
                "userId": {"$exists": True, "$ne": None},
                "$or": [
                    {"internId": {"$exists": False}},
                    {"internId": None}
                ]
            }).to_list(length=None)
            
            if docs_to_migrate:
                logger.info(f"Migrating {len(docs_to_migrate)} documents in {display_name} (PRESERVING all data)...")
                
                migrated_count = 0
                
                for doc in docs_to_migrate:
                    user_id = doc.get('userId')
                    
                    if user_id is None:
                        # Skip null userId but DON'T delete
                        continue
                    
                    try:
                        # Copy userId to internId, keep userId for compatibility
                        await collection.update_one(
                            {"_id": doc["_id"]},
                            {"$set": {"internId": user_id}}
                            # NOTE: We keep userId field for backward compatibility
                        )
                        migrated_count += 1
                        
                    except Exception as e:
                        logger.warning(f"Failed to migrate document {doc['_id']} in {display_name}: {e}")
                
                logger.info(f"✅ Migration complete for {display_name}: {migrated_count} documents migrated (all data preserved)")
            else:
                logger.info(f"No documents to migrate in {display_name}")
        
        # Step 3: Count preserved followup sessions
        followup_collection = database.database[Config.FOLLOWUP_SESSIONS_COLLECTION]
        total_sessions = await followup_collection.count_documents({})
        pending_sessions = await followup_collection.count_documents({"status": "pending"})
        completed_sessions = await followup_collection.count_documents({"status": "completed"})
        
        logger.info(f"📊 Followup Sessions Preserved: {total_sessions} total "
                   f"({pending_sessions} pending, {completed_sessions} completed)")
        
        logger.info("✅ Clean data migration completed - ALL EXISTING DATA PRESERVED")
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")



async def setup_ttl_indexes():
    """Setup TTL index for automatic cleanup of temp work updates"""
    try:
        temp_collection = database.database[TEMP_WORK_UPDATES_COLLECTION]
        
        # Check if TTL index already exists
        existing_indexes = await temp_collection.list_indexes().to_list(length=None)
        
        ttl_index_exists = False
        for index in existing_indexes:
            index_key = index.get('key', {})
            if 'submittedAt' in index_key and 'expireAfterSeconds' in index:
                ttl_index_exists = True
                logger.info(f"TTL index already exists: {index['name']} (expires after {index['expireAfterSeconds']}s)")
                break
        
        # Create TTL index if it doesn't exist
        if not ttl_index_exists:
            await temp_collection.create_index(
                "submittedAt", 
                expireAfterSeconds=86400,  # 24 hours in seconds
                name="submittedAt_ttl_24h_clean"
            )
            logger.info("TTL index created successfully - documents expire after 24 hours")
        
        # Verify TTL index is working
        await verify_ttl_index()
        
    except Exception as e:
        logger.error(f"Failed to setup TTL indexes: {e}")
        raise

async def verify_ttl_index():
    """Verify that TTL index is properly configured"""
    try:
        temp_collection = database.database[TEMP_WORK_UPDATES_COLLECTION]
        
        # Get all indexes to verify TTL setup
        indexes = await temp_collection.list_indexes().to_list(length=None)
        
        for index in indexes:
            if 'expireAfterSeconds' in index and 'submittedAt' in index.get('key', {}):
                expire_seconds = index['expireAfterSeconds']
                expire_hours = expire_seconds / 3600
                logger.info(f"✅ TTL index verified: {index['name']} - expires after {expire_hours} hours")
                return True
        
        logger.warning("❌ No TTL index found on submittedAt field")
        return False
        
    except Exception as e:
        logger.error(f"Failed to verify TTL index: {e}")
        return False

async def create_temp_work_update(work_update_data: dict) -> str:
    """Create temporary work update with internId support and validation"""
    try:
        temp_collection = get_temp_collection()
        
        # Validate internId is provided
        intern_id = work_update_data.get("internId")
        if not intern_id:
            raise ValueError("internId is required for temporary work updates")
        
        # Check for existing temp update for same intern and date
        existing_temp = await temp_collection.find_one({
            "internId": intern_id,
            "date": work_update_data["date"]
        })
        
        if existing_temp:
            # Replace existing temp update
            await temp_collection.replace_one(
                {"_id": existing_temp["_id"]},
                work_update_data
            )
            logger.info(f"Replaced existing temp work update for intern {intern_id}")
            return str(existing_temp["_id"])
        else:
            # Create new temp update
            result = await temp_collection.insert_one(work_update_data)
            logger.info(f"Created new temp work update for intern {intern_id}: {result.inserted_id}")
            return str(result.inserted_id)
            
    except Exception as e:
        logger.error(f"Failed to create temp work update: {e}")
        raise

async def get_temp_work_update(temp_id: str) -> dict:
    """Get temporary work update by ID"""
    try:
        temp_collection = get_temp_collection()
        return await temp_collection.find_one({"_id": ObjectId(temp_id)})
    except Exception as e:
        logger.error(f"Failed to get temp work update: {e}")
        return None

async def delete_temp_work_update(temp_id: str) -> bool:
    """Delete temporary work update"""
    try:
        temp_collection = get_temp_collection()
        result = await temp_collection.delete_one({"_id": ObjectId(temp_id)})
        logger.info(f"Deleted temp work update {temp_id}: {result.deleted_count > 0}")
        return result.deleted_count > 0
    except Exception as e:
        logger.error(f"Failed to delete temp work update: {e}")
        return False

async def move_temp_to_permanent(temp_id: str, additional_data: dict = None) -> str:
    """Move temporary work update to permanent collection"""
    try:
        temp_collection = get_temp_collection()
        work_updates_collection = database.database[Config.WORK_UPDATES_COLLECTION]
        
        # Get temp work update
        temp_update = await temp_collection.find_one({"_id": ObjectId(temp_id)})
        if not temp_update:
            raise ValueError("Temporary work update not found")
        
        # Prepare permanent document
        permanent_update = temp_update.copy()
        del permanent_update["_id"]  # Remove temp ID
        
        # Add additional data if provided
        if additional_data:
            permanent_update.update(additional_data)
        
        # Set completion status
        permanent_update["followupCompleted"] = True
        permanent_update["completedAt"] = datetime.now()
        
        # Check for existing permanent update (override logic)
        intern_id = permanent_update.get("internId")
        if not intern_id:
            raise ValueError("Cannot move temp update without valid internId")
        
        existing_permanent = await work_updates_collection.find_one({
            "internId": intern_id,
            "update_date": permanent_update["update_date"]
        })
        
        if existing_permanent:
            # Override existing permanent work update
            await work_updates_collection.replace_one(
                {"_id": existing_permanent["_id"]},
                permanent_update
            )
            permanent_id = str(existing_permanent["_id"])
            logger.info(f"Updated existing permanent record: {permanent_id}")
        else:
            # Create new permanent work update
            result = await work_updates_collection.insert_one(permanent_update)
            permanent_id = str(result.inserted_id)
            logger.info(f"Created new permanent record: {permanent_id}")
        
        # Delete temp work update
        delete_result = await temp_collection.delete_one({"_id": ObjectId(temp_id)})
        
        if delete_result.deleted_count > 0:
            logger.info(f"Moved temp work update {temp_id} to permanent {permanent_id}")
        else:
            logger.warning(f"Temp work update {temp_id} might have already been deleted by TTL")
        
        return permanent_id
    
    except Exception as e:
        logger.error(f"Failed to move temp to permanent: {e}")
        raise

async def get_work_update_data(intern_id: str, work_update_id: str = None):
    """Get work update data for AI processing"""
    try:
        if not intern_id:
            logger.error("intern_id is required to get work update data")
            return None
            
        work_updates = database.database[Config.WORK_UPDATES_COLLECTION]
        temp_work_updates = database.database[TEMP_WORK_UPDATES_COLLECTION]
        
        if work_update_id:
            # Try permanent collection first
            work_update = await work_updates.find_one({"_id": ObjectId(work_update_id)})
            
            # If not found, try temp collection
            if not work_update:
                work_update = await temp_work_updates.find_one({"_id": ObjectId(work_update_id)})
        else:
            # Get latest work update for intern
            permanent_update = await work_updates.find_one(
                {"internId": intern_id},
                sort=[("submittedAt", DESCENDING)]
            )
            
            temp_update = await temp_work_updates.find_one(
                {"internId": intern_id},
                sort=[("submittedAt", DESCENDING)]
            )
            
            # Choose the most recent one
            if permanent_update and temp_update:
                perm_time = permanent_update.get("submittedAt", datetime.min)
                temp_time = temp_update.get("submittedAt", datetime.min)
                work_update = temp_update if temp_time > perm_time else permanent_update
            else:
                work_update = permanent_update or temp_update
        
        if not work_update:
            return None
        
        # Extract relevant data for AI processing
        data = {
            "description": work_update.get("task", ""),
            "challenges": work_update.get("progress", ""),
            "plans": work_update.get("blockers", ""),
            "user_id": work_update.get("internId"),
            "submitted_at": work_update.get("submittedAt")
        }
        
        return data
        
    except Exception as e:
        logger.error(f"Failed to get work update data: {e}")
        return None

async def cleanup_abandoned_temp_updates(hours_old: int = 24):
    """
    Clean up ONLY temporary work updates that are truly abandoned
    NEVER touches followup_sessions collection
    Followup sessions are PERMANENT records and should never be auto-deleted
    """
    try:
        temp_collection = database.database[TEMP_WORK_UPDATES_COLLECTION]
        
        cutoff_time = datetime.now() - timedelta(hours=hours_old)
        
        # Only clean temp_work_updates, NOT followup_sessions
        abandoned_cursor = temp_collection.find({
            "submittedAt": {"$lt": cutoff_time},
            "temp_status": "pending_followup"
        })
        
        abandoned_count = 0
        
        async for temp_update in abandoned_cursor:
            # Delete the temp update only
            await temp_collection.delete_one({"_id": temp_update["_id"]})
            abandoned_count += 1
        
        if abandoned_count > 0:
            logger.info(f"Manual cleanup: {abandoned_count} abandoned temp updates (followup sessions preserved)")
        else:
            logger.info("Manual cleanup: No abandoned temporary updates found (TTL working properly)")
        
        # Verify followup sessions are intact
        followup_collection = database.database[Config.FOLLOWUP_SESSIONS_COLLECTION]
        total_sessions = await followup_collection.count_documents({})
        logger.info(f"✅ Followup sessions preserved: {total_sessions} total sessions remain intact")
        
        return {
            "deleted_temp_updates": abandoned_count,
            "deleted_sessions": 0,  # We NEVER delete sessions
            "preserved_sessions": total_sessions,
            "note": "Followup sessions are permanent records and are always preserved"
        }
        
    except Exception as e:
        logger.error(f"Failed to cleanup abandoned temp updates: {e}")
        return {
            "deleted_temp_updates": 0,
            "deleted_sessions": 0,
            "error": str(e)
        }

async def get_database_stats():
    """Get database statistics for monitoring"""
    try:
        work_updates = database.database[Config.WORK_UPDATES_COLLECTION]
        temp_work_updates = database.database[TEMP_WORK_UPDATES_COLLECTION]
        followup_sessions = database.database[Config.FOLLOWUP_SESSIONS_COLLECTION]
        
        # Count work updates
        total_work_updates = await work_updates.count_documents({})
        completed_followups = await work_updates.count_documents({"followupCompleted": True})
        incomplete_followups = await work_updates.count_documents({"followupCompleted": False})
        
        # Count temporary work updates
        total_temp_updates = await temp_work_updates.count_documents({})
        pending_temp_updates = await temp_work_updates.count_documents({"temp_status": "pending_followup"})
        
        # Count sessions
        total_sessions = await followup_sessions.count_documents({})
        pending_sessions = await followup_sessions.count_documents({"status": "pending"})
        completed_sessions = await followup_sessions.count_documents({"status": "completed"})
        
        # Check TTL index status
        ttl_status = await verify_ttl_index()
        
        stats = {
            "work_updates": {
                "total": total_work_updates,
                "completed_followups": completed_followups,
                "incomplete_followups": incomplete_followups
            },
            "temp_work_updates": {
                "total": total_temp_updates,
                "pending": pending_temp_updates
            },
            "followup_sessions": {
                "total": total_sessions,
                "pending": pending_sessions,
                "completed": completed_sessions
            },
            "ttl_index": {
                "active": ttl_status,
                "cleanup_interval": "24 hours",
                "status": "Automatic deletion enabled" if ttl_status else "TTL index not found"
            }
        }
        
        logger.info(f"Database Stats: {stats}")
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get database stats: {e}")
        return None

async def get_user_work_history(intern_id: str, limit: int = 10) -> list:
    """Get work history for a specific user from both collections"""
    try:
        if not intern_id:
            logger.error("intern_id is required to get work history")
            return []
            
        work_updates = database.database[Config.WORK_UPDATES_COLLECTION]
        temp_work_updates = database.database[TEMP_WORK_UPDATES_COLLECTION]
        
        # Get from permanent collection
        permanent_cursor = work_updates.find(
            {"internId": intern_id}
        ).sort("submittedAt", DESCENDING).limit(limit)
        
        permanent_updates = await permanent_cursor.to_list(length=limit)
        
        # Get from temp collection
        temp_cursor = temp_work_updates.find(
            {"internId": intern_id}
        ).sort("submittedAt", DESCENDING).limit(limit)
        
        temp_updates = await temp_cursor.to_list(length=limit)
        
        # Combine and sort by timestamp
        all_updates = permanent_updates + temp_updates
        all_updates.sort(
            key=lambda x: x.get("submittedAt", datetime.min), 
            reverse=True
        )
        
        return all_updates[:limit]
        
    except Exception as e:
        logger.error(f"Failed to get user work history: {e}")
        return []

async def get_user_followup_sessions(intern_id: str, limit: int = 10) -> list:
    """Get followup sessions for a specific user"""
    try:
        if not intern_id:
            logger.error("intern_id is required to get followup sessions")
            return []
            
        followup_sessions = database.database[Config.FOLLOWUP_SESSIONS_COLLECTION]
        
        cursor = followup_sessions.find(
            {"internId": intern_id}
        ).sort("createdAt", DESCENDING).limit(limit)
        
        sessions = await cursor.to_list(length=limit)
        
        # Convert ObjectId to string for JSON serialization
        for session in sessions:
            if "_id" in session:
                session["sessionId"] = str(session["_id"])
        
        return sessions
        
    except Exception as e:
        logger.error(f"Failed to get user followup sessions: {e}")
        return []

async def get_pending_sessions_count() -> int:
    """Get count of pending followup sessions across all users"""
    try:
        followup_sessions = database.database[Config.FOLLOWUP_SESSIONS_COLLECTION]
        return await followup_sessions.count_documents({"status": "pending"})
    except Exception as e:
        logger.error(f"Failed to get pending sessions count: {e}")
        return 0

async def get_active_users_today() -> list:
    """Get list of users who submitted work updates today"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        
        work_updates = database.database[Config.WORK_UPDATES_COLLECTION]
        temp_work_updates = database.database[TEMP_WORK_UPDATES_COLLECTION]
        daily_records = database.database["dailyrecords"]
        
        # Get users from all collections for today
        active_users = set()
        
        # From work_updates
        work_cursor = work_updates.find({"date": today}, {"internId": 1})
        async for doc in work_cursor:
            if doc.get("internId"):
                active_users.add(doc["internId"])
        
        # From temp_work_updates
        temp_cursor = temp_work_updates.find({"date": today}, {"internId": 1})
        async for doc in temp_cursor:
            if doc.get("internId"):
                active_users.add(doc["internId"])
        
        # From daily_records (LogBook)
        daily_cursor = daily_records.find({"date": today}, {"internId": 1})
        async for doc in daily_cursor:
            if doc.get("internId"):
                active_users.add(str(doc["internId"]))  # ObjectId to string
        
        return list(active_users)
        
    except Exception as e:
        logger.error(f"Failed to get active users today: {e}")
        return []

def get_database():
    """Get database instance"""
    return database.database

def get_temp_collection():
    """Get temporary work updates collection"""
    return database.database[TEMP_WORK_UPDATES_COLLECTION]

def get_work_updates_collection():
    """Get work updates collection"""
    return database.database[Config.WORK_UPDATES_COLLECTION]

def get_followup_sessions_collection():
    """Get followup sessions collection"""
    return database.database[Config.FOLLOWUP_SESSIONS_COLLECTION]

def get_daily_records_collection():
    """Get LogBook daily records collection"""
    return database.database["dailyrecords"]