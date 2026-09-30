"""지역·시설·환경 데이터를 DB 우선으로 모아 추천 결과를 만든다."""
from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import os
from pathlib import Path

from django.conf import settings
from django.db import connection

from . import collector


def _parts(region: str) -> tuple[str, str]:
    parts = [part for part in (region or "").split() if part]
    return (parts[0], parts[-1]) if len(parts) >= 2 else ("", "")


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _table_exists(schema: str, table: str) -> bool:
    """현재 연결된 PostgreSQL에 선택한 테이블이 있는지 확인한다."""
    rows = _rows("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"{schema}.{table}",))
    return bool(rows and rows[0].get("exists"))


def _first_existing_table(*candidates: tuple[str, str]) -> str | None:
    for schema, table in candidates:
        if _table_exists(schema, table):
            return f'"{schema}"."{table}"'
    return None


def _load_env() -> None:
    env_path = Path(settings.BASE_DIR) / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


def _facility_row(row: dict, source: str) -> dict:
    operation_notice = ""
    homepage = ""
    try:
        enriched = json.loads(row.get("enriched_fields") or "{}")
        evidence = enriched.get("web_evidence") or {}
        operation_notice = " / ".join(evidence.get("evidence") or [])[:300]
        homepage = evidence.get("url", "")
    except (TypeError, ValueError, AttributeError):
        operation_notice = ""
    return {
        "facility_name": row.get("faci_nm") or "시설명 미등록",
        "facility_type": row.get("ftype_nm") or row.get("fcob_nm") or "운동 시설",
        "address": row.get("faci_road_addr") or row.get("faci_addr") or "",
        "city": row.get("cp_nm") or "",
        "district": row.get("cpb_nm") or "",
        "latitude": row.get("faci_lat") or "",
        "longitude": row.get("faci_lot") or "",
        "homepage": homepage,
        "hours": "",
        "source": source,
        "db_distance_km": row.get("db_distance_km"),
        "operation_notice": operation_notice,
    }


def facilities_for_region(
    sido: str,
    district: str,
    limit: int = 1000,
    origin: tuple[float, float] | None = None,
    nearby_only: bool = False,
) -> list[dict]:
    """시설 DB에서 시도와 시군구가 모두 일치하는 행만 반환한다."""
    # 팀 Supabase의 m3_processed를 우선 사용하고, 기존 로컬 DB도 호환한다.
    facility_table = _first_existing_table(
        ("m3_processed", "facility"),
        ("processed", "facility"),
        ("public", "facility_processed"),
    )
    if facility_table:
        if origin and nearby_only:
            processed_rows = _rows(
                f"""
                SELECT faci_nm, ftype_nm, fcob_nm, cp_nm, cpb_nm, faci_road_addr,
                       faci_addr, faci_lat, faci_lot, NULL::text AS enriched_fields,
                       ST_Distance(
                         ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                         ST_SetSRID(ST_MakePoint(faci_lot, faci_lat), 4326)::geography
                       ) / 1000.0 AS db_distance_km
                FROM {facility_table}
                WHERE faci_lat BETWEEN -90 AND 90
                  AND faci_lot BETWEEN -180 AND 180
                ORDER BY db_distance_km, faci_nm
                LIMIT %s
                """,
                (origin[1], origin[0], max(limit, 2000)),
            )
        elif origin:
            processed_rows = _rows(
                f"""
                SELECT faci_nm, ftype_nm, fcob_nm, cp_nm, cpb_nm, faci_road_addr,
                       faci_addr, faci_lat, faci_lot, NULL::text AS enriched_fields,
                       ST_Distance(
                         ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                         ST_SetSRID(ST_MakePoint(faci_lot, faci_lat), 4326)::geography
                       ) / 1000.0 AS db_distance_km
                FROM {facility_table}
                WHERE trim(cp_nm) = trim(%s)
                  AND trim(cpb_nm) = trim(%s)
                  AND faci_lat BETWEEN -90 AND 90
                  AND faci_lot BETWEEN -180 AND 180
                ORDER BY db_distance_km NULLS LAST, faci_nm
                LIMIT %s
                """,
                (origin[1], origin[0], sido, district, limit),
            )
        else:
            processed_rows = _rows(
                f"""
                SELECT faci_nm, ftype_nm, fcob_nm, cp_nm, cpb_nm, faci_road_addr,
                       faci_addr, faci_lat, faci_lot, NULL::text AS enriched_fields
                FROM {facility_table}
                WHERE trim(cp_nm) = trim(%s)
                  AND trim(cpb_nm) = trim(%s)
                ORDER BY faci_nm
                LIMIT %s
                """,
                (sido, district, limit),
            )
        if processed_rows:
            return [_facility_row(row, f"DB:{facility_table.replace(chr(34), '')}") for row in processed_rows]

    if origin and nearby_only:
        # 실제 GPS 위치를 받은 경우에는 로그인 지역에 한정하지 않고
        # 전국 시설 중 현재 위치에 가까운 시설을 먼저 검색한다.
        rows = _rows(
            """
            SELECT faci_nm, ftype_nm, fcob_nm, cp_nm, cpb_nm, faci_road_addr,
                   faci_addr, faci_lat, faci_lot, enriched_fields,
                   ST_Distance(
                     ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                     ST_SetSRID(ST_MakePoint(faci_lot::double precision, faci_lat::double precision), 4326)::geography
                   ) / 1000.0 AS db_distance_km
            FROM facility_processed
            WHERE trim(faci_lat) ~ '^-?[0-9]+(\\.[0-9]+)?$'
              AND trim(faci_lot) ~ '^-?[0-9]+(\\.[0-9]+)?$'
            ORDER BY db_distance_km, faci_nm
            LIMIT %s
            """,
            (origin[1], origin[0], max(limit, 2000)),
        )
    elif origin:
        # PostGIS Point는 (경도, 위도) 순서이며, 원점은 (위도, 경도)로 받는다.
        # text 좌표 중 숫자 형식인 행만 안전하게 숫자로 변환한다.
        rows = _rows(
            """
            SELECT faci_nm, ftype_nm, fcob_nm, cp_nm, cpb_nm, faci_road_addr,
                   faci_addr, faci_lat, faci_lot, enriched_fields,
                   CASE
                     WHEN trim(faci_lat) ~ '^-?[0-9]+(\\.[0-9]+)?$'
                      AND trim(faci_lot) ~ '^-?[0-9]+(\\.[0-9]+)?$'
                     THEN ST_Distance(
                       ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                       ST_SetSRID(ST_MakePoint(faci_lot::double precision, faci_lat::double precision), 4326)::geography
                     ) / 1000.0
                     ELSE NULL
                   END AS db_distance_km
            FROM facility_processed
            WHERE trim(cp_nm) = trim(%s)
              AND trim(cpb_nm) = trim(%s)
            ORDER BY db_distance_km NULLS LAST, faci_nm
            LIMIT %s
            """,
            (origin[1], origin[0], sido, district, limit),
        )
    else:
        rows = _rows(
            """
            SELECT faci_nm, ftype_nm, fcob_nm, cp_nm, cpb_nm, faci_road_addr,
                   faci_addr, faci_lat, faci_lot, enriched_fields
            FROM facility_processed
            WHERE trim(cp_nm) = trim(%s)
              AND trim(cpb_nm) = trim(%s)
            ORDER BY faci_nm
            LIMIT %s
            """,
            (sido, district, limit),
        )
    if rows:
        return [_facility_row(row, "DB:facility_processed") for row in rows]

    backup = Path(settings.BASE_DIR) / "frontend" / "db_backup" / "facility_processed.csv"
    if not backup.exists():
        return []
    result = []
    with backup.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            if row.get("cp_nm", "").strip() != sido or row.get("cpb_nm", "").strip() != district:
                continue
            result.append(_facility_row(row, "DB_BACKUP:facility_processed.csv"))
            if len(result) >= limit:
                break
    return result


def environment_for_region(sido: str, district: str) -> dict:
    """날씨·습도·대기질을 DB 우선, 인접/외부 데이터 순서로 보완한다."""
    _load_env()
    nx = int(os.getenv("KMA_NX", "60"))
    ny = int(os.getenv("KMA_NY", "127"))
    weather_table = _first_existing_table(
        ("m3_processed", "weather_ultra_ncst"),
        ("processed", "weather_ultra_ncst"),
        ("public", "weather_ultra_ncst"),
    ) or '"public"."weather_ultra_ncst"'
    weather_rows = _rows(
        f"""
        SELECT DISTINCT ON (category) category, "obsrValue", nx, ny, collected_at
        FROM {weather_table}
        WHERE nx = %s AND ny = %s
        ORDER BY category, collected_at DESC
        """,
        (nx, ny),
    )
    weather = {row["category"]: row["obsrValue"] for row in weather_rows}
    weather_source = f"DB:{weather_table}" if weather else ""
    if not weather:
        try:
            raw = collector.fetch_weather(nx, ny)
            weather = {row.get("category"): row.get("obsrValue") for row in collector.items_from_response(raw.get("ultra_srt_ncst", {}))}
            weather_source = "API:기상청"
        except Exception:
            weather = {}

    sido_short = sido.replace("특별자치도", "").replace("특별시", "").replace("광역시", "").replace("자치시", "").strip()
    sido_alias = {"경기도": "경기", "서울특별시": "서울", "인천광역시": "인천", "부산광역시": "부산", "대전광역시": "대전", "대구광역시": "대구", "광주광역시": "광주", "울산광역시": "울산"}
    sido_short = sido_alias.get(sido, sido_short)
    district_token = district.replace("시", "").replace("군", "").replace("구", "")
    air_table = (
        _first_existing_table(
            ("m3_processed", "air_quality"),
            ("processed", "air_quality"),
            ("public", "air_quality_processed"),
        )
        or '"public"."air_quality_processed"'
    )
    air_rows = _rows(
        f"""
        SELECT "sidoName", "stationName", "pm10Value", "pm25Value", "o3Value",
               "khaiValue", "dataTime", collected_at
        FROM {air_table}
        WHERE ("sidoName" = %s OR "sidoName" ILIKE %s)
          AND ("stationName" ILIKE %s OR "stationName" ILIKE %s)
        ORDER BY collected_at DESC, "dataTime" DESC
        LIMIT 1
        """,
        (sido_short, f"%{sido_short}%", f"%{district_token}%", f"%{district}%"),
    )
    if not air_rows:
        air_rows = _rows(
            f"""
            SELECT "sidoName", "stationName", "pm10Value", "pm25Value", "o3Value",
                   "khaiValue", "dataTime", collected_at
            FROM {air_table}
            WHERE "sidoName" = %s OR "sidoName" ILIKE %s
            ORDER BY collected_at DESC, "dataTime" DESC
            LIMIT 1
            """,
            (sido_short, f"%{sido_short}%"),
        )
    air = air_rows[0] if air_rows else {}
    air_source = f"DB:{air_table}" if air else ""
    if not air:
        try:
            raw = collector.fetch_air_nearby(sido, district)
            items = collector.items_from_response(raw.get("measurements", {}))
            air = items[0] if items else {}
            air_source = "API:에어코리아" if air else ""
        except Exception:
            air = {}

    return {"weather": weather, "weather_source": weather_source, "air": air, "air_source": air_source}


def _is_outdoor(item: dict) -> bool:
    text = f"{item.get('facility_name', '')} {item.get('facility_type', '')}".lower()
    return any(word in text for word in ("공원", "운동장", "야구장", "축구장", "풋살", "테니스장", "골프장", "야외", "실외"))


def _sport_for(item: dict) -> str:
    text = f"{item.get('facility_name', '')} {item.get('facility_type', '')}".lower()
    if any(word in text for word in ("공원", "운동장", "야구장", "축구장", "풋살", "테니스장", "골프장", "야외", "둘레길")):
        return "running"
    if any(word in text for word in ("수영", "수영장")):
        return "swimming"
    if any(word in text for word in ("배드민턴", "탁구", "테니스")):
        return "badminton"
    if any(word in text for word in ("자전거", "사이클")):
        return "cycling"
    if any(word in text for word in ("크로스핏", "기능성", "하이록스")):
        return "crossfit"
    if any(word in text for word in ("헬스", "헬스장", "체력단련", "피트니스", "휘트니스", "fitness", "스포츠센터", "스포츠 센터", "체육센터", "체육관", "종합체육시설", "근력", "웨이트")):
        return "fitness"
    if any(word in text for word in ("러닝", "육상")):
        return "running"
    return "unknown"


def _region_coordinate(region: str) -> tuple[float, float] | None:
    _load_env()
    key = os.getenv("KAKAO_REST_API_KEY", "").strip()
    if not key:
        return None
    try:
        response = collector.requests.get(
            "https://dapi.kakao.com/v2/local/search/address.json",
            headers={"Authorization": f"KakaoAK {key}"},
            params={"query": region, "size": 1}, timeout=8,
        )
        response.raise_for_status()
        row = (response.json().get("documents") or [None])[0]
        return (float(row["y"]), float(row["x"])) if row else None
    except (KeyError, TypeError, ValueError, collector.requests.RequestException):
        return None


def _region_for_coordinate(origin: tuple[float, float]) -> tuple[str, str] | None:
    """현재 위치 좌표를 카카오 행정구역명으로 바꿔 환경 DB 검색에 사용한다."""
    _load_env()
    key = os.getenv("KAKAO_REST_API_KEY", "").strip()
    if not key:
        return None
    try:
        response = collector.requests.get(
            "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json",
            headers={"Authorization": f"KakaoAK {key}"},
            params={"x": origin[1], "y": origin[0]}, timeout=5,
        )
        response.raise_for_status()
        documents = response.json().get("documents") or []
        row = next((item for item in documents if item.get("region_type") == "H"), documents[0] if documents else None)
        if not row:
            return None
        return row.get("region_1depth_name", ""), row.get("region_2depth_name", "")
    except (KeyError, TypeError, ValueError, collector.requests.RequestException):
        return None


def _distance_km(origin: tuple[float, float], item: dict) -> float | None:
    try:
        lat, lng = float(item["latitude"]), float(item["longitude"])
        p1, p2 = math.radians(origin[0]), math.radians(lat)
        dp, dl = math.radians(lat - origin[0]), math.radians(lng - origin[1])
        value = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 6371 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))
    except (KeyError, TypeError, ValueError):
        return None


