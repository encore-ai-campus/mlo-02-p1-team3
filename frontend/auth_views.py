from functools import wraps

from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError, transaction
import json

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .auth_forms import LoginForm, SignupForm
from .models import (
    FriendNote,
    FriendRequest,
    Friendship,
    Member,
    SelectedRecommendation,
    SiteVisit,
    WorkoutProgress,
    generate_friend_code,
)
from .recommendation_service import make_recommendations
from .dragon import DRAGON_DESIGNS, character_payload, dragon_level
from .progression import clamp_calories, level_for_calories

LOGIN_ERROR_MESSAGE = "아이디 또는 비밀번호 오류입니다."
GUEST_SESSION_KEY = "guest_mode"
GUEST_MEMBER_NICKNAME = "우심운까"


def _current_member(request):
    member_id = request.session.get("member_id")
    if not member_id:
        return None
    member = Member.objects.filter(pk=member_id).first()
    if member is None:
        request.session.pop("member_id", None)
        request.session.pop("member_nickname", None)
    return member


def _is_guest(request):
    return bool(request.session.get(GUEST_SESSION_KEY))


def _guest_member():
    """Return the shared read-only demo account used by guest mode."""
    return Member.objects.filter(nickname=GUEST_MEMBER_NICKNAME).first()


def member_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        member = _current_member(request)
        is_guest = _is_guest(request)
        if member is None and is_guest:
            member = _guest_member()
            if member is not None:
                request.session["member_id"] = member.pk
                request.session["member_nickname"] = member.nickname
        if member is None:
            return redirect("login")
        request.usim_member = member
        request.usim_guest = is_guest
        return view_func(request, *args, **kwargs)
    return wrapped


def app_access_required(view_func):
    """회원 또는 오프닝에서 시작한 게스트에게 앱 전체 페이지 접근을 허용한다."""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        member = _current_member(request)
        is_guest = _is_guest(request)
        if member is None and is_guest:
            member = _guest_member()
            if member is not None:
                request.session["member_id"] = member.pk
                request.session["member_nickname"] = member.nickname
        if member is None and not is_guest:
            return redirect("login")
        if member is None:
            return redirect("welcome")

        if member is not None and not is_guest:
            request.session.pop(GUEST_SESSION_KEY, None)

        request.usim_member = member
        request.usim_guest = is_guest
        return view_func(request, *args, **kwargs)
    return wrapped


def _app_context(request, active_tab):
    member = getattr(request, "usim_member", None) or _current_member(request)
    is_guest = bool(getattr(request, "usim_guest", False)) or (member is None and _is_guest(request))
    if not request.session.session_key:
        request.session.create()
    visitor_key = request.session.session_key
    today = timezone.localdate()
    SiteVisit.objects.get_or_create(visitor_key=visitor_key, visited_on=today)
    return {
        "active_tab": active_tab,
        "member": member,
        "is_guest": is_guest,
        "site_today": SiteVisit.objects.filter(visited_on=today).count(),
        "site_total": SiteVisit.objects.values("visitor_key").distinct().count(),
    }


def welcome(request):
    return render(request, "pages/welcome.html")


@require_POST
def guest_start(request):
    """심사위원용 우심운까 계정을 읽기 전용 게스트 세션으로 시작한다."""
    member = _current_member(request)
    if member is not None and not _is_guest(request):
        # 이미 로그인된 사용자는 자신의 방으로 바로 보낸다.
        request.session.pop(GUEST_SESSION_KEY, None)
        return redirect("home")

    demo_member = _guest_member()
    if demo_member is None:
        return redirect("login")

    request.session.cycle_key()
    request.session["member_id"] = demo_member.pk
    request.session["member_nickname"] = demo_member.nickname
    request.session[GUEST_SESSION_KEY] = True
    return redirect("home")


@never_cache
@require_http_methods(["GET", "POST"])
def signup_page(request):
    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            Member.objects.create(
                name=form.cleaned_data["name"],
                nickname=form.cleaned_data["nickname"],
                password_hash=make_password(form.cleaned_data["password"]),
                address=form.cleaned_data["address"],
                friend_code=generate_friend_code(),
            )
            return redirect("login")
    else:
        form = SignupForm()
    return render(request, "pages/signup.html", {"form": form})


