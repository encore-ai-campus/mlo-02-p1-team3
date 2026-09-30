"""운동 칼로리를 ROOM 레벨로 변환하는 공통 성장 곡선."""

from functools import lru_cache


MAX_TOTAL_CALORIES = 600_000
MAX_ROOM_LEVEL = 100
BASE_LEVEL_EXP = 100
LEVEL_EXPONENT = 1.6


def clamp_calories(value: int | float | None) -> int:
    """저장된 누적 칼로리를 음수가 아닌 정수로 정규화한다."""
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


@lru_cache(maxsize=None)
def level_cost(level: int) -> int:
    """현재 레벨에서 다음 레벨로 가는 데 필요한 칼로리."""
    level = max(1, min(int(level), MAX_ROOM_LEVEL - 1))
    raw_total = sum(BASE_LEVEL_EXP * (number ** LEVEL_EXPONENT) for number in range(1, MAX_ROOM_LEVEL))
    level_count = MAX_ROOM_LEVEL - 1
    curve_scale = (MAX_TOTAL_CALORIES - (BASE_LEVEL_EXP * level_count)) / (raw_total - (BASE_LEVEL_EXP * level_count))
    raw_cost = BASE_LEVEL_EXP * (level ** LEVEL_EXPONENT)
    cost = round(BASE_LEVEL_EXP + (raw_cost - BASE_LEVEL_EXP) * curve_scale)
    if level == MAX_ROOM_LEVEL - 1:
        cost = MAX_TOTAL_CALORIES - sum(level_cost(number) for number in range(1, level))
    return max(BASE_LEVEL_EXP if level == 1 else 1, cost)


@lru_cache(maxsize=None)
def level_start(level: int) -> int:
    """해당 레벨에 진입하기 위해 필요한 누적 칼로리."""
    level = max(1, min(int(level), MAX_ROOM_LEVEL))
    return sum(level_cost(number) for number in range(1, level))


def level_for_calories(total_calories: int | float | None) -> int:
    total = min(MAX_TOTAL_CALORIES, clamp_calories(total_calories))
    for level in range(1, MAX_ROOM_LEVEL):
        if total < level_start(level + 1):
            return level
    return MAX_ROOM_LEVEL


def progress_for_calories(total_calories: int | float | None) -> dict[str, int | float]:
    total = clamp_calories(total_calories)
    level = level_for_calories(total)
    if level >= MAX_ROOM_LEVEL:
        return {
            "total": total,
            "level": MAX_ROOM_LEVEL,
            "current_exp": total - MAX_TOTAL_CALORIES,
            "next_exp": 0,
            "remaining": 0,
            "percent": 100,
        }
    next_exp = level_cost(level)
    current_exp = total - level_start(level)
    return {
        "total": total,
        "level": level,
        "current_exp": current_exp,
        "next_exp": next_exp,
        "remaining": max(0, next_exp - current_exp),
        "percent": max(0, min(100, (current_exp / next_exp) * 100)),
    }
