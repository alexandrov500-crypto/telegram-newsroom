from __future__ import annotations

import asyncio
import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from db import repository as repo
from db.models import Base, DraftStatus, RawPost
from db.retention import delete_old_processed_raw_posts, delete_old_rejected_drafts
from utils.text_hash import sha256_hex


def _sqlite_url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'repo_test.db'}"


async def _make_engine(url: str) -> tuple[AsyncEngine, async_sessionmaker]:
    engine = create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False, "timeout": 30.0},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    return engine, factory


def test_create_read_draft(tmp_path):
    async def body() -> None:
        engine, factory = await _make_engine(_sqlite_url(tmp_path))
        try:
            async with factory() as session:
                d = await repo.create_draft(
                    session,
                    content="Hello draft",
                    content_hash=sha256_hex("Hello draft"),
                    sources_payload=[{"channel": "@c", "message_id": 1}],
                )
                await session.commit()
                did = int(d.id)

            async with factory() as session:
                loaded = await repo.get_draft_by_id(session, did)
                assert loaded is not None
                assert loaded.content == "Hello draft"
                assert loaded.status == DraftStatus.PENDING.value
                sources = json.loads(loaded.sources)
                assert sources[0]["channel"] == "@c"
                assert sources[0]["message_id"] == 1
        finally:
            await engine.dispose()

    asyncio.run(body())


def test_draft_status_transition(tmp_path):
    async def body() -> None:
        engine, factory = await _make_engine(_sqlite_url(tmp_path))
        try:
            async with factory() as session:
                d = await repo.create_draft(
                    session,
                    content="x",
                    content_hash=sha256_hex("x"),
                    sources_payload=[{"channel": "@c", "message_id": 2}],
                )
                await session.commit()
                did = int(d.id)

            async with factory() as session:
                ok = await repo.try_transition_draft_status(
                    session, draft_id=did, from_status=DraftStatus.PENDING.value, to_status="publishing"
                )
                assert ok is True
                await session.commit()

            async with factory() as session:
                loaded = await repo.get_draft_by_id(session, did)
                assert loaded is not None
                assert loaded.status == "publishing"
        finally:
            await engine.dispose()

    asyncio.run(body())


def test_retention_processed_raw_and_rejected_drafts(tmp_path):
    async def body() -> None:
        engine, factory = await _make_engine(_sqlite_url(tmp_path))
        try:
            now = repo.utcnow()
            old = now - timedelta(days=90)
            recent = now - timedelta(days=1)

            async with factory() as session:
                await repo.upsert_raw_post(
                    session,
                    channel_name="@ch",
                    message_id=10,
                    text="old processed",
                    created_at=old,
                )
                await session.flush()
                rid = (
                    await session.execute(
                        select(RawPost.id).where(RawPost.channel_name == "@ch", RawPost.message_id == 10)
                    )
                ).scalar_one()
                await repo.mark_raw_posts_processed(session, [rid], old)
                await session.commit()

            async with factory() as session:
                n_raw = await delete_old_processed_raw_posts(session, older_than=now - timedelta(days=7))
                assert n_raw == 1
                await session.commit()

            async with factory() as session:
                d_old = await repo.create_draft(
                    session,
                    content="rej",
                    content_hash=sha256_hex("rej"),
                    sources_payload=[{"channel": "@c", "message_id": 3}],
                    status=DraftStatus.REJECTED.value,
                )
                d_keep = await repo.create_draft(
                    session,
                    content="keep",
                    content_hash=sha256_hex("keep"),
                    sources_payload=[{"channel": "@c", "message_id": 4}],
                    status=DraftStatus.REJECTED.value,
                )
                await session.flush()
                old_id = int(d_old.id)
                keep_id = int(d_keep.id)
                await session.commit()

            async with factory() as session:
                from sqlalchemy import update as sa_update

                from db.models import Draft

                await session.execute(sa_update(Draft).where(Draft.id == old_id).values(created_at=old))
                await session.execute(sa_update(Draft).where(Draft.id == keep_id).values(created_at=recent))
                await session.commit()

            async with factory() as session:
                n_d = await delete_old_rejected_drafts(session, older_than=now - timedelta(days=7))
                assert n_d == 1
                await session.commit()

            async with factory() as session:
                n_drafts = await repo.count_drafts(session)
                assert n_drafts == 1
        finally:
            await engine.dispose()

    asyncio.run(body())


