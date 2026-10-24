"""Assistant conversation routes (US8 T092 + US5 T103, contracts/api.md).

Conversations live in memory, owned by ``user_id``; another user's conversation id is a 404.
Posting a message runs one ``run_turn`` with the user reloaded from the database.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from hcm_lite.api.deps import current_user, services, today
from hcm_lite.assistant.context import AppContext
from hcm_lite.assistant.runner import run_turn
from hcm_lite.errors import NotFound, ValidationError
from hcm_lite.models.domain import AuthenticatedUser

router = APIRouter(tags=["assistant"])


class CreateConversation(BaseModel):
    pass


class PostMessage(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def _conversation(request: Request, user: AuthenticatedUser, cid: str) -> Any:
    conversation = request.app.state.conversations.get(user.user_id, cid)
    if conversation is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found"}})
    return conversation


@router.post("/assistant/conversations", status_code=201)
async def create_conversation(request: Request,
                              user: AuthenticatedUser = Depends(current_user)) -> dict:
    cid = request.app.state.conversations.create(user.user_id)
    return {"conversation_id": cid}


@router.post("/assistant/conversations/{cid}/messages")
async def post_message(cid: str, body: PostMessage, request: Request,
                       user: AuthenticatedUser = Depends(current_user),
                       svc=Depends(services), _today=Depends(today)) -> dict:
    conversation = _conversation(request, user, cid)
    conversation.touch()
    ctx = AppContext(user=user, session=conversation, today=_today, services=svc)
    result = await run_turn(ctx, body.message)
    conversation.touch()
    return {
        "reply": result.final_text,
        "citations": [citation.model_dump(mode="json") for citation in result.citations],
        "ready_draft": (result.ready_draft.model_dump(mode="json")
                        if result.ready_draft is not None else None),
        "error_category": result.error_category,
    }


@router.post("/assistant/conversations/{cid}/drafts/{draft_id}/confirm")
async def confirm_draft(cid: str, draft_id: str, request: Request,
                        user: AuthenticatedUser = Depends(current_user),
                        svc=Depends(services), _today=Depends(today)) -> dict:
    conversation = _conversation(request, user, cid)
    try:
        record = await svc.leave.submit(user, conversation, draft_id, channel="api",
                                        today=_today)
    except NotFound:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found"}}) from None
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "invalid_input", "message": exc.message,
                              "field": exc.field}}) from None
    submitted_before = conversation.get_draft(draft_id)
    already = (submitted_before is not None
               and submitted_before.status.value == "submitted")
    conversation.history.append(
        {"role": "system",
         "content": f"Leave request submitted with reference {record.id} (status pending)."})
    return JSONResponse(status_code=200 if already else 201,
                        content={"reference": record.id, "status": record.status.value})


@router.delete("/assistant/conversations/{cid}/drafts/{draft_id}", status_code=204)
async def discard_draft(cid: str, draft_id: str, request: Request,
                        user: AuthenticatedUser = Depends(current_user)) -> None:
    conversation = _conversation(request, user, cid)
    conversation.discard_draft(draft_id)
