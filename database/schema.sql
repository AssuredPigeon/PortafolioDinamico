-- =============================================================================
-- Esquema Relacional PostgreSQL: Portafolio Dinámico Auto-actualizable
-- Autor: Daniel Tornero Solano (Sewell) · UABC Tijuana
-- Compatible con PostgreSQL 14+, Supabase y Neon.
-- =============================================================================

CREATE TABLE IF NOT EXISTS usuario (
    id_usuario SERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    github_username VARCHAR(100) NOT NULL UNIQUE,
    correo VARCHAR(150) NOT NULL
);

CREATE TABLE IF NOT EXISTS repositorio (
    id_repositorio BIGINT PRIMARY KEY,
    id_usuario INTEGER NOT NULL REFERENCES usuario(id_usuario) ON DELETE CASCADE,
    nombre VARCHAR(150) NOT NULL,
    nombre_completo VARCHAR(255) NOT NULL UNIQUE,
    descripcion_original TEXT NOT NULL DEFAULT '',
    descripcion_generada TEXT,
    origen_descripcion VARCHAR(50) DEFAULT 'metadatos',
    puntaje_ia DOUBLE PRECISION DEFAULT 0.0,
    lenguajes JSONB NOT NULL DEFAULT '[]'::jsonb,
    topics JSONB NOT NULL DEFAULT '[]'::jsonb,
    detalle_tecnico JSONB NOT NULL DEFAULT '{}'::jsonb,
    visible BOOLEAN NOT NULL DEFAULT TRUE,
    url VARCHAR(500) NOT NULL,
    estrellas INTEGER NOT NULL DEFAULT 0,
    fecha_ultimo_commit TIMESTAMPTZ NOT NULL,
    es_fork BOOLEAN NOT NULL DEFAULT FALSE,
    readme_consultado BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_repositorio_usuario
    ON repositorio(id_usuario);

CREATE INDEX IF NOT EXISTS idx_repositorio_visible_fecha
    ON repositorio(visible, fecha_ultimo_commit DESC);

CREATE TABLE IF NOT EXISTS actividad_commit (
    id_actividad SERIAL PRIMARY KEY,
    id_repositorio BIGINT NOT NULL REFERENCES repositorio(id_repositorio) ON DELETE CASCADE,
    fecha DATE NOT NULL,
    cantidad_commits INTEGER NOT NULL CHECK (cantidad_commits >= 0),
    lenguaje_principal VARCHAR(80) NOT NULL DEFAULT 'Sin detectar',
    CONSTRAINT uq_actividad_repo_fecha UNIQUE (id_repositorio, fecha)
);

CREATE INDEX IF NOT EXISTS idx_actividad_fecha
    ON actividad_commit(fecha DESC);

