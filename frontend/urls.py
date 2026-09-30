from django.urls import path

from . import auth_views
from . import chatbot_views
from . import views as legacy_views


urlpatterns = [
    # Opening / account
    path("", auth_views.welcome, name="welcome"),
    path("signup/", auth_views.signup_page, name="signup"),
    path("login/", auth_views.login_page, name="login"),
    path("login/loading/", auth_views.login_loading, name="login_loading"),
    path("login/loading-ready-data/", auth_views.prepare_login_home, name="prepare_login_home"),
    path("guest/start/", auth_views.guest_start, name="guest_start"),
    path("logout/", auth_views.logout_page, name="logout"),
    path("api/check-member-nickname/", auth_views.check_member_nickname, name="check_member_nickname"),
    path("api/selected-recommendation/", auth_views.select_recommendation_api, name="select_recommendation"),
    path("api/account-state/", auth_views.account_state, name="account_state"),
    path("api/workout-calories/", auth_views.add_workout_calories, name="add_workout_calories"),
    path("api/workout-calories/reset/", auth_views.reset_workout_progress, name="reset_workout_progress"),
    path("api/workout-calories/undo/", auth_views.undo_last_workout_calories, name="undo_last_workout_calories"),
    path("api/friends/", auth_views.friends_api, name="friends_api"),
    path("api/friends/lookup/", auth_views.friend_lookup_api, name="friend_lookup_api"),
    path("api/friends/add/", auth_views.add_friend_api, name="add_friend_api"),
    path("api/friend-requests/", auth_views.friend_requests_api, name="friend_requests_api"),
    path("api/friend-requests/respond/", auth_views.respond_friend_request_api, name="respond_friend_request_api"),
    path("api/friend-notes/", auth_views.friend_notes_api, name="friend_notes_api"),
    path("api/friend-notes/create/", auth_views.create_friend_note_api, name="create_friend_note_api"),
    path("api/room-state/", auth_views.room_state_api, name="room_state_api"),
    path("api/room-state/<int:member_id>/", auth_views.room_state_api, name="friend_room_state_api"),
    path("api/dragon-character/", auth_views.dragon_character_api, name="dragon_character_api"),
    # 일부 브라우저 확장 프로그램이 /api/ 경로를 차단할 때 사용하는 별칭
    path("account-state-data/", auth_views.account_state, name="account_state_data"),
    path("workout-calories-data/", auth_views.add_workout_calories, name="workout_calories_data"),

    # AI chatbot (OpenAI API key stays on the Django server)
    path("api/chatbot/", chatbot_views.chatbot_message, name="chatbot_message"),
    path("api/chatbot/clear/", chatbot_views.chatbot_clear, name="chatbot_clear"),

    # Logged-in app. Existing frontend templates / design are reused as-is.
    path("main/", auth_views.main_page, name="home"),
    path("main/", auth_views.main_page, name="index"),
    path("recommend/", auth_views.recommend_page, name="recommend"),
    path("friends/", auth_views.friends_page, name="friends"),
    path("friends/visitor/<int:member_id>/", auth_views.friend_visitor_page, name="friend_visitor"),
    path("profile/", auth_views.profile_page, name="profile"),
    path("diary/", auth_views.diary_page, name="diary"),
]

# Keep legacy recommendation/profile endpoints when they already exist in the project.
_optional_legacy_routes = [
    ("recommend/home/", "recommend_home", "recommend_home"),
    ("recommend/custom/", "recommend_custom", "recommend_custom"),
    ("local/", "local_consumption", "local_consumption"),
    ("profile/clear/", "clear_profile", "profile_clear"),
    ("api/check-nickname/", "check_nickname", "check_nickname"),
]
for route, attr, name in _optional_legacy_routes:
    view = getattr(legacy_views, attr, None)
    if view is not None:
        urlpatterns.append(path(route, view, name=name))

# Preserve optional recommendation API modules without making them a hard dependency
# for the newer frontend-only project variant.
try:
    from .profile_demo import demo_recommendations
except ImportError:
    demo_recommendations = None
if demo_recommendations is not None:
    urlpatterns.append(path("demo-api/recommendations/", demo_recommendations, name="profile_demo_recommendations"))

try:
    from .live_recommendations import live_recommendations
except ImportError:
    live_recommendations = None
if live_recommendations is not None:
    urlpatterns.append(path("api/live-recommendations/", live_recommendations, name="live_recommendations"))
    # 일부 브라우저 확장 프로그램이 recommendations 경로를 차단하는 경우를 위한 별칭
    urlpatterns.append(path("api/nearby-facilities/", live_recommendations, name="nearby_facilities"))
    # /api/ 자체를 차단하는 브라우저 확장 프로그램에서도 사용할 수 있는 경로
    urlpatterns.append(path("nearby-facilities-data/", live_recommendations, name="nearby_facilities_data"))
