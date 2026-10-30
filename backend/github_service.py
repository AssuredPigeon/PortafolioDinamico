from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx


class GitHubRateLimitError(RuntimeError):
    """Se lanza cuando la API de GitHub responde 403/429 por límite de peticiones."""


class GitHubUserNotFoundError(RuntimeError):
    """Se lanza cuando la cuenta de GitHub solicitada no existe (HTTP 404)."""


class GitHubClient:
    """Cliente HTTP de solo lectura para la API REST de GitHub con manejo de rate limits y HTTP 202."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None, http_client: httpx.Client | None = None) -> None:
        self.token = (token or "").strip() or None
        self.rate_remaining: int | None = None
        self.rate_limit: int | None = None
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=20.0, follow_redirects=True)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        headers = {
            "Accept": accept,
            "User-Agent": "Portafolio-Dinamico-UABC-PyTorch",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _update_limits(self, response: httpx.Response) -> None:
        rem = response.headers.get("x-ratelimit-remaining")
        lim = response.headers.get("x-ratelimit-limit")
        if rem is not None and rem.isdigit():
            self.rate_remaining = int(rem)
        if lim is not None and lim.isdigit():
            self.rate_limit = int(lim)

    def _check_rate_limit(self, response: httpx.Response, context: str) -> None:
        self._update_limits(response)
        if response.status_code in (403, 429):
            reset_raw = response.headers.get("x-ratelimit-reset")
            reset_msg = ""
            if reset_raw and reset_raw.isdigit():
                dt = datetime.fromtimestamp(int(reset_raw), tz=timezone.utc).astimezone()
                reset_msg = f" Se reinicia a las {dt.strftime('%H:%M:%S')}."
            raise GitHubRateLimitError(
                f"Límite de peticiones de GitHub alcanzado en {context} "
                f"({self.rate_remaining}/{self.rate_limit}).{reset_msg}"
            )

    def fetch_user_profile(self, username: str) -> dict[str, Any]:
        """Obtiene el perfil público de un usuario u organización en GitHub."""
        url = f"{self.BASE_URL}/users/{username}"
        resp = self._client.get(url, headers=self._headers())
        self._check_rate_limit(resp, f"/users/{username}")
        if resp.status_code == 404:
            raise GitHubUserNotFoundError(f"No existe el usuario u organización '{username}' en GitHub.")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}

    def fetch_user_repos(self, username: str) -> list[dict[str, Any]]:
        url = f"{self.BASE_URL}/users/{username}/repos"
        resp = self._client.get(
            url,
            params={"per_page": 100, "sort": "pushed"},
            headers=self._headers(),
        )
        self._check_rate_limit(resp, f"/users/{username}/repos")
        if resp.status_code == 404:
            raise GitHubUserNotFoundError(f"No existe el usuario u organización '{username}' en GitHub.")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []

    def fetch_single_repo(self, full_name: str) -> dict[str, Any] | None:
        url = f"{self.BASE_URL}/repos/{full_name}"
        resp = self._client.get(url, headers=self._headers())
        self._check_rate_limit(resp, f"/repos/{full_name}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def fetch_repo_language_bytes(self, full_name: str) -> dict[str, int]:
        url = f"{self.BASE_URL}/repos/{full_name}/languages"
        resp = self._client.get(url, headers=self._headers())
        self._check_rate_limit(resp, f"/repos/{full_name}/languages")
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            return {}
        ordered = sorted(data.items(), key=lambda kv: int(kv[1]), reverse=True)
        return {str(lang): int(b) for lang, b in ordered if int(b) > 0}

    def fetch_repo_languages(self, full_name: str) -> list[str]:
        return list(self.fetch_repo_language_bytes(full_name).keys())

    def fetch_repo_readme(self, full_name: str) -> str | None:
        url = f"{self.BASE_URL}/repos/{full_name}/readme"
        resp = self._client.get(
            url,
            headers=self._headers(accept="application/vnd.github.raw+json"),
        )
        self._check_rate_limit(resp, f"/repos/{full_name}/readme")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        raw_bytes = resp.content
        if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
            return raw_bytes.decode("utf-16", errors="ignore")
        return resp.text.replace("\x00", "")

    def fetch_repo_tree(self, full_name: str, branch: str = "main") -> list[dict[str, Any]]:
        """Obtiene el árbol recursivo de archivos del repositorio (maneja repos vacíos con 404/409)."""
        url = f"{self.BASE_URL}/repos/{full_name}/git/trees/{branch}"
        resp = self._client.get(
            url,
            params={"recursive": "1"},
            headers=self._headers(),
        )
        self._check_rate_limit(resp, f"/repos/{full_name}/git/trees/{branch}")
        if resp.status_code in (404, 409, 422):
            return []
        resp.raise_for_status()
        data = resp.json()
        tree = data.get("tree") if isinstance(data, dict) else []
        return tree if isinstance(tree, list) else []

    def fetch_repo_file_text(self, full_name: str, file_path: str, max_chars: int = 24000) -> str | None:
        """Descarga en modo solo lectura el contenido de texto de un archivo puntual del repositorio."""
        clean_path = file_path.lstrip("/")
        url = f"{self.BASE_URL}/repos/{full_name}/contents/{clean_path}"
        resp = self._client.get(
            url,
            headers=self._headers(accept="application/vnd.github.raw+json"),
        )
        self._check_rate_limit(resp, f"/repos/{full_name}/contents/{clean_path}")
        if resp.status_code in (403, 404, 422):
            return None
        resp.raise_for_status()
        raw_bytes = resp.content
        if b"\x00" in raw_bytes[:512]:
            # En caso de UTF-16 con BOM (como algunos READMEs generados en Windows PowerShell)
            for enc in ("utf-16", "utf-16-le", "utf-8"):
                try:
                    decoded = raw_bytes.decode(enc)
                    if "\x00" not in decoded:
                        return decoded[:max_chars]
                except Exception:
                    continue
            return None
        return resp.text[:max_chars]

    def fetch_repo_contributors_count(self, full_name: str) -> int:
        """Cuenta colaboradores humanos del repositorio ignorando cuentas bot."""
        url = f"{self.BASE_URL}/repos/{full_name}/contributors"
        resp = self._client.get(
            url,
            params={"per_page": 30},
            headers=self._headers(),
        )
        self._check_rate_limit(resp, f"/repos/{full_name}/contributors")
        if resp.status_code in (204, 404, 409):
            return 1
        resp.raise_for_status()
        items = resp.json()
        if not isinstance(items, list):
            return 1
        humans = [
            c for c in items
            if isinstance(c, dict)
            and "[bot]" not in str(c.get("login") or "").lower()
            and "dependabot" not in str(c.get("login") or "").lower()
        ]
        return max(1, len(humans))

    def fetch_recent_commit_messages(self, full_name: str, limit: int = 12) -> list[str]:
        """Obtiene los encabezados de los commits humanos más recientes del repositorio."""
        url = f"{self.BASE_URL}/repos/{full_name}/commits"
        resp = self._client.get(
            url,
            params={"per_page": limit},
            headers=self._headers(),
        )
        self._check_rate_limit(resp, f"/repos/{full_name}/commits")
        if resp.status_code in (404, 409):
            return []
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            return []
        messages: list[str] = []
        for item in data:
            login = str((item.get("author") or {}).get("login") or "").lower()
            if "[bot]" in login or "dependabot" in login:
                continue
            msg = str((item.get("commit") or {}).get("message") or "").strip()
            if msg:
                first_line = " ".join(msg.splitlines()).strip()
                messages.append(first_line)
        return messages

    def fetch_stats_commit_activity(
        self,
        full_name: str,
        max_retries: int = 2,
        retry_delay_sec: float = 1.2,
    ) -> tuple[list[dict[str, Any]] | None, int]:
        """
        Consulta /stats/commit_activity manejando respuestas HTTP 202 (GitHub calculando estadísticas)
        mediante reintentos controlados (Sección 9 y Regla 7).
        """
        url = f"{self.BASE_URL}/repos/{full_name}/stats/commit_activity"
        for attempt in range(max_retries + 1):
            resp = self._client.get(url, headers=self._headers())
            self._check_rate_limit(resp, f"/repos/{full_name}/stats/commit_activity")

            if resp.status_code == 202:
                if attempt < max_retries:
                    time.sleep(retry_delay_sec)
                    continue
                return None, 202

            if resp.status_code in (204, 404, 409):
                return [], resp.status_code

            resp.raise_for_status()
            data = resp.json()
            return (data if isinstance(data, list) else []), 200

        return None, 202

    def fetch_commits_since(self, full_name: str, since_iso: str) -> dict[str, int]:
        """
        Respaldo directo con /commits?since=... cuando /stats/commit_activity devuelve 202 persistente
        o aún no refleja commits recientes. Agrupa conteo de commits por fecha YYYY-MM-DD (UTC).
        """
        url = f"{self.BASE_URL}/repos/{full_name}/commits"
        resp = self._client.get(
            url,
            params={"since": since_iso, "per_page": 100},
            headers=self._headers(),
        )
        self._check_rate_limit(resp, f"/repos/{full_name}/commits")
        if resp.status_code in (404, 409):
            return {}
        resp.raise_for_status()

        commits = resp.json()
        counts: dict[str, int] = {}
        if isinstance(commits, list):
            for item in commits:
                author_login = (item.get("author") or {}).get("login") or ""
                if "[bot]" in author_login.lower() or "dependabot" in author_login.lower():
                    continue
                raw_date = (
                    item.get("commit", {}).get("author", {}).get("date")
                    or item.get("commit", {}).get("committer", {}).get("date")
                )
                if not raw_date:
                    continue
                day_str = raw_date[:10]
                counts[day_str] = counts.get(day_str, 0) + 1
        return counts

    def fetch_user_push_events(self, username: str, cutoff_date_iso: str) -> dict[str, dict[str, int]]:
        """
        Obtiene los eventos públicos PushEvent del usuario para capturar también commits realizados
        en ramas de trabajo colaborativas (feature branches) que /stats/commit_activity no incluye
        por evaluar únicamente la rama principal (default_branch).
        Devuelve { repo_full_name_lower: { 'YYYY-MM-DD': cantidad_commits } }.
        """
        url = f"{self.BASE_URL}/users/{username}/events/public"
        resp = self._client.get(
            url,
            params={"per_page": 100},
            headers=self._headers(),
        )
        self._check_rate_limit(resp, f"/users/{username}/events/public")
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()

        events = resp.json()
        by_repo: dict[str, dict[str, int]] = {}
        if not isinstance(events, list):
            return by_repo

        for ev in events:
            if ev.get("type") != "PushEvent":
                continue
            repo_name = str((ev.get("repo") or {}).get("name") or "").lower()
            created_at = str(ev.get("created_at") or "")[:10]
            if not repo_name or not created_at or created_at < cutoff_date_iso:
                continue

            payload = ev.get("payload") or {}
            # En GitHub Events API v3, size o distinct_size indica cuántos commits trajo el push
            n_commits = int(payload.get("distinct_size") or payload.get("size") or len(payload.get("commits") or []) or 1)
            if n_commits <= 0:
                continue

            repo_days = by_repo.setdefault(repo_name, {})
            repo_days[created_at] = repo_days.get(created_at, 0) + n_commits

        return by_repo

    def fetch_repo_push_events(self, full_name: str, cutoff_date_iso: str) -> dict[str, int]:
        """
        Obtiene PushEvents públicos del repositorio (excluyendo bots como dependabot)
        para reflejar commits realizados en ramas secundarias de trabajo en equipo.
        """
        url = f"{self.BASE_URL}/repos/{full_name}/events"
        resp = self._client.get(
            url,
            params={"per_page": 50},
            headers=self._headers(),
        )
        self._check_rate_limit(resp, f"/repos/{full_name}/events")
        if resp.status_code in (404, 409):
            return {}
        resp.raise_for_status()

        events = resp.json()
        counts: dict[str, int] = {}
        if not isinstance(events, list):
            return counts

        for ev in events:
            if ev.get("type") != "PushEvent":
                continue
            actor_login = str((ev.get("actor") or {}).get("login") or "").lower()
            if "[bot]" in actor_login or "dependabot" in actor_login or actor_login.endswith("-bot"):
                continue
            day_str = str(ev.get("created_at") or "")[:10]
            if not day_str or day_str < cutoff_date_iso:
                continue
            payload = ev.get("payload") or {}
            n_commits = int(payload.get("distinct_size") or payload.get("size") or len(payload.get("commits") or []) or 1)
            if n_commits > 0:
                counts[day_str] = counts.get(day_str, 0) + n_commits
        return counts

    def fetch_daily_commits_window(
        self,
        full_name: str,
        cutoff_date_iso: str,
        since_iso: str,
        max_retries_202: int = 1,
        retry_delay_sec: float = 0.35,
    ) -> dict[str, int]:
        weeks, status = self.fetch_stats_commit_activity(
            full_name,
            max_retries=max_retries_202,
            retry_delay_sec=retry_delay_sec,
        )
        daily_counts: dict[str, int] = {}

        if weeks:
            for w in weeks:
                if not isinstance(w, dict) or not w.get("total"):
                    continue
                week_ts = int(w.get("week", 0))
                days = w.get("days") or []
                for idx, count in enumerate(days):
                    c_int = int(count or 0)
                    if c_int <= 0:
                        continue
                    day_dt = datetime.fromtimestamp(week_ts + idx * 86400, tz=timezone.utc)
                    day_iso = day_dt.strftime("%Y-%m-%d")
                    if day_iso >= cutoff_date_iso:
                        daily_counts[day_iso] = daily_counts.get(day_iso, 0) + c_int

        if status == 202 or not daily_counts:
            fallback = self.fetch_commits_since(full_name, since_iso)
            if fallback:
                daily_counts = {k: v for k, v in fallback.items() if k >= cutoff_date_iso and v > 0}

        # Integrar PushEvents de ramas secundarias (ignorando bots) sin duplicar días ya contados
        repo_events = self.fetch_repo_push_events(full_name, cutoff_date_iso)
        for day_iso, ev_count in repo_events.items():
            daily_counts[day_iso] = max(daily_counts.get(day_iso, 0), ev_count)

        return daily_counts

