"""Close all stuck active sessions."""
import asyncio
from backend.db import get_db
from backend.models import Session as SessionModel
from backend.session_manager import close_session, get_pipeline, unregister_pipeline
from sqlalchemy import select

async def main():
    async for db in get_db():
        r = await db.execute(select(SessionModel).where(SessionModel.status == "active"))
        rows = r.scalars().all()
        for row in rows:
            name = (row.skill_pack or {}).get("skill", {}).get("name", "?")
            print(f"Closing: {row.session_id} ({name})")
            pipeline = await get_pipeline(row.session_id)
            if pipeline:
                try:
                    await pipeline.stop()
                except Exception as e:
                    print(f"  pipeline.stop failed: {e}")
                await unregister_pipeline(row.session_id)
            await close_session(row.session_id, db)
            print("  Done")
        break

asyncio.run(main())
