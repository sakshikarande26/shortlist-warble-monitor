"""SQLAlchemy ORM models: creators, posts, samples (append-only), alerts
(idempotent per post), and the request log used to track API budget spend.
"""

import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, event
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Creator(Base):
    __tablename__ = "creators"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # wc_...
    handle: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    platform: Mapped[str] = mapped_column(String)
    followers: Mapped[int] = mapped_column(Integer)
    fetched_at_sim_hours: Mapped[float] = mapped_column(Float)
    fetched_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # wp_...
    creator_id: Mapped[str] = mapped_column(ForeignKey("creators.id"))
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[str | None] = mapped_column(String, nullable=True)
    platform: Mapped[str] = mapped_column(String)
    first_seen_sim_hours: Mapped[float] = mapped_column(Float)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        Enum("active", "gone", name="post_status"), default="active", server_default="active"
    )
    gone_sim_hours: Mapped[float | None] = mapped_column(Float, nullable=True)


class Sample(Base):
    """Append-only time series. No update/delete path exists in the DAO,
    and the event listeners below turn any accidental mutation into a hard
    error rather than a silently corrupted history.
    """

    __tablename__ = "samples"
    __table_args__ = (Index("ix_samples_post_id_sim_hours", "post_id", "sim_hours"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    post_id: Mapped[str] = mapped_column(ForeignKey("posts.id"), index=True)
    views: Mapped[int] = mapped_column(Integer)
    likes: Mapped[int] = mapped_column(Integer)
    comments: Mapped[int] = mapped_column(Integer)
    metrics_at: Mapped[str] = mapped_column(String)  # ISO timestamp string from the API
    sim_hours: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(Enum("cache", "live", name="sample_source"))
    captured_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))


@event.listens_for(Sample, "before_update")
def _block_sample_update(mapper, connection, target):
    raise RuntimeError("samples is append-only: updates are not allowed")


@event.listens_for(Sample, "before_delete")
def _block_sample_delete(mapper, connection, target):
    raise RuntimeError("samples is append-only: deletes are not allowed")


class Alert(Base):
    """post_id is the primary key (not an autoincrement id) so the schema
    itself enforces "idempotent per post" — there can only ever be one row.
    """

    __tablename__ = "alerts"

    post_id: Mapped[str] = mapped_column(ForeignKey("posts.id"), primary_key=True)
    decided_sim_hours: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted: Mapped[bool] = mapped_column(Boolean)
    received_sim_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    received_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)


class RequestLog(Base):
    __tablename__ = "request_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint: Mapped[str] = mapped_column(String)
    method: Mapped[str] = mapped_column(String)
    sim_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer)
    rate_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    called_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))
