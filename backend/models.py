from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JsonListType = JSON().with_variant(JSONB(), "postgresql")
JsonDictType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


class Usuario(Base):
    __tablename__ = "usuario"

    id_usuario: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    github_username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    correo: Mapped[str] = mapped_column(String(150), nullable=False)

    repositorios: Mapped[list["Repositorio"]] = relationship(
        back_populates="usuario",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id_usuario": self.id_usuario,
            "nombre": self.nombre,
            "github_username": self.github_username,
            "correo": self.correo,
        }


class Repositorio(Base):
    __tablename__ = "repositorio"

    id_repositorio: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    id_usuario: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("usuario.id_usuario", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    descripcion_original: Mapped[str] = mapped_column(Text, nullable=False, default="")
    descripcion_generada: Mapped[str | None] = mapped_column(Text, nullable=True)
    origen_descripcion: Mapped[str] = mapped_column(String(50), nullable=False, default="metadatos")
    puntaje_ia: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    lenguajes: Mapped[list[str]] = mapped_column(JsonListType, nullable=False, default=list)
    topics: Mapped[list[str]] = mapped_column(JsonListType, nullable=False, default=list)
    detalle_tecnico: Mapped[dict[str, Any]] = mapped_column(JsonDictType, nullable=False, default=dict)
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    estrellas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fecha_ultimo_commit: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    es_fork: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    readme_consultado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    usuario: Mapped["Usuario"] = relationship(back_populates="repositorios")
    actividades: Mapped[list["ActividadCommit"]] = relationship(
        back_populates="repositorio",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict[str, Any]:
        dt = self.fecha_ultimo_commit
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        iso_commit = dt.isoformat().replace("+00:00", "Z")
        return {
            "id_repositorio": self.id_repositorio,
            "id_usuario": self.id_usuario,
            "nombre": self.nombre,
            "nombre_completo": self.nombre_completo,
            "descripcion_original": self.descripcion_original or "",
            "descripcion_generada": self.descripcion_generada,
            "origen_descripcion": self.origen_descripcion or "metadatos",
            "puntaje_ia": round(float(self.puntaje_ia or 0.0), 4),
            "lenguajes": list(self.lenguajes or []),
            "topics": list(self.topics or []),
            "detalle_tecnico": dict(self.detalle_tecnico or {}),
            "visible": bool(self.visible),
            "url": self.url,
            "estrellas": int(self.estrellas or 0),
            "fecha_ultimo_commit": iso_commit,
            "es_fork": bool(self.es_fork),
            "readme_consultado": bool(self.readme_consultado),
        }


class ActividadCommit(Base):
    __tablename__ = "actividad_commit"
    __table_args__ = (
        UniqueConstraint("id_repositorio", "fecha", name="uq_actividad_repo_fecha"),
    )

    id_actividad: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_repositorio: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("repositorio.id_repositorio", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    cantidad_commits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lenguaje_principal: Mapped[str] = mapped_column(String(80), nullable=False, default="Sin detectar")

    repositorio: Mapped["Repositorio"] = relationship(back_populates="actividades")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id_actividad": self.id_actividad,
            "id_repositorio": self.id_repositorio,
            "fecha": self.fecha.isoformat(),
            "cantidad_commits": int(self.cantidad_commits),
            "lenguaje_principal": self.lenguaje_principal,
        }