def _number(value: object) -> float | None:
    try:
        if value in (None, "", "강수없음"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _kakao_fallback_facilities(
    origin: tuple[float, float] | None,
    region: str,
    selected_sports: set[str],
) -> list[dict]:
    """DB에 맞는 결과가 없을 때 카카오 장소 검색 결과를 일회성 후보로 사용한다.

    외부 결과는 DB에 저장하지 않고 현재 요청의 응답에만 포함한다.
    """
    _load_env()
    key = os.getenv("KAKAO_REST_API_KEY", "").strip()
    if not key:
        return []
    if origin is None:
        origin = _region_coordinate(region)
    if origin is None:
        return []

    keyword_map = {
        "fitness": ["헬스장", "피트니스", "체력단련장", "스포츠센터"],
        "running": ["공원", "운동장", "산책로", "육상경기장"],
        "cycling": ["자전거", "자전거대여소", "체육공원", "공원"],
        "crossfit": ["크로스핏", "기능성 트레이닝", "체육관"],
        "swimming": ["수영장", "체육센터"],
        "badminton": ["배드민턴장", "체육관", "체육센터"],
    }
    keywords = []
    for sport in selected_sports:
        keywords.extend(keyword_map.get(sport, []))
    if not keywords:
        keywords = ["체육시설"]

    # 수동 지역 검색은 지역 중심점에서 시설이 멀리 분포할 수 있어
    # DB에 결과가 없을 때만 5km까지 외부 후보를 보완한다.
    radius = 5000
    result = []
    seen = set()
    for keyword in keywords[:4]:
        try:
            response = collector.requests.get(
                "https://dapi.kakao.com/v2/local/search/keyword.json",
                headers={"Authorization": f"KakaoAK {key}"},
                params={
                    "query": keyword,
                    "x": origin[1],
                    "y": origin[0],
                    "radius": radius,
                    "size": 15,
                    "sort": "distance",
                },
                timeout=4,
            )
            response.raise_for_status()
            documents = response.json().get("documents") or []
        except (ValueError, collector.requests.RequestException):
            continue
        for item in documents:
            place_name = str(item.get("place_name") or "")
            category_name = str(item.get("category_name") or "")
            # 장소 검색에는 주차장·식당 등 주변 부대시설도 섞일 수 있어
            # 운동 추천과 직접 관계없는 명칭은 후보에서 제외한다.
            if any(word in f"{place_name} {category_name}" for word in ("주차장", "주차", "식당", "카페", "모텔", "호텔", "화장실", "놀이터", "반려견")):
                continue
            place_id = item.get("id") or f"{item.get('place_name')}:{item.get('x')}:{item.get('y')}"
            if place_id in seen:
                continue
            try:
                latitude = float(item["y"])
                longitude = float(item["x"])
            except (KeyError, TypeError, ValueError):
                continue
            seen.add(place_id)
            result.append({
                "facility_name": item.get("place_name") or "시설명 미등록",
                "facility_type": item.get("category_name") or keyword,
                "address": item.get("road_address_name") or item.get("address_name") or "",
                "city": item.get("address_name", "").split()[0] if item.get("address_name") else "",
                "district": item.get("address_name", "").split()[1] if len(item.get("address_name", "").split()) > 1 else "",
                "latitude": latitude,
                "longitude": longitude,
                "homepage": item.get("place_url") or "",
                "hours": "",
                "source": "Kakao Local fallback",
                "fallback_sport": next(iter(selected_sports), "fitness"),
                "db_distance_km": _distance_km(origin, {"latitude": latitude, "longitude": longitude}),
            })
    return result


def _live_operation_evidence(item: dict) -> dict:
    """추천 시점에 공개 운영정보를 다시 확인한다. 결과는 DB에 저장하지 않는다."""
    _load_env()
    url = str(item.get("homepage") or "").strip()
    if not url:
        key = os.getenv("KAKAO_REST_API_KEY", "").strip()
        name = str(item.get("facility_name") or "").strip()
        address = str(item.get("address") or "").strip()
        if key and name:
            try:
                response = collector.requests.get(
                    "https://dapi.kakao.com/v2/local/search/keyword.json",
                    headers={"Authorization": f"KakaoAK {key}"},
                    params={"query": f"{name} {address}".strip(), "size": 1},
                    timeout=3,
                )
                response.raise_for_status()
                documents = response.json().get("documents") or []
                url = documents[0].get("place_url", "") if documents else ""
            except (ValueError, TypeError, collector.requests.RequestException):
                url = ""
    if not url:
        return {"status": "no_public_page", "evidence": []}
    try:
        return collector.web_evidence(url)
    except Exception as exc:
        return {"status": "crawl_failed", "url": url, "error": str(exc), "evidence": []}


def _attach_live_operation_evidence(rows: list[dict], limit: int = 10) -> None:
    """화면에 노출될 후보를 병렬 확인해 최신 휴무·운영 문구를 붙인다."""
    targets = rows[:limit]
    if not targets:
        return
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(_live_operation_evidence, row): row for row in targets}
        for future in as_completed(futures):
            row = futures[future]
            try:
                evidence = future.result()
            except Exception:
                evidence = {"status": "crawl_failed", "evidence": []}
            hits = [str(hit).strip() for hit in evidence.get("evidence") or [] if str(hit).strip()]
            row["operation_checked_at"] = "live"
            row["operation_status"] = evidence.get("status", "")
            if hits:
                row["operation_notice"] = " / ".join(hits)[:300]
                row["reasons"].append("추천 시점 운영·휴무 공지 확인")
                row["score"] = max(0, row["score"] - (25 if any(word in row["operation_notice"] for word in ("오늘 휴무", "금일 휴무", "오늘 휴관", "임시 휴관")) else 0))
            if "score_breakdown" in row:
                row["score_breakdown"]["operation"] = row["score"] - row["score_breakdown"].get("before_operation", row["score"])
                row["score_breakdown"]["final"] = row["score"]
                row["score_breakdown"].pop("before_operation", None)