def test_dedupe_fetch_and_hash_lookup(tmp_path):
    async def body() -> None:
        engine, factory = await _make_engine(_sqlite_url(tmp_path))
        try:
            h = sha256_hex("same body")
            async with factory() as session:
                await repo.create_draft(
                    session,
                    content="same body",
                    content_hash=h,
                    sources_payload=[{"channel": "@c", "message_id": 5}],
                )
                await session.commit()

            async with factory() as session:
                recent = await repo.fetch_recent_drafts_for_dedupe(session, limit=10, not_older_than=None)
                assert len(recent) == 1
                skip, reason = repo.draft_should_be_skipped_as_duplicate(
                    new_content="same body",
                    new_hash=h,
                    recent=recent,
                    similarity_threshold=0.99,
                )
                assert skip is True
                assert reason == "exact_hash_match"
        finally:
            await engine.dispose()

    asyncio.run(body())


def test_create_draft_and_mark_posts_processed(tmp_path):
    async def body() -> None:
        engine, factory = await _make_engine(_sqlite_url(tmp_path))
        try:
            now = repo.utcnow()
            async with factory() as session:
                ins = await repo.upsert_raw_post(
                    session,
                    channel_name="@c",
                    message_id=99,
                    text="raw",
                    created_at=now,
                )
                assert ins is True
                await session.flush()
                rid = (
                    await session.execute(
                        select(RawPost.id).where(RawPost.channel_name == "@c", RawPost.message_id == 99)
                    )
                ).scalar_one()

                d = await repo.create_draft_and_mark_posts_processed(
                    session,
                    content="composed",
                    content_hash=sha256_hex("composed"),
                    sources_payload=[{"channel": "@c", "message_id": 99}],
                    raw_post_ids=[rid],
                )
                await session.commit()
                did = int(d.id)

            async with factory() as session:
                rp = await session.get(RawPost, rid)
                assert rp is not None
                assert rp.processed_at is not None
                dr = await repo.get_draft_by_id(session, did)
                assert dr is not None
                assert dr.content == "composed"
        finally:
            await engine.dispose()

    asyncio.run(body())


def test_upsert_raw_post_backfills_media_extras(tmp_path):
    async def body() -> None:
        engine, factory = await _make_engine(_sqlite_url(tmp_path))
        try:
            now = repo.utcnow()
            media = {
                "media_type": "photo",
                "local_path": "/data/runtime/media_cache/-100_99.jpg",
                "message_id": 99,
                "chat_id": -100,
            }
            async with factory() as session:
                inserted = await repo.upsert_raw_post(
                    session,
                    channel_name="@c",
                    message_id=99,
                    text="raw",
                    created_at=now,
                    extras_json="{}",
                )
                assert inserted is True
                await session.commit()

            async with factory() as session:
                again = await repo.upsert_raw_post(
                    session,
                    channel_name="@c",
                    message_id=99,
                    text="raw",
                    created_at=now,
                    extras_json=json.dumps({"media": media}),
                )
                assert again is False
                await session.commit()

            async with factory() as session:
                row = (
                    await session.execute(
                        select(RawPost).where(RawPost.channel_name == "@c", RawPost.message_id == 99)
                    )
                ).scalar_one()
                extras = json.loads(row.extras or "{}")
                assert extras["media"]["local_path"] == media["local_path"]
        finally:
            await engine.dispose()

    asyncio.run(body())
