def normalize_jurisdiction(j):
    if not j:
        return "India"   # system-wide legal default
    return j.strip().title()