def _safety_data_unavailable() -> dict:
    """현재 연결된 DB에 AED·안전점검 원천 테이블이 없음을 명시한다."""
    return {
        "aed": {
            "status": "unavailable",
            "label": "확인 가능한 AED 데이터 없음",
        },
        "inspection": {
            "status": "unavailable",
            "label": "확인 가능한 안전점검 데이터 없음",
        },
    }


def _normalise_text(value: object) -> str:
    return "".join(str(value or "").lower().split())


def _attach_safety_data(rows: list[dict], district: str) -> None:
    """추천 후보에 Supabase m3_processed의 AED·안전점검 정보를 연결한다."""
    if not rows:
        return
    aed_table = _first_existing_table(
        ("m3_processed", "aed"),
        ("processed", "aed"),
    )
    inspection_table = _first_existing_table(
        ("m3_processed", "culture_sports_facility_safety_inspections"),
        ("processed", "culture_sports_facility_safety_inspections"),
    )
    aed_rows = []
    if aed_table:
        aed_rows = _rows(
            f'''
            SELECT "buildPlace" AS name, "buildAddress" AS address,
                   "gugun" AS district, "wgs84Lat" AS latitude, "wgs84Lon" AS longitude
            FROM {aed_table}
            WHERE "gugun" ILIKE %s
            ''',
            (f"%{district.replace('구', '')}%",),
        )
    inspection_rows = []
    if inspection_table:
        inspection_rows = _rows(
            f'''
            SELECT "FCLTY_NM" AS name, "FCLTY_ROAD_NM_ADDR" AS address,
                   "CMPTNC_SIGNGU_NM" AS district, "SAFECHK_GNRLZ_GRAD_NM" AS grade,
                   "SAFECHK_DE" AS checked_at, "OPER_STATE_NM" AS operation_state
            FROM {inspection_table}
            WHERE "CMPTNC_SIGNGU_NM" ILIKE %s
            ''',
            (f"%{district.replace('구', '')}%",),
        )

    for row in rows:
        safety = _safety_data_unavailable()
        facility_name = _normalise_text(row.get("name"))
        facility_address = _normalise_text(row.get("address"))
        facility_point = (row.get("latitude"), row.get("longitude"))
        if aed_rows:
            nearest = None
            nearest_distance = None
            for aed in aed_rows:
                distance = _distance_km(facility_point, {"latitude": aed.get("latitude"), "longitude": aed.get("longitude")}) if all(facility_point) else None
                same_address = facility_address and _normalise_text(aed.get("address")) in facility_address
                if same_address or (distance is not None and (nearest_distance is None or distance < nearest_distance)):
                    nearest, nearest_distance = aed, distance
            if nearest:
                location = nearest.get("name") or nearest.get("address") or "시설 인근"
                safety["aed"] = {
                    "status": "available",
                    "label": f"AED 확인: {location}",
                    "name": nearest.get("name") or "",
                    "address": nearest.get("address") or "",
                }
        if inspection_rows:
            matched = next(
                (inspection for inspection in inspection_rows
                 if _normalise_text(inspection.get("name")) == facility_name
                 or (_normalise_text(inspection.get("name")) and _normalise_text(inspection.get("name")) in facility_name)
                 or (_normalise_text(inspection.get("address")) and _normalise_text(inspection.get("address")) in facility_address)),
                None,
            )
            if matched:
                grade = matched.get("grade") or "등급 확인 필요"
                checked_at = str(matched.get("checked_at") or "점검일 확인 필요")
                safety["inspection"] = {
                    "status": "available",
                    "label": f"안전점검 {grade} · {checked_at[:10]}",
                    "grade": grade,
                    "checked_at": checked_at,
                    "operation_state": matched.get("operation_state") or "",
                }
        row["safety"] = safety


