from datetime import datetime

from models.schemas import ConversationMessage, ModifyRequest, Session, TripPlan, TripRequest


def build_initial_session(session_id: str, request: TripRequest, plan: TripPlan) -> Session:
    """Create the first saved session payload for a freshly generated plan."""
    timestamp = datetime.now().isoformat()
    return Session(
        session_id=session_id,
        user_request=request,
        current_plan=plan,
        messages=[
            ConversationMessage(
                role="assistant",
                content=f"已为{request.city}生成{request.travel_days}天行程",
                timestamp=timestamp,
            )
        ],
        summary=f"用户计划去{request.city}旅行{request.travel_days}天",
        updated_at=timestamp,
    )


def apply_modified_plan(session: Session, request: ModifyRequest, updated_plan: TripPlan) -> Session:
    """Update a saved session after the user asks to modify the plan."""
    timestamp = datetime.now().isoformat()
    session.current_plan = updated_plan
    session.messages.append(
        ConversationMessage(
            role="user",
            content=request.instruction,
            timestamp=timestamp,
        )
    )
    session.messages.append(
        ConversationMessage(
            role="assistant",
            content="已根据您的要求修改行程",
            timestamp=timestamp,
        )
    )

    # Keep a short rolling history once the conversation grows.
    if len(session.messages) >= 10 and session.user_request:
        session.summary = (
            f"用户计划去{session.user_request.city}旅行"
            f"{session.user_request.travel_days}天，已进行多次修改"
        )
        session.messages = session.messages[-5:]

    session.updated_at = timestamp
    return session
