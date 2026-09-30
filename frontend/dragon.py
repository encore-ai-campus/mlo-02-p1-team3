from django.templatetags.static import static


DRAGON_STAGES = {
    "egg": {"label": "알", "min_level": 1, "image": "egg.png"},
    "baby": {"label": "아기 용", "min_level": 5, "image": "baby.png"},
    "dragon": {"label": "성장한 용", "min_level": 10, "image": "dragon.png"},
}

DRAGON_DESIGNS = {
    "usim": {"label": "우심운까", "image": "usim.png", "price": 0, "free": True},
    "pink": {"label": "핑크 용", "image": "pink.png", "price": 0, "free": True},
    "blue": {"label": "파란 용", "image": "blue.png", "price": 0, "free": True},
}


def dragon_level(member):
    progress = getattr(member, "workout_progress", None)
    return progress.level if progress else 1


def character_payload(member):
    level = dragon_level(member)
    selected = member.selected_dragon_design if level >= 40 else ""
    if selected in DRAGON_DESIGNS and DRAGON_DESIGNS[selected]["free"]:
        design = DRAGON_DESIGNS[selected]
        image_key = selected
        stage = "final"
        label = design["label"]
    elif level >= 40 and selected in DRAGON_DESIGNS:
        # A paid design is never equipped by this feature until a purchase
        # flow exists. Keep the server-side response on the free default.
        image_key = "dragon"
        stage = "dragon"
        label = DRAGON_STAGES[stage]["label"]
    else:
        stage = "dragon" if level >= 10 else "baby" if level >= 5 else "egg"
        image_key = stage
        label = DRAGON_STAGES[stage]["label"]

    options = []
    for key, option in DRAGON_DESIGNS.items():
        options.append({
            "key": key,
            "label": option["label"],
            "image_url": static(f"assets/images/dragon/{option['image']}"),
            "price": option["price"],
            "locked": not option["free"] or level < 40,
            "required_level": 40,
            "selected": selected == key,
        })
    return {
        "level": level,
        "stage": stage,
        "stage_label": label,
        "image_key": image_key,
        "image_url": static(f"assets/images/dragon/{DRAGON_DESIGNS[image_key]['image'] if image_key in DRAGON_DESIGNS else DRAGON_STAGES[image_key]['image']}"),
        "selected_design": selected,
        "selection_available": level >= 40,
        "options": options,
        "stage_images": [
            {"key": key, "label": value["label"], "image_url": static(f"assets/images/dragon/{value['image']}"), "min_level": value["min_level"]}
            for key, value in DRAGON_STAGES.items()
        ],
    }
