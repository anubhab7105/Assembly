"""
Assembly — Conversations API Routes

Manages conversation history for authenticated users.
"""


from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.core.security import get_current_user_id
from src.database.base import get_db
from src.database.models import Conversation, Message
from src.database.schemas import ConversationListItem, ConversationResponse

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("/", response_model=list[ConversationListItem])
def list_conversations(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """List all conversations for the current user, most recent first."""
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )

    result = []
    for conv in conversations:
        msg_count = db.query(Message).filter(Message.conversation_id == conv.id).count()
        item = ConversationListItem(
            id=conv.id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=msg_count,
        )
        result.append(item)

    return result


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Get a conversation with all its messages."""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    return ConversationResponse.model_validate(conv)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """Delete a conversation and all its messages."""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
        .first()
    )
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    db.delete(conv)
    db.commit()