def make_recommendations(
    region: str,
    sports: set[str],
    available: int,
    max_travel: int,
    origin: tuple[float, float] | None = None,
) -> dict:
    _load_env()
    sido, district = _parts(region)
    if not sido or not district:
        return {"region": region, "facilities": [], "recommendations": [], "environment": {}}
    location_origin = origin is not None
    if origin is None:
        origin = _region_coordinate(region)
    facilities = facilities_for_region(
        sido,
        district,
        limit=1000,
        origin=origin,
        nearby_only=location_origin,
    )
    environment_region = (sido, district)
    if location_origin:
        environment_region = _region_for_coordinate(origin) or environment_region
    environment = environment_for_region(*environment_region)
    selected_sports = {"fitness" if sport in {"fitness", "헬스"} else sport for sport in sports}
    air = environment.get("air", {})
    weather = environment.get("weather", {})
    pm10 = _number(air.get("pm10Value"))
    pm25 = _number(air.get("pm25Value"))
    temperature = _number(weather.get("T1H"))
    humidity = _number(weather.get("REH"))
    wind_speed = _number(weather.get("WSD"))
    rain_amount = _number(weather.get("RN1")) or 0
    precipitation_type = str(weather.get("PTY") or "0")
    bad_air = (pm10 is not None and pm10 >= 81) or (pm25 is not None and pm25 >= 36)
    weather_summary = {
        "temperature_c": temperature,
        "humidity_percent": humidity,
        "wind_speed_mps": wind_speed,
        "rain_1h_mm": rain_amount,
        "precipitation_type": precipitation_type,
        "pm10": pm10,
        "pm25": pm25,
    }
    rows = []
    for item in facilities:
        sport = _sport_for(item)
        if selected_sports and sport not in selected_sports:
            continue
        db_distance = item.get("db_distance_km")
        # 현재 위치를 보낸 경우 DB에 저장된 거리값보다 원본 좌표로
        # 다시 계산한 직선거리를 우선한다. 잘못된 좌표/단위로 10,000km
        # 같은 값이 노출되는 것을 막기 위한 방어 로직이다.
        distance = _distance_km(origin, item) if origin else None
        if distance is None:
            try:
                distance = float(db_distance) if db_distance is not None else None
            except (TypeError, ValueError):
                distance = None
        if distance is not None and (distance < 0 or distance > 500):
            continue
        travel_minutes = round(distance * 20) if distance is not None else None
        if travel_minutes is not None and travel_minutes > max_travel:
            continue
        # 거리 40점 + 실내외·날씨·대기질 60점의 규칙 기반 점수다.
        distance_score = max(0.0, 40.0 - ((distance or (max_travel / 20)) * 18.0))
        score = 45.0 + distance_score
        weather_adjustment = 0.0
        air_quality_adjustment = 0.0
        reasons = [
            "현재 위치 주변 시설" if location_origin else f"{district} 시설 DB 일치",
            "시설 기본정보 확인",
        ]
        if distance is not None:
            reasons.append(f"거리 {distance:.3f}km 반영")
        outdoor = _is_outdoor(item)
        raining = precipitation_type not in ("", "0", "강수없음") or rain_amount > 0
        if raining and outdoor:
            score -= 24
            weather_adjustment -= 24
            reasons.append("강수 가능성으로 실내 시설 우선")
        elif raining and not outdoor:
            score += 8
            weather_adjustment += 8
            reasons.append("비가 와서 실내 시설 우선")
        if temperature is not None:
            if outdoor and (temperature < 5 or temperature > 30):
                score -= 10
                weather_adjustment -= 10
                reasons.append("기온이 실외 운동에 불리함")
            elif outdoor and 10 <= temperature <= 25:
                score += 6
                weather_adjustment += 6
                reasons.append("기온이 실외 운동에 적합")
        if humidity is not None:
            if outdoor and humidity >= 80:
                score -= 8
                weather_adjustment -= 8
                reasons.append("습도가 높아 실내 운동 우선")
            elif outdoor and 40 <= humidity <= 70:
                score += 4
                weather_adjustment += 4
                reasons.append("습도가 실외 운동에 적합")
        if wind_speed is not None and outdoor and wind_speed >= 8:
            score -= 8
            weather_adjustment -= 8
            reasons.append("풍속이 높아 실내 운동 우선")
        if bad_air and not outdoor:
            score += 14
            air_quality_adjustment += 14
            reasons.append("미세먼지가 높아 실내 시설 우선")
        elif not bad_air and outdoor:
            score += 5
            air_quality_adjustment += 5
            reasons.append("미세먼지가 양호해 실외 운동 가능")
        if environment.get("weather"):
            reasons.append("기온·습도·강수·풍속 반영")
        if environment.get("air"):
            reasons.append("PM10·PM2.5 반영")
        operation_notice = item.get("operation_notice", "")
        if operation_notice:
            reasons.append("시설 운영·휴무 공지 확인")
        rows.append({
            "id": len(rows) + 1,
            "name": item["facility_name"],
            "sport": sport,
            "facility_type": item["facility_type"],
            "address": item["address"],
            "province": item["city"],
            "district": item["district"],
            "indoor": not _is_outdoor(item),
            "travel_time": travel_minutes if travel_minutes is not None else "확인 필요",
            "distance_km": round(distance, 3) if distance is not None else None,
            "latitude": item.get("latitude"),
            "longitude": item.get("longitude"),
            "available_exercise_minutes": max(10, available),
            "score": max(0, min(99, round(score))),
            "score_breakdown": {
                "base": 45,
                "distance": round(distance_score, 2),
                "weather": weather_adjustment,
                "air_quality": air_quality_adjustment,
                "operation": 0,
                "final": max(0, min(99, round(score))),
                "before_operation": max(0, min(99, round(score))),
            },
            "reasons": reasons,
            "source": item["source"],
            "operation_notice": operation_notice,
            "safety": _safety_data_unavailable(),
        })
    fallback_used = False
    if not rows:
        fallback_facilities = _kakao_fallback_facilities(origin, region, selected_sports)
        fallback_used = bool(fallback_facilities)
        for item in fallback_facilities:
            sport = item.get("fallback_sport") or _sport_for(item)
            distance = item.get("db_distance_km")
            travel_minutes = round(distance * 20) if distance is not None else None
            score = max(25.0, 70.0 - ((distance or (max_travel / 20)) * 12.0))
            reasons = [
                "DB에 일치 시설이 없어 카카오 장소 검색으로 보완",
                "외부 장소 검색 결과는 운영정보 확인 필요",
            ]
            if distance is not None:
                reasons.append(f"거리 {distance:.3f}km 반영")
            if travel_minutes is not None and travel_minutes > max_travel:
                continue
            if environment.get("weather"):
                reasons.append("기온·습도·강수·풍속 반영")
            if environment.get("air"):
                reasons.append("PM10·PM2.5 반영")
            rows.append({
                "id": len(rows) + 1,
                "name": item["facility_name"],
                "sport": sport,
                "facility_type": item["facility_type"],
                "address": item["address"],
                "province": item["city"],
                "district": item["district"],
                "indoor": not _is_outdoor(item),
                "travel_time": travel_minutes if travel_minutes is not None else "확인 필요",
                "distance_km": round(distance, 3) if distance is not None else None,
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "available_exercise_minutes": max(10, available),
                "score": max(0, min(99, round(score))),
                "score_breakdown": {
                    "base": 70,
                    "distance": round(-((distance or (max_travel / 20)) * 12.0), 2),
                    "weather": 0,
                    "air_quality": 0,
                    "operation": 0,
                    "final": max(0, min(99, round(score))),
                    "before_operation": max(0, min(99, round(score))),
                },
                "reasons": reasons,
                "source": item["source"],
                "homepage": item.get("homepage", ""),
                "operation_notice": "",
                "safety": _safety_data_unavailable(),
            })
    # 거리·환경 점수를 합산한 최종 점수순으로 정렬하고, 동점이면 가까운 시설을 우선한다.
    rows.sort(key=lambda row: (
        -row["score"],
        row["distance_km"] if row["distance_km"] is not None else 999999,
    ))
    rows = rows[:20]
    _attach_safety_data(rows, district)
    _attach_live_operation_evidence(rows, limit=10)
    rows.sort(key=lambda row: (
        -row["score"],
        row["distance_km"] if row["distance_km"] is not None else 999999,
    ))
    return {
        "region": f"{sido} {district}",
        "facilities": facilities,
        "recommendations": rows,
        "environment": {**environment, "metrics": weather_summary},
        "distance_source": "PostGIS 현재 위치 좌표" if location_origin else "지역 중심 좌표",
        "fallback_used": fallback_used,
        "operation_check": "추천 시점 상위 시설 공개 운영정보 확인",
    }