@never_cache
@require_http_methods(["GET", "POST"])
def login_page(request):
    error = None
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            member = Member.objects.filter(nickname=form.cleaned_data["nickname"]).first()
            valid = member is not None and check_password(
                form.cleaned_data["password"], member.password_hash
            )
            if not valid:
                error = LOGIN_ERROR_MESSAGE
            else:
                request.session.cycle_key()
                request.session.pop(GUEST_SESSION_KEY, None)
                request.session["member_id"] = member.pk
                request.session["member_nickname"] = member.nickname
                return redirect("login_loading")
        else:
            # 입력 형식 오류는 필드 오류로 표시하되 계정 존재 여부는 노출하지 않는다.
            if request.POST.get("nickname") and request.POST.get("password"):
                error = LOGIN_ERROR_MESSAGE
    else:
        form = LoginForm()

    return render(request, "pages/login.html", {"form": form, "error": error})


@never_cache
@member_required
def login_loading(request):
    return render(request, "pages/login_loading.html")


@never_cache
@member_required
@require_GET
def prepare_login_home(request):
    """로그인 전환 화면에서 메인 추천을 미리 계산해 다음 화면의 대기시간을 줄인다."""
    member = request.usim_member
    try:
        available = 60
        max_travel = 20
        payload = make_recommendations(member.address, set(), available, max_travel, None)
        request.session["preloaded_home_recommendations"] = payload.get("recommendations", [])
        request.session.modified = True
        return JsonResponse({"ready": True})
    except Exception as exc:
        return JsonResponse({"ready": False, "error": str(exc)}, status=503)


@require_POST
def logout_page(request):
    request.session.flush()
    return redirect("welcome")


@never_cache
@require_GET
def check_member_nickname(request):
    nickname = request.GET.get("nickname", "").strip()
    available = bool(nickname) and not Member.objects.filter(nickname=nickname).exists()
    return JsonResponse({"available": available})


