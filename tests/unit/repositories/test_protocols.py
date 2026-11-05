# SPDX-License-Identifier: AGPL-3.0-or-later
from app.repositories.dynamodb_messages import DynamoDBMessageRepository
from app.repositories.dynamodb_profiles import DynamoDBProfileRepository
from app.repositories.dynamodb_sessions import DynamoDBSessionRepository
from app.repositories.protocols import MessageRepository, ProfileRepository, SessionRepository


def test_dynamodb_repositories_implement_protocols(
    profiles: DynamoDBProfileRepository,
    sessions: DynamoDBSessionRepository,
    messages: DynamoDBMessageRepository,
) -> None:
    # mypy checks these assignments structurally: a missing or mismatched method fails
    # type checking, so services can depend on the Protocols alone.
    profile_repository: ProfileRepository = profiles
    session_repository: SessionRepository = sessions
    message_repository: MessageRepository = messages

    assert (profile_repository, session_repository, message_repository) == (
        profiles,
        sessions,
        messages,
    )
