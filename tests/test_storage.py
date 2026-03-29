"""Property-based tests for data storage layer.

Feature: data-storage
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from hypothesis import given, strategies as st, settings

from dm_bot.storage import (
    Connection,
    ConnectionRepository,
    Conversation,
    ConversationRepository,
    DatabaseManager,
    Message,
    MessageRepository,
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def db_manager():
    """Create an in-memory database manager for testing."""
    manager = DatabaseManager(db_path=Path(":memory:"))
    manager.initialize_schema()
    yield manager
    manager.close()


@pytest.fixture
def connection_repo(db_manager):
    """Create a ConnectionRepository with an in-memory database."""
    return ConnectionRepository(db_manager)


# =============================================================================
# Hypothesis Strategies
# =============================================================================


@st.composite
def connection_data(draw):
    """Generate valid Connection data.
    
    Generates linkedin_slug, display_name, and profile_url that are valid
    for storage in SQLite.
    """
    # LinkedIn slugs: alphanumeric with hyphens, non-empty
    slug = draw(
        st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(
                whitelist_categories=("L", "N"),
                whitelist_characters="-",
            ),
        ).filter(lambda s: s.strip() and not s.startswith("-") and not s.endswith("-"))
    )
    
    # Display names: printable text, non-empty
    name = draw(
        st.text(
            min_size=1,
            max_size=200,
            alphabet=st.characters(
                min_codepoint=32,
                max_codepoint=126,
                blacklist_characters=["\x00"],
            ),
        ).filter(lambda s: s.strip())
    )
    
    url = f"https://linkedin.com/in/{slug}"
    
    # Generate timestamps
    first_seen = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 1, 1),
        )
    )
    updated = draw(
        st.datetimes(
            min_value=first_seen,
            max_value=datetime(2030, 1, 1),
        )
    )
    
    return Connection(
        linkedin_slug=slug,
        display_name=name,
        profile_url=url,
        first_seen_at=first_seen,
        updated_at=updated,
    )


# =============================================================================
# Property Tests for ConnectionRepository
# =============================================================================


# Feature: data-storage, Property 1: Connection round-trip consistency
# Validates: Requirements 1.1, 1.3
@settings(max_examples=100, deadline=None)
@given(conn_data=connection_data())
def test_property_1_connection_round_trip_consistency(conn_data: Connection) -> None:
    """
    Property 1: Connection round-trip consistency
    
    For any valid Connection data, storing it and then querying by linkedin_slug
    should return a Connection with equivalent linkedin_slug, display_name, and
    profile_url values.
    
    **Feature: data-storage, Property 1: Connection round-trip consistency**
    **Validates: Requirements 1.1, 1.3**
    """
    # Create fresh database for each test
    manager = DatabaseManager(db_path=Path(":memory:"))
    manager.initialize_schema()
    repo = ConnectionRepository(manager)
    
    try:
        # Store the connection
        stored = repo.upsert(conn_data)
        
        # Retrieve by slug
        retrieved = repo.get_by_slug(conn_data.linkedin_slug)
        
        # Verify round-trip consistency
        assert retrieved is not None, (
            f"Expected to find connection with slug '{conn_data.linkedin_slug}'"
        )
        assert retrieved.linkedin_slug == conn_data.linkedin_slug, (
            f"linkedin_slug mismatch: expected '{conn_data.linkedin_slug}', "
            f"got '{retrieved.linkedin_slug}'"
        )
        assert retrieved.display_name == conn_data.display_name, (
            f"display_name mismatch: expected '{conn_data.display_name}', "
            f"got '{retrieved.display_name}'"
        )
        assert retrieved.profile_url == conn_data.profile_url, (
            f"profile_url mismatch: expected '{conn_data.profile_url}', "
            f"got '{retrieved.profile_url}'"
        )
        assert retrieved.id is not None, "Expected id to be populated after storage"
    finally:
        manager.close()



# Feature: data-storage, Property 2: Connection upsert idempotency
# Validates: Requirements 1.2
@settings(max_examples=100, deadline=None)
@given(conn_data=connection_data(), num_upserts=st.integers(min_value=2, max_value=5))
def test_property_2_connection_upsert_idempotency(
    conn_data: Connection, num_upserts: int
) -> None:
    """
    Property 2: Connection upsert idempotency
    
    For any Connection, storing it multiple times should result in exactly one
    record in the database with that linkedin_slug.
    
    **Feature: data-storage, Property 2: Connection upsert idempotency**
    **Validates: Requirements 1.2**
    """
    # Create fresh database for each test
    manager = DatabaseManager(db_path=Path(":memory:"))
    manager.initialize_schema()
    repo = ConnectionRepository(manager)
    
    try:
        # Upsert the same connection multiple times
        for _ in range(num_upserts):
            repo.upsert(conn_data)
        
        # Count records with this slug
        all_connections = repo.list_all()
        matching = [c for c in all_connections if c.linkedin_slug == conn_data.linkedin_slug]
        
        assert len(matching) == 1, (
            f"Expected exactly 1 connection with slug '{conn_data.linkedin_slug}', "
            f"found {len(matching)} after {num_upserts} upserts"
        )
    finally:
        manager.close()



# Feature: data-storage, Property 3: Connection list ordering
# Validates: Requirements 1.4
@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_property_3_connection_list_ordering(data) -> None:
    """
    Property 3: Connection list ordering
    
    For any set of Connections with distinct updated_at timestamps, listing all
    connections should return them in descending order by updated_at.
    
    **Feature: data-storage, Property 3: Connection list ordering**
    **Validates: Requirements 1.4**
    """
    # Create fresh database for each test
    manager = DatabaseManager(db_path=Path(":memory:"))
    manager.initialize_schema()
    repo = ConnectionRepository(manager)
    
    try:
        # Generate 2-5 connections with distinct slugs and timestamps
        num_connections = data.draw(st.integers(min_value=2, max_value=5))
        
        # Generate distinct slugs
        slugs = data.draw(
            st.lists(
                st.text(
                    min_size=1,
                    max_size=50,
                    alphabet=st.characters(whitelist_categories=("L", "N")),
                ).filter(lambda s: s.strip()),
                min_size=num_connections,
                max_size=num_connections,
                unique=True,
            )
        )
        
        # Generate distinct timestamps
        base_time = datetime(2024, 1, 1)
        timestamps = [base_time + timedelta(hours=i * 10) for i in range(num_connections)]
        
        # Shuffle timestamps to insert in random order
        shuffled_indices = data.draw(st.permutations(list(range(num_connections))))
        
        # Insert connections in shuffled order
        for idx in shuffled_indices:
            conn = Connection(
                linkedin_slug=slugs[idx],
                display_name=f"User {idx}",
                profile_url=f"https://linkedin.com/in/{slugs[idx]}",
                first_seen_at=timestamps[idx],
                updated_at=timestamps[idx],
            )
            repo.upsert(conn)
        
        # List all connections
        all_connections = repo.list_all()
        
        # Verify ordering: should be descending by updated_at
        assert len(all_connections) == num_connections, (
            f"Expected {num_connections} connections, got {len(all_connections)}"
        )
        
        for i in range(len(all_connections) - 1):
            assert all_connections[i].updated_at >= all_connections[i + 1].updated_at, (
                f"Connections not in descending order by updated_at: "
                f"{all_connections[i].updated_at} should be >= {all_connections[i + 1].updated_at}"
            )
    finally:
        manager.close()


# =============================================================================
# Hypothesis Strategies for Conversation
# =============================================================================


@st.composite
def conversation_data(draw, connection_id: int):
    """Generate valid Conversation data for a given connection_id.
    
    Generates thread_url, last_message_at, last_synced_at, and created_at
    that are valid for storage in SQLite.
    """
    # Thread URL: optional, valid URL format
    thread_url = draw(
        st.one_of(
            st.none(),
            st.text(
                min_size=10,
                max_size=200,
                alphabet=st.characters(
                    whitelist_categories=("L", "N"),
                    whitelist_characters="-/_:",
                ),
            ).map(lambda s: f"https://linkedin.com/messaging/thread/{s}"),
        )
    )
    
    # Created at timestamp
    created_at = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 1, 1),
        )
    )
    
    # Last message at: optional, must be >= created_at if present
    last_message_at = draw(
        st.one_of(
            st.none(),
            st.datetimes(
                min_value=created_at,
                max_value=datetime(2030, 1, 1),
            ),
        )
    )
    
    # Last synced at: optional, must be >= created_at if present
    last_synced_at = draw(
        st.one_of(
            st.none(),
            st.datetimes(
                min_value=created_at,
                max_value=datetime(2030, 1, 1),
            ),
        )
    )
    
    return Conversation(
        connection_id=connection_id,
        thread_url=thread_url,
        last_message_at=last_message_at,
        last_synced_at=last_synced_at,
        created_at=created_at,
    )


def create_test_connection(manager: DatabaseManager) -> Connection:
    """Helper to create a test connection and return it with populated id."""
    repo = ConnectionRepository(manager)
    conn = Connection(
        linkedin_slug=f"test-user-{datetime.now().timestamp()}",
        display_name="Test User",
        profile_url="https://linkedin.com/in/test-user",
        first_seen_at=datetime(2024, 1, 1),
        updated_at=datetime(2024, 1, 1),
    )
    return repo.upsert(conn)


# =============================================================================
# Property Tests for ConversationRepository
# =============================================================================


# Feature: data-storage, Property 4: Conversation round-trip consistency
# Validates: Requirements 2.1, 2.3
@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_property_4_conversation_round_trip_consistency(data) -> None:
    """
    Property 4: Conversation round-trip consistency
    
    For any valid Conversation data linked to an existing Connection, storing it
    and then querying by connection_id should return a Conversation with equivalent
    connection_id and thread_url values.
    
    **Feature: data-storage, Property 4: Conversation round-trip consistency**
    **Validates: Requirements 2.1, 2.3**
    """
    # Create fresh database for each test
    manager = DatabaseManager(db_path=Path(":memory:"))
    manager.initialize_schema()
    
    try:
        # First create a connection to link the conversation to
        stored_connection = create_test_connection(manager)
        assert stored_connection.id is not None
        
        # Generate conversation data for this connection
        conv_data = data.draw(conversation_data(stored_connection.id))
        
        # Store the conversation
        conv_repo = ConversationRepository(manager)
        stored = conv_repo.upsert(conv_data)
        
        # Retrieve by connection_id
        retrieved = conv_repo.get_by_connection_id(stored_connection.id)
        
        # Verify round-trip consistency
        assert retrieved is not None, (
            f"Expected to find conversation with connection_id {stored_connection.id}"
        )
        assert retrieved.connection_id == conv_data.connection_id, (
            f"connection_id mismatch: expected {conv_data.connection_id}, "
            f"got {retrieved.connection_id}"
        )
        assert retrieved.thread_url == conv_data.thread_url, (
            f"thread_url mismatch: expected '{conv_data.thread_url}', "
            f"got '{retrieved.thread_url}'"
        )
        assert retrieved.id is not None, "Expected id to be populated after storage"
    finally:
        manager.close()


# Feature: data-storage, Property 5: Conversation upsert idempotency
# Validates: Requirements 2.2
@settings(max_examples=100, deadline=None)
@given(data=st.data(), num_upserts=st.integers(min_value=2, max_value=5))
def test_property_5_conversation_upsert_idempotency(data, num_upserts: int) -> None:
    """
    Property 5: Conversation upsert idempotency
    
    For any Conversation, storing it multiple times should result in exactly one
    record in the database for that connection_id.
    
    **Feature: data-storage, Property 5: Conversation upsert idempotency**
    **Validates: Requirements 2.2**
    """
    # Create fresh database for each test
    manager = DatabaseManager(db_path=Path(":memory:"))
    manager.initialize_schema()
    
    try:
        # First create a connection to link the conversation to
        stored_connection = create_test_connection(manager)
        assert stored_connection.id is not None
        
        # Generate conversation data for this connection
        conv_data = data.draw(conversation_data(stored_connection.id))
        
        conv_repo = ConversationRepository(manager)
        
        # Upsert the same conversation multiple times
        for _ in range(num_upserts):
            conv_repo.upsert(conv_data)
        
        # Count records with this connection_id by querying directly
        conn = manager.connect()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM conversation WHERE connection_id = ?",
            (stored_connection.id,),
        )
        count = cursor.fetchone()[0]
        
        assert count == 1, (
            f"Expected exactly 1 conversation with connection_id {stored_connection.id}, "
            f"found {count} after {num_upserts} upserts"
        )
    finally:
        manager.close()


# Feature: data-storage, Property 9: Conversation sync query filtering
# Validates: Requirements 6.1, 6.2, 6.3
@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_property_9_conversation_sync_query_filtering(data) -> None:
    """
    Property 9: Conversation sync query filtering
    
    For any set of Conversations with various last_message_at and last_synced_at
    combinations, querying for conversations needing sync should return only those
    where last_message_at > last_synced_at, respecting the since filter and limit
    parameter.
    
    **Feature: data-storage, Property 9: Conversation sync query filtering**
    **Validates: Requirements 6.1, 6.2, 6.3**
    """
    # Create fresh database for each test
    manager = DatabaseManager(db_path=Path(":memory:"))
    manager.initialize_schema()
    
    try:
        conn_repo = ConnectionRepository(manager)
        conv_repo = ConversationRepository(manager)
        
        # Generate 3-6 conversations with different sync states
        num_conversations = data.draw(st.integers(min_value=3, max_value=6))
        
        base_time = datetime(2024, 1, 1)
        conversations_needing_sync = []
        
        for i in range(num_conversations):
            # Create a unique connection for each conversation
            connection = Connection(
                linkedin_slug=f"user-{i}-{data.draw(st.integers(min_value=1000, max_value=9999))}",
                display_name=f"User {i}",
                profile_url=f"https://linkedin.com/in/user-{i}",
                first_seen_at=base_time,
                updated_at=base_time,
            )
            stored_conn = conn_repo.upsert(connection)
            assert stored_conn.id is not None, "Connection should have id after upsert"
            connection_id: int = stored_conn.id
            
            # Decide sync state for this conversation
            sync_state = data.draw(st.sampled_from([
                "needs_sync",      # last_message_at > last_synced_at
                "synced",          # last_message_at <= last_synced_at
                "never_synced",    # last_synced_at is None, last_message_at is set
                "no_messages",     # last_message_at is None
            ]))
            
            created_at = base_time + timedelta(hours=i)
            
            if sync_state == "needs_sync":
                last_message_at = base_time + timedelta(hours=i + 10)
                last_synced_at = base_time + timedelta(hours=i + 5)
                conversations_needing_sync.append(connection_id)
            elif sync_state == "synced":
                last_message_at = base_time + timedelta(hours=i + 5)
                last_synced_at = base_time + timedelta(hours=i + 10)
            elif sync_state == "never_synced":
                last_message_at = base_time + timedelta(hours=i + 10)
                last_synced_at = None
                conversations_needing_sync.append(connection_id)
            else:  # no_messages
                last_message_at = None
                last_synced_at = None
            
            conv = Conversation(
                connection_id=connection_id,
                thread_url=f"https://linkedin.com/messaging/thread/{i}",
                last_message_at=last_message_at,
                last_synced_at=last_synced_at,
                created_at=created_at,
            )
            conv_repo.upsert(conv)
        
        # Query conversations needing sync
        needing_sync = conv_repo.get_needing_sync()
        
        # Verify: all returned conversations should need sync
        returned_connection_ids = {c.connection_id for c in needing_sync}
        expected_connection_ids = set(conversations_needing_sync)
        
        assert returned_connection_ids == expected_connection_ids, (
            f"Sync query mismatch: expected connection_ids {expected_connection_ids}, "
            f"got {returned_connection_ids}"
        )
        
        # Verify each returned conversation actually needs sync
        for conv in needing_sync:
            assert conv.last_message_at is not None, (
                "Conversation needing sync should have last_message_at set"
            )
            assert conv.last_synced_at is None or conv.last_message_at > conv.last_synced_at, (
                f"Conversation should need sync: last_message_at={conv.last_message_at}, "
                f"last_synced_at={conv.last_synced_at}"
            )
        
        # Test limit parameter
        if len(conversations_needing_sync) > 1:
            limited = conv_repo.get_needing_sync(limit=1)
            assert len(limited) <= 1, (
                f"Expected at most 1 result with limit=1, got {len(limited)}"
            )
        
        # Test since parameter
        if conversations_needing_sync:
            # Get a conversation that needs sync
            sample_conv = needing_sync[0]
            if sample_conv.last_message_at:
                # Query with since = last_message_at should include this conversation
                since_results = conv_repo.get_needing_sync(since=sample_conv.last_message_at)
                matching = [c for c in since_results if c.connection_id == sample_conv.connection_id]
                assert len(matching) == 1, (
                    f"Expected conversation with connection_id {sample_conv.connection_id} "
                    f"to be included when since={sample_conv.last_message_at}"
                )
    finally:
        manager.close()



# =============================================================================
# Hypothesis Strategies for Message
# =============================================================================


@st.composite
def message_data(draw, conversation_id: int):
    """Generate valid Message data for a given conversation_id.
    
    Generates content, timestamp, direction, and synced_at that are valid
    for storage in SQLite.
    """
    # Content: non-empty text
    content = draw(
        st.text(
            min_size=1,
            max_size=1000,
            alphabet=st.characters(
                min_codepoint=32,
                max_codepoint=126,
                blacklist_characters=["\x00"],
            ),
        ).filter(lambda s: s.strip())
    )
    
    # Timestamp
    timestamp = draw(
        st.datetimes(
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 1, 1),
        )
    )
    
    # Direction
    direction = draw(st.sampled_from(["inbound", "outbound"]))
    
    # Synced at: must be >= timestamp
    synced_at = draw(
        st.datetimes(
            min_value=timestamp,
            max_value=datetime(2030, 1, 1),
        )
    )
    
    # Optional fields
    linkedin_msg_id = draw(
        st.one_of(
            st.none(),
            st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))),
        )
    )
    
    return Message(
        conversation_id=conversation_id,
        content=content,
        timestamp=timestamp,
        direction=direction,
        synced_at=synced_at,
        linkedin_msg_id=linkedin_msg_id,
    )


def create_test_conversation(manager: DatabaseManager) -> tuple[Connection, Conversation]:
    """Helper to create a test connection and conversation, returning both with populated ids."""
    conn_repo = ConnectionRepository(manager)
    conv_repo = ConversationRepository(manager)
    
    connection = Connection(
        linkedin_slug=f"test-user-{datetime.now().timestamp()}",
        display_name="Test User",
        profile_url="https://linkedin.com/in/test-user",
        first_seen_at=datetime(2024, 1, 1),
        updated_at=datetime(2024, 1, 1),
    )
    stored_conn = conn_repo.upsert(connection)
    
    conversation = Conversation(
        connection_id=stored_conn.id,  # type: ignore[arg-type]
        thread_url="https://linkedin.com/messaging/thread/test",
        created_at=datetime(2024, 1, 1),
    )
    stored_conv = conv_repo.upsert(conversation)
    
    return stored_conn, stored_conv


# =============================================================================
# Property Tests for MessageRepository
# =============================================================================


# Feature: data-storage, Property 6: Message round-trip consistency
# Validates: Requirements 3.1, 3.3, 3.4
@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_property_6_message_round_trip_consistency(data) -> None:
    """
    Property 6: Message round-trip consistency
    
    For any valid Message data linked to an existing Conversation, storing it
    and then querying by conversation_id should include a Message with equivalent
    content, timestamp, and direction values.
    
    **Feature: data-storage, Property 6: Message round-trip consistency**
    **Validates: Requirements 3.1, 3.3, 3.4**
    """
    # Create fresh database for each test
    manager = DatabaseManager(db_path=Path(":memory:"))
    manager.initialize_schema()
    
    try:
        # Create a connection and conversation
        _, stored_conv = create_test_conversation(manager)
        assert stored_conv.id is not None
        
        # Generate message data for this conversation
        msg_data = data.draw(message_data(stored_conv.id))
        
        # Store the message
        msg_repo = MessageRepository(manager)
        stored = msg_repo.store(msg_data)
        
        # Retrieve by conversation_id
        messages = msg_repo.get_by_conversation(stored_conv.id)
        
        # Verify round-trip consistency
        assert len(messages) >= 1, (
            f"Expected at least 1 message for conversation_id {stored_conv.id}"
        )
        
        # Find the message we stored
        matching = [m for m in messages if m.dedup_key == stored.dedup_key]
        assert len(matching) == 1, (
            f"Expected exactly 1 message with dedup_key '{stored.dedup_key}'"
        )
        
        retrieved = matching[0]
        assert retrieved.content == msg_data.content, (
            f"content mismatch: expected '{msg_data.content}', got '{retrieved.content}'"
        )
        assert retrieved.timestamp == msg_data.timestamp, (
            f"timestamp mismatch: expected {msg_data.timestamp}, got {retrieved.timestamp}"
        )
        assert retrieved.direction == msg_data.direction, (
            f"direction mismatch: expected '{msg_data.direction}', got '{retrieved.direction}'"
        )
        assert retrieved.id is not None, "Expected id to be populated after storage"
        assert retrieved.dedup_key is not None, "Expected dedup_key to be populated after storage"
    finally:
        manager.close()


# Feature: data-storage, Property 7: Message deduplication idempotency
# Validates: Requirements 3.2, 5.1
@settings(max_examples=100, deadline=None)
@given(data=st.data(), num_stores=st.integers(min_value=2, max_value=5))
def test_property_7_message_deduplication_idempotency(data, num_stores: int) -> None:
    """
    Property 7: Message deduplication idempotency
    
    For any Message, storing it multiple times (same conversation_id, timestamp,
    and content) should result in exactly one record in the database.
    
    **Feature: data-storage, Property 7: Message deduplication idempotency**
    **Validates: Requirements 3.2, 5.1**
    """
    # Create fresh database for each test
    manager = DatabaseManager(db_path=Path(":memory:"))
    manager.initialize_schema()
    
    try:
        # Create a connection and conversation
        _, stored_conv = create_test_conversation(manager)
        assert stored_conv.id is not None
        
        # Generate message data for this conversation
        msg_data = data.draw(message_data(stored_conv.id))
        
        msg_repo = MessageRepository(manager)
        
        # Store the same message multiple times
        stored_messages = []
        for _ in range(num_stores):
            stored = msg_repo.store(msg_data)
            stored_messages.append(stored)
        
        # All stored messages should have the same id (same record)
        ids = {m.id for m in stored_messages}
        assert len(ids) == 1, (
            f"Expected all stores to return the same message id, got {ids}"
        )
        
        # Count records in database
        conn = manager.connect()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM message WHERE conversation_id = ?",
            (stored_conv.id,),
        )
        count = cursor.fetchone()[0]
        
        assert count == 1, (
            f"Expected exactly 1 message in database after {num_stores} stores, "
            f"found {count}"
        )
    finally:
        manager.close()


# Feature: data-storage, Property 8: Message ordering by timestamp
# Validates: Requirements 3.3
@settings(max_examples=100, deadline=None)
@given(data=st.data())
def test_property_8_message_ordering_by_timestamp(data) -> None:
    """
    Property 8: Message ordering by timestamp
    
    For any set of Messages in a conversation with distinct timestamps, querying
    messages for that conversation should return them in ascending order by timestamp.
    
    **Feature: data-storage, Property 8: Message ordering by timestamp**
    **Validates: Requirements 3.3**
    """
    # Create fresh database for each test
    manager = DatabaseManager(db_path=Path(":memory:"))
    manager.initialize_schema()
    
    try:
        # Create a connection and conversation
        _, stored_conv = create_test_conversation(manager)
        assert stored_conv.id is not None
        
        msg_repo = MessageRepository(manager)
        
        # Generate 3-6 messages with distinct timestamps
        num_messages = data.draw(st.integers(min_value=3, max_value=6))
        
        base_time = datetime(2024, 1, 1)
        timestamps = [base_time + timedelta(hours=i * 10) for i in range(num_messages)]
        
        # Shuffle timestamps to insert in random order
        shuffled_indices = data.draw(st.permutations(list(range(num_messages))))
        
        # Insert messages in shuffled order
        for idx in shuffled_indices:
            msg = Message(
                conversation_id=stored_conv.id,
                content=f"Message {idx}",
                timestamp=timestamps[idx],
                direction="inbound" if idx % 2 == 0 else "outbound",
                synced_at=timestamps[idx],
            )
            msg_repo.store(msg)
        
        # Retrieve messages
        messages = msg_repo.get_by_conversation(stored_conv.id)
        
        # Verify ordering: should be ascending by timestamp
        assert len(messages) == num_messages, (
            f"Expected {num_messages} messages, got {len(messages)}"
        )
        
        for i in range(len(messages) - 1):
            assert messages[i].timestamp <= messages[i + 1].timestamp, (
                f"Messages not in ascending order by timestamp: "
                f"{messages[i].timestamp} should be <= {messages[i + 1].timestamp}"
            )
    finally:
        manager.close()


# Feature: data-storage, Property 10: Deduplication key determinism
# Validates: Requirements 5.1
@settings(max_examples=100, deadline=None)
@given(
    conversation_id=st.integers(min_value=1, max_value=10000),
    timestamp=st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 1, 1)),
    content=st.text(min_size=1, max_size=500).filter(lambda s: s.strip()),
)
def test_property_10_deduplication_key_determinism(
    conversation_id: int, timestamp: datetime, content: str
) -> None:
    """
    Property 10: Deduplication key determinism
    
    For any combination of conversation_id, timestamp, and content, generating
    the deduplication key multiple times should produce the same result.
    
    **Feature: data-storage, Property 10: Deduplication key determinism**
    **Validates: Requirements 5.1**
    """
    # Generate the key multiple times
    key1 = MessageRepository.generate_dedup_key(conversation_id, timestamp, content)
    key2 = MessageRepository.generate_dedup_key(conversation_id, timestamp, content)
    key3 = MessageRepository.generate_dedup_key(conversation_id, timestamp, content)
    
    # All keys should be identical
    assert key1 == key2, (
        f"Dedup key not deterministic: first call returned '{key1}', "
        f"second call returned '{key2}'"
    )
    assert key2 == key3, (
        f"Dedup key not deterministic: second call returned '{key2}', "
        f"third call returned '{key3}'"
    )
    
    # Key should be a valid SHA256 hex string (64 characters)
    assert len(key1) == 64, (
        f"Expected SHA256 hex string (64 chars), got {len(key1)} chars"
    )
    assert all(c in "0123456789abcdef" for c in key1), (
        f"Expected hex string, got '{key1}'"
    )
