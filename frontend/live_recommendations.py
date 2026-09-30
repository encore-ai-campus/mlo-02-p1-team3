from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .recommendation_service import make_recommendations


@never_cache
@require_GET
def live_recommendations(request):
    province = " ".join((request.GET.get("province") or "").split())
    district = " ".join((request.GET.get("district") or "").split())
    region = f"{province} {district}".strip()
    if not province or not district:
        return JsonResponse({"error": "시도와 시군구를 입력해주세요."}, status=400)
    try:
        sports = {value.strip().lower() for value in request.GET.get("sports", "").split(",") if value.strip()}
        available = max(1, int(request.GET.get("available_minutes", "60")))
        max_travel = max(0, int(request.GET.get("max_travel_minutes", "20")))
        latitude_raw = (request.GET.get("latitude") or "").strip()
        longitude_raw = (request.GET.get("longitude") or "").strip()
        latitude = float(latitude_raw) if latitude_raw else None
        longitude = float(longitude_raw) if longitude_raw else None
        if latitude is not None and not -90 <= latitude <= 90:
            raise ValueError("위도 범위가 올바르지 않습니다.")
        if longitude is not None and not -180 <= longitude <= 180:
            raise ValueError("경도 범위가 올바르지 않습니다.")
        if (latitude is None) != (longitude is None):
            raise ValueError("위도와 경도를 함께 보내야 합니다.")
        if latitude == 0 and longitude == 0:
            latitude = longitude = None
        origin = (latitude, longitude) if latitude is not None else None
        payload = make_recommendations(region, sports, available, max_travel, origin)
    except Exception as exc:
        return JsonResponse({"error": "추천 데이터 조회에 실패했습니다.", "detail": str(exc)}, status=500)
    return JsonResponse({
        "source": "DATABASE_FIRST",
        "region": payload["region"],
        "environment": payload["environment"],
        "recommendations": payload["recommendations"],
        "distance_source": payload.get("distance_source", "지역 중심 좌표"),
        "notice": (
            ("DB 일치 시설이 없어 카카오 장소 검색 결과로 보완했습니다. " if payload.get("fallback_used") else "")
            + "추천 시점에 확인 가능한 공개 운영·휴무 정보를 다시 확인했습니다. 공개 페이지가 없는 시설은 확인 필요입니다."
        ),
    })
