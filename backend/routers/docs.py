"""Documentation router - serves skill.md file."""

import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["docs"])


@router.get("/skill.md")
async def get_skill_documentation(request: Request):
    """Serve the skill.md documentation file - internal use only.

    Requires X-Requested-With header from frontend to prevent direct browser access.
    Users should access documentation via the /docs UI page.
    """
    # Check for internal request header
    requested_with = request.headers.get("X-Requested-With", "")
    if requested_with != "VeroFrontend":
        raise HTTPException(
            status_code=403,
            detail="Direct access not allowed. Please use the documentation page at /docs"
        )

    skill_md_path = os.path.join(os.path.dirname(__file__), "..", "..", "skill.md")
    if os.path.exists(skill_md_path):
        with open(skill_md_path, "r") as f:
            content = f.read()
        return PlainTextResponse(content, media_type="text/markdown")
    raise HTTPException(status_code=404, detail="skill.md not found")
