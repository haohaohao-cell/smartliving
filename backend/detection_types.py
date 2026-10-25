PERSON_CLASS_ALIASES = {
    "0",
    "person",
    "human",
    "people",
    "pedestrian",
}


def normalize_class_name(class_name):
    if class_name is None:
        return ""
    return str(class_name).strip().lower().replace(" ", "_")


def is_person_class(class_name):
    return normalize_class_name(class_name) in PERSON_CLASS_ALIASES
