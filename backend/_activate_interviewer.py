"""Activate the Technical Interviewer skill pack."""
import asyncio
from backend.db import get_db
from backend.models import SkillPack
from sqlalchemy import select, update

async def main():
    async for db in get_db():
        result = await db.execute(
            select(SkillPack).where(SkillPack.name == "Technical Interviewer")
        )
        row = result.scalar_one_or_none()
        if row:
            await db.execute(
                update(SkillPack).where(SkillPack.id == row.id).values(is_active=True)
            )
            await db.commit()
            print(f"Activated: {row.name} (id={row.id[:8]})")
        else:
            print("Technical Interviewer not found")
        break

asyncio.run(main())
