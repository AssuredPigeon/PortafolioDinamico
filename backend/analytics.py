from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

MESES_CORTOS = {
    1: "ene",
    2: "feb",
    3: "mar",
    4: "abr",
    5: "may",
    6: "jun",
    7: "jul",
    8: "ago",
    9: "sep",
    10: "oct",
    11: "nov",
    12: "dic",
}


def start_of_week_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def format_short_spanish_day(d: date) -> str:
    return f"{d.day:02d} {MESES_CORTOS[d.month]}"


def compute_activity_trend(
    actividad_commits: list[dict[str, Any]],
    repositorios: list[dict[str, Any]],
    reference_now: datetime | None = None,
    num_weeks: int = 9,
) -> dict[str, Any]:
    """
    Calcula los indicadores de la Pantalla 3 (Tendencia de actividad - RF7):
    - Serie semanal de commits en los últimos ~2 meses (9 semanas lunes-domingo)
    - Lenguaje principal reciente
    - Racha actual de días consecutivos con actividad (y mejor racha reciente)
    """
    now_utc = (reference_now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    today = now_utc.date()
    current_monday = start_of_week_monday(today)

    buckets: list[dict[str, Any]] = []
    bucket_map: dict[str, dict[str, Any]] = {}
    bucket_repos_map: dict[str, dict[str, int]] = {}
    for i in range(num_weeks - 1, -1, -1):
        wk_start = current_monday - timedelta(days=i * 7)
        key = wk_start.isoformat()
        bucket = {
            "semanaInicio": key,
            "etiqueta": format_short_spanish_day(wk_start),
            "commits": 0,
            "desglose": [],
        }
        buckets.append(bucket)
        bucket_map[key] = bucket
        bucket_repos_map[key] = {}

    min_date_iso = buckets[0]["semanaInicio"] if buckets else "1970-01-01"
    visible_repo_ids = {
        int(r["id_repositorio"])
        for r in repositorios
        if r.get("visible", True) is not False
    }
    repo_names = {
        int(r["id_repositorio"]): str(r.get("nombre") or r.get("nombre_completo") or f"Repo #{r['id_repositorio']}")
        for r in repositorios
    }

    commits_by_day: dict[date, int] = {}
    lang_totals: dict[str, int] = {}
    total_commits_period = 0

    for item in actividad_commits:
        repo_id = int(item.get("id_repositorio", 0))
        if visible_repo_ids and repo_id not in visible_repo_ids:
            continue

        cant = int(item.get("cantidad_commits") or 0)
        raw_fecha = str(item.get("fecha") or "")[:10]
        if cant <= 0 or not raw_fecha:
            continue

        try:
            d_obj = date.fromisoformat(raw_fecha)
        except ValueError:
            continue

        commits_by_day[d_obj] = commits_by_day.get(d_obj, 0) + cant

        wk_key = start_of_week_monday(d_obj).isoformat()
        if wk_key >= min_date_iso and wk_key in bucket_map:
            bucket_map[wk_key]["commits"] += cant
            r_name = repo_names.get(repo_id, f"Repo #{repo_id}")
            bucket_repos_map[wk_key][r_name] = bucket_repos_map[wk_key].get(r_name, 0) + cant
            total_commits_period += cant
            lang = (item.get("lenguaje_principal") or "").strip()
            if lang and lang not in ("N/A", "Sin detectar"):
                lang_totals[lang] = lang_totals.get(lang, 0) + cant

    for wk_key, bucket in bucket_map.items():
        per_repo = bucket_repos_map.get(wk_key, {})
        bucket["desglose"] = [
            {"nombre": name, "commits": count}
            for name, count in sorted(per_repo.items(), key=lambda kv: (-kv[1], kv[0].lower()))
        ]

    if lang_totals:
        top_language = max(lang_totals.items(), key=lambda kv: kv[1])[0]
    else:
        top_language = "Sin detectar"
        for repo in repositorios:
            if repo.get("visible", True) and repo.get("lenguajes"):
                top_language = repo["lenguajes"][0]
                break

    # Racha actual (cuenta desde hoy o desde ayer si hoy aún no hay commit)
    cursor: date | None = None
    if today in commits_by_day:
        cursor = today
    elif (today - timedelta(days=1)) in commits_by_day:
        cursor = today - timedelta(days=1)

    current_streak = 0
    while cursor is not None and cursor in commits_by_day:
        current_streak += 1
        cursor = cursor - timedelta(days=1)

    # Mejor racha dentro de la ventana de 2 meses
    min_date_obj = date.fromisoformat(min_date_iso)
    active_days_sorted = sorted(d for d in commits_by_day if d >= min_date_obj)
    best_recent_streak = 0
    running_streak = 0
    prev_day: date | None = None

    for d_item in active_days_sorted:
        if prev_day is not None and (d_item - prev_day).days == 1:
            running_streak += 1
        else:
            running_streak = 1
        best_recent_streak = max(best_recent_streak, running_streak)
        prev_day = d_item

    return {
        "semanas": buckets,
        "totalCommitsPeriodo": total_commits_period,
        "lenguajePrincipalReciente": top_language,
        "rachaActualDias": current_streak,
        "mejorRachaReciente": best_recent_streak,
        "diasActivosPeriodo": len(active_days_sorted),
    }

