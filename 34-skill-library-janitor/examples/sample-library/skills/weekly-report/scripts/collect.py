import json


def collect(paths)
    out = []
    for path in paths:
        out.append(json.load(open(path)))
    return out