@never_cache
@member_required
@require_POST
def select_recommendation_api(request):
    """추천 시설을 오늘 운동 장소로 저장하고 지도 이동에 필요한 값을 반환한다."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "추천 시설 정보 형식이 올바르지 않습니다."}, status=400)

    name = str(payload.get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "선택할 운동 시설이 없습니다."}, status=400)

    def optional_float(value):
        if value in (None, ""):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number == number else None

    try:
        score = max(0, min(99, int(payload.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    snapshot = {
        "facility_type": str(payload.get("facility_type") or ""),
        "province": str(payload.get("province") or ""),
        "district": str(payload.get("district") or ""),
        "indoor": bool(payload.get("indoor")),
        "distance_km": payload.get("distance_km"),
        "travel_time": payload.get("travel_time"),
        "score_breakdown": payload.get("score_breakdown") or {},
        "reasons": payload.get("reasons") or [],
        "operation_notice": str(payload.get("operation_notice") or ""),
        "safety": payload.get("safety") or {},
        "source": str(payload.get("source") or ""),
    }
    selected = SelectedRecommendation.objects.create(
        member=request.usim_member,
        facility_name=name[:200],
        sport=str(payload.get("sport") or "")[:40],
        address=str(payload.get("address") or "")[:300],
        latitude=optional_float(payload.get("latitude")),
        longitude=optional_float(payload.get("longitude")),
        score=score,
        recommendation_snapshot=snapshot,
    )
    return JsonResponse({
        "selected": True,
        "id": selected.id,
        "facility_name": selected.facility_name,
        "latitude": selected.latitude,
        "longitude": selected.longitude,
    })


def _member_progress_payload(member):
    if not member.friend_code:
        member.friend_code = generate_friend_code()
        member.save(update_fields=["friend_code", "updated_at"])
    progress, _ = WorkoutProgress.objects.get_or_create(member=member)
    total = clamp_calories(progress.total_calories)
    return {
        "friend_code": member.friend_code,
        "total_calories": total,
        "level": level_for_calories(total),
        "entries": progress.entries if isinstance(progress.entries, list) else [],
    }


@never_cache
@app_access_required
@require_GET
def account_state(request):
    member = getattr(request, "usim_member", None)
    if member is None:
        return JsonResponse({"friend_code": "", "total_calories": 0, "level": 1, "entries": []})
    return JsonResponse(_member_progress_payload(member))


@never_cache
@app_access_required
@require_POST
def add_workout_calories(request):
    member = getattr(request, "usim_member", None)
    if member is None:
        return JsonResponse({"error": "회원 로그인 후 운동량을 저장할 수 있습니다."}, status=401)
    if getattr(request, "usim_guest", False):
        return JsonResponse({"error": "게스트 모드에서는 보기만 가능합니다."}, status=403)
    try:
        body = json.loads(request.body or "{}")
        amount = int(body.get("calories", 0))
    except (TypeError, ValueError, json.JSONDecodeError):
        amount = 0
    if amount <= 0:
        return JsonResponse({"error": "칼로리는 1 이상이어야 합니다."}, status=400)
    progress, _ = WorkoutProgress.objects.get_or_create(member=member)
    entries = progress.entries if isinstance(progress.entries, list) else []
    entries.insert(0, {"calories": amount, "created_at": timezone.now().isoformat()})
    progress.total_calories = clamp_calories(progress.total_calories) + amount
    progress.entries = entries[:30]
    progress.save(update_fields=["total_calories", "entries", "updated_at"])
    return JsonResponse(_member_progress_payload(member))


@never_cache
@member_required
@require_POST
def reset_workout_progress(request):
    """회원이 확인 후 운동량과 레벨을 LV.1 상태로 초기화한다."""
    if getattr(request, "usim_guest", False):
        return JsonResponse({"error": "게스트 모드에서는 초기화할 수 없습니다."}, status=403)
    progress, _ = WorkoutProgress.objects.get_or_create(member=request.usim_member)
    progress.total_calories = 0
    progress.entries = []
    progress.save(update_fields=["total_calories", "entries", "updated_at"])
    room_state = request.usim_member.room_state if isinstance(request.usim_member.room_state, dict) else {}
    room_state["characterSkin"] = "default"
    request.usim_member.room_state = room_state
    request.usim_member.save(update_fields=["room_state", "updated_at"])
    return JsonResponse(_member_progress_payload(request.usim_member))


@never_cache
@member_required
@require_POST
def undo_last_workout_calories(request):
    """가장 최근에 기록한 운동량 한 건을 되돌린다."""
    if getattr(request, "usim_guest", False):
        return JsonResponse({"error": "게스트 모드에서는 기록을 되돌릴 수 없습니다."}, status=403)
    progress = WorkoutProgress.objects.filter(member=request.usim_member).first()
    entries = progress.entries if progress and isinstance(progress.entries, list) else []
    if not progress or not entries:
        return JsonResponse({"error": "되돌릴 최근 운동 기록이 없습니다."}, status=400)
    latest = entries[0] if isinstance(entries[0], dict) else {}
    try:
        amount = int(latest.get("calories", 0))
    except (TypeError, ValueError):
        amount = 0
    if amount <= 0:
        return JsonResponse({"error": "최근 운동 기록의 칼로리 값을 확인할 수 없습니다."}, status=400)
    progress.total_calories = max(0, clamp_calories(progress.total_calories) - amount)
    progress.entries = entries[1:30]
    progress.save(update_fields=["total_calories", "entries", "updated_at"])
    return JsonResponse(_member_progress_payload(request.usim_member))


@never_cache
def main_page(request):
    """회원은 자신의 방, 게스트는 오프닝에서 시작한 체험 방에 접근한다."""
    member = _current_member(request)
    is_guest = _is_guest(request)
    if member is None and is_guest:
        member = _guest_member()
        if member is not None:
            request.session["member_id"] = member.pk
            request.session["member_nickname"] = member.nickname
    if member is None and not is_guest:
        return redirect("login")
    if member is None:
        return redirect("welcome")

    if member is not None and not is_guest:
        request.session.pop(GUEST_SESSION_KEY, None)

    request.usim_member = member
    request.usim_guest = is_guest
    context = _app_context(request, "home")
    context["room_owner"] = member
    context["room_is_visitor"] = False
    owner_progress = getattr(member, "workout_progress", None) if member is not None else None
    context["visitor_total_calories"] = clamp_calories(owner_progress.total_calories) if owner_progress else 0
    address = member.address if member is not None else "서울특별시 관악구"
    try:
        latitude = float(request.GET["latitude"]) if request.GET.get("latitude") else None
        longitude = float(request.GET["longitude"]) if request.GET.get("longitude") else None
        if latitude is not None and not -90 <= latitude <= 90:
            latitude = longitude = None
        if longitude is not None and not -180 <= longitude <= 180:
            latitude = longitude = None
        if latitude == 0 and longitude == 0:
            latitude = longitude = None
        origin = (latitude, longitude) if latitude is not None and longitude is not None else None
        available = max(1, int(request.GET.get("available_minutes", "60")))
        max_travel = max(0, int(request.GET.get("max_travel_minutes", "20")))
        preloaded = request.session.pop("preloaded_home_recommendations", None) if origin is None else None
        payload = None
        if preloaded is not None:
            payload = {"recommendations": preloaded}
        else:
            payload = make_recommendations(address, set(), available, max_travel, origin)
        context["initial_recommendations"] = payload.get("recommendations", [])
        context["location_loaded"] = bool(origin)
    except Exception:
        context["initial_recommendations"] = []
        context["location_loaded"] = False
    return render(request, "frontend/home.html", context)


@never_cache
@app_access_required
def recommend_page(request):
    return render(request, "frontend/recommend.html", _app_context(request, "recommend"))


@never_cache
@app_access_required
def friends_page(request):
    return render(request, "frontend/friends.html", _app_context(request, "friends"))


@never_cache
@member_required
def friend_visitor_page(request, member_id):
    """친구가 꾸민 MY ROOM을 그대로 보여주는 방문자 홈페이지."""
    visitor = Member.objects.filter(pk=member_id).first()
    if visitor is None or not Friendship.objects.filter(
        member=request.usim_member, friend=visitor
    ).exists():
        return redirect("friends")

    progress = getattr(visitor, "workout_progress", None)
    total_calories = clamp_calories(progress.total_calories) if progress else 0
    context = _app_context(request, "friends")
    context.update({
        "room_owner": visitor,
        "room_is_visitor": True,
        "visitor_total_calories": total_calories,
        "visitor_level": level_for_calories(total_calories),
    })
    try:
        latitude = float(request.GET["latitude"]) if request.GET.get("latitude") else None
        longitude = float(request.GET["longitude"]) if request.GET.get("longitude") else None
        if latitude is not None and not -90 <= latitude <= 90:
            latitude = longitude = None
        if longitude is not None and not -180 <= longitude <= 180:
            latitude = longitude = None
        if latitude == 0 and longitude == 0:
            latitude = longitude = None
        origin = (latitude, longitude) if latitude is not None and longitude is not None else None
        payload = make_recommendations(visitor.address, set(), 60, 20, origin)
        context["initial_recommendations"] = payload.get("recommendations", [])
        context["location_loaded"] = bool(origin)
    except Exception:
        context["initial_recommendations"] = []
        context["location_loaded"] = False
    return render(request, "frontend/home.html", context)


def _friend_progress(member):
    progress = getattr(member, "workout_progress", None)
    total = clamp_calories(progress.total_calories) if progress else 0
    return total


def _friend_payload(member):
    """친구 화면에서 필요한 공개 프로필만 반환한다."""
    if not member.friend_code:
        member.friend_code = generate_friend_code()
        member.save(update_fields=["friend_code", "updated_at"])
    total = _friend_progress(member)
    return {
        "id": member.pk,
        "friend_code": member.friend_code,
        "nickname": member.nickname,
        "region": member.address or "지역 미설정",
        "sport": "fitness",
        "preferred_sports": ["fitness"],
        "calories": total,
        "status": "운동 기록 있음" if total else "운동 기다리는 중",
        "message": "오늘도 같이 움직여요!",
        "mood": "energy" if total else "ready",
        "pose": "main",
    }


def _friend_list(member):
    relations = Friendship.objects.filter(member=member).select_related("friend")
    return [_friend_payload(relation.friend) for relation in relations]


def _json_body(request):
    try:
        return json.loads(request.body or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


@never_cache
@member_required
@require_http_methods(["GET", "POST"])
def room_state_api(request, member_id=None):
    """내 방은 저장하고, 친구 방은 읽기 전용으로 조회한다."""
    current = request.usim_member
    owner = current if member_id is None else Member.objects.filter(pk=member_id).first()
    if owner is None:
        return JsonResponse({"error": "방을 찾지 못했어요."}, status=404)
    if owner.pk != current.pk and not Friendship.objects.filter(member=current, friend=owner).exists():
        return JsonResponse({"error": "친구의 운동방만 볼 수 있어요."}, status=403)
    if request.method == "GET":
        return JsonResponse({"state": owner.room_state or {}, "layout": owner.room_layout or {}})
    if getattr(request, "usim_guest", False):
        return JsonResponse({"error": "게스트 모드에서는 보기만 가능합니다."}, status=403)
    if owner.pk != current.pk:
        return JsonResponse({"error": "친구의 운동방은 수정할 수 없어요."}, status=403)
    body = _json_body(request)
    state = body.get("state") if isinstance(body.get("state"), dict) else {}
    layout = body.get("layout") if isinstance(body.get("layout"), dict) else {}
    # Character skins and special furniture are level rewards. Validate the
    # saved JSON on the server too, so a client cannot equip a locked asset.
    skin_levels = {
        "default": 1,
        "hanbokFemale": 5,
        "hanbokMale": 5,
        "hanbokFemale2": 5,
        "hanbokMale2": 5,
        "hanbokRedFemale": 1,
        "hanbokOrangeMale": 1,
        "hanbokBlackMale": 1,
        "hanbokBlackFemale": 1,
        "hanbokPinkFemale": 1,
        "rockMale": 20,
        "rockFemale": 20,
        "highendMale": 50,
        "highendFemale": 50,
    }
    requested_skin = state.get("characterSkin", "default")
    progress = WorkoutProgress.objects.filter(member=owner).first()
    current_level = level_for_calories(progress.total_calories) if progress else 1
    if requested_skin not in skin_levels or current_level < skin_levels[requested_skin]:
        requested_skin = "default"
    state["characterSkin"] = requested_skin
    visible = state.get("visible") if isinstance(state.get("visible"), dict) else {}
    if current_level < 20:
        for key in ("specialShelf", "specialTurntable", "specialAmp", "specialSofa", "specialRug", "specialLamp"):
            visible[key] = False
    state["visible"] = visible
    owner.room_state = state
    owner.room_layout = layout
    owner.save(update_fields=["room_state", "room_layout", "updated_at"])
    return JsonResponse({"saved": True, "state": state, "layout": layout})


@never_cache
@member_required
@require_http_methods(["GET", "POST"])
def dragon_character_api(request):
    """챗봇과 프로필이 함께 사용하는 우심이 성장/선택 상태 API."""
    member = request.usim_member
    if request.method == "GET":
        return JsonResponse(character_payload(member))
    if getattr(request, "usim_guest", False):
        return JsonResponse({"error": "게스트 모드에서는 우심이를 변경할 수 없습니다."}, status=403)

    body = _json_body(request)
    design = body.get("design")
    level = dragon_level(member)
    if design not in DRAGON_DESIGNS:
        return JsonResponse({"error": "선택할 수 없는 우심이입니다."}, status=400)
    if level < 40:
        return JsonResponse({"error": "레벨 40부터 우심이 디자인을 선택할 수 있습니다."}, status=403)
    member.selected_dragon_design = design
    member.save(update_fields=["selected_dragon_design", "updated_at"])
    return JsonResponse({"saved": True, **character_payload(member)})


@never_cache
@member_required
@require_GET
def friends_api(request):
    member = request.usim_member
    return JsonResponse({"friends": _friend_list(member)})


@never_cache
@member_required
@require_GET
def friend_lookup_api(request):
    identifier = request.GET.get("code", "").strip()
    if not identifier:
        return JsonResponse({"error": "친구 코드 또는 아이디를 입력해주세요."}, status=400)
    if identifier.upper().startswith("USIM-"):
        target = Member.objects.filter(friend_code=identifier.upper()).first()
    else:
        target = Member.objects.filter(nickname=identifier).first()
    if target is None:
        return JsonResponse({"error": "해당 친구 코드 또는 아이디를 찾지 못했어요."}, status=404)
    if target.pk == request.usim_member.pk:
        return JsonResponse({"error": "내 친구 코드는 조회할 수 없어요."}, status=400)
    return JsonResponse({"friend": _friend_payload(target)})


def _friend_request_payload(friend_request):
    requester = friend_request.requester
    return {
        "id": friend_request.pk,
        "nickname": requester.nickname,
        "friend_code": requester.friend_code,
        "region": requester.address or "지역 미설정",
        "created_at": timezone.localtime(friend_request.created_at).strftime("%m/%d %H:%M"),
    }


@never_cache
@member_required
@require_GET
def friend_requests_api(request):
    requests = FriendRequest.objects.filter(
        recipient=request.usim_member, status=FriendRequest.STATUS_PENDING
    ).select_related("requester")
    return JsonResponse({"requests": [_friend_request_payload(row) for row in requests]})


@never_cache
@member_required
@require_POST
def respond_friend_request_api(request):
    if getattr(request, "usim_guest", False):
        return JsonResponse({"error": "게스트 모드에서는 보기만 가능합니다."}, status=403)
    body = _json_body(request)
    try:
        request_id = int(body.get("request_id"))
    except (TypeError, ValueError):
        request_id = 0
    action = str(body.get("action", "")).strip().lower()
    if action not in {"accept", "decline"} or not request_id:
        return JsonResponse({"error": "친구 요청 처리 정보가 올바르지 않아요."}, status=400)

    friend_request = FriendRequest.objects.filter(
        pk=request_id,
        recipient=request.usim_member,
        status=FriendRequest.STATUS_PENDING,
    ).select_related("requester").first()
    if friend_request is None:
        return JsonResponse({"error": "처리할 친구 요청을 찾지 못했어요."}, status=404)

    if action == "decline":
        friend_request.status = FriendRequest.STATUS_DECLINED
        friend_request.responded_at = timezone.now()
        friend_request.save(update_fields=["status", "responded_at"])
        return JsonResponse({"status": "declined"})

    with transaction.atomic():
        friend_request.status = FriendRequest.STATUS_ACCEPTED
        friend_request.responded_at = timezone.now()
        friend_request.save(update_fields=["status", "responded_at"])
        Friendship.objects.get_or_create(member=request.usim_member, friend=friend_request.requester)
        Friendship.objects.get_or_create(member=friend_request.requester, friend=request.usim_member)
    return JsonResponse({"status": "accepted", "friend": _friend_payload(friend_request.requester)})


@never_cache
@member_required
@require_POST
def add_friend_api(request):
    if getattr(request, "usim_guest", False):
        return JsonResponse({"error": "게스트 모드에서는 보기만 가능합니다."}, status=403)
    member = request.usim_member
    code = str(_json_body(request).get("friend_code", "")).strip().upper()
    if not code:
        return JsonResponse({"error": "친구 코드를 입력해주세요."}, status=400)
    target = Member.objects.filter(friend_code=code).first()
    if target is None:
        return JsonResponse({"error": "해당 친구 코드를 찾지 못했어요."}, status=404)
    if target.pk == member.pk:
        return JsonResponse({"error": "내 친구 코드는 추가할 수 없어요."}, status=400)

    if Friendship.objects.filter(member=member, friend=target).exists():
        return JsonResponse({"error": "이미 친구로 추가된 회원이에요.", "friends": _friend_list(member)}, status=409)
    if FriendRequest.objects.filter(
        requester=member, recipient=target, status=FriendRequest.STATUS_PENDING
    ).exists():
        return JsonResponse({"error": "이미 친구 요청을 보냈어요."}, status=409)
    if FriendRequest.objects.filter(
        requester=target, recipient=member, status=FriendRequest.STATUS_PENDING
    ).exists():
        return JsonResponse({"error": "상대가 보낸 친구 요청을 먼저 승인해주세요."}, status=409)

    friend_request = FriendRequest.objects.create(requester=member, recipient=target)
    return JsonResponse({"request": _friend_request_payload(friend_request), "status": "pending"}, status=201)


@never_cache
@member_required
@require_GET
def friend_notes_api(request):
    member = request.usim_member
    visible_ids = [member.pk] + list(
        Friendship.objects.filter(member=member).values_list("friend_id", flat=True)
    )
    notes = FriendNote.objects.filter(author_id__in=visible_ids).select_related("author")[:5]
    return JsonResponse({
        "notes": [
            {
                "id": note.pk,
                "author": note.author.nickname,
                "text": note.text,
                "time": timezone.localtime(note.created_at).strftime("%H:%M"),
            }
            for note in notes
        ]
    })


@never_cache
@member_required
@require_POST
def create_friend_note_api(request):
    if getattr(request, "usim_guest", False):
        return JsonResponse({"error": "게스트 모드에서는 보기만 가능합니다."}, status=403)
    text = str(_json_body(request).get("text", "")).strip()
    if not text:
        return JsonResponse({"error": "한마디를 입력해주세요."}, status=400)
    if len(text) > 60:
        return JsonResponse({"error": "한마디는 60자 이내로 입력해주세요."}, status=400)
    note = FriendNote.objects.create(author=request.usim_member, text=text)
    return JsonResponse({
        "note": {
            "id": note.pk,
            "author": note.author.nickname,
            "text": note.text,
            "time": timezone.localtime(note.created_at).strftime("%H:%M"),
        }
    }, status=201)


@never_cache
@app_access_required
def profile_page(request):
    return render(request, "frontend/profile.html", _app_context(request, "profile"))


@never_cache
@app_access_required
def diary_page(request):
    return render(request, "frontend/diary.html", _app_context(request, "diary"))
