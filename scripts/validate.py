#!/usr/bin/env python3
"""Проверка geo-баз и профилей Happ перед публикацией. Выходит с кодом 1, если что-то не так.

  python3 scripts/validate.py [каталог_с_прежними_базами]

Проверяет: базы читаются; все теги из HAPP/*.JSON есть в базах; размер в пределах лимита памяти туннеля;
число записей в теге не упало больше чем на 30% по сравнению с прежней базой (если каталог указан)."""
import glob
import json
import os
import sys

MAX_BYTES = {"geoip.dat": 500_000, "geosite.dat": 200_000}
MAX_DROP = 0.30


def _varint(b, i):
    r = s = 0
    while True:
        x = b[i]
        i += 1
        r |= (x & 0x7F) << s
        s += 7
        if x < 128:
            return r, i


def _fields(b):
    i = 0
    while i < len(b):
        k, i = _varint(b, i)
        w = k & 7
        if w == 0:
            v, i = _varint(b, i)
        elif w == 2:
            n, i = _varint(b, i)
            if i + n > len(b):
                raise ValueError("обрезанный файл")
            v, i = b[i:i + n], i + n
        else:
            raise ValueError(f"неизвестный тип поля {w}")
        yield k >> 3, v


def load(path):
    """{ТЕГ: число записей}."""
    out = {}
    for f, v in _fields(open(path, "rb").read()):
        if f != 1:
            continue
        code, n = None, 0
        for ff, vv in _fields(v):
            if ff == 1:
                code = vv.decode().lower()
            elif ff == 2:
                n += 1
        if not code:
            raise ValueError("запись без кода")
        out[code] = n
    return out


def main(prev_dir=None):
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
    errors, bases = [], {}
    for name, limit in MAX_BYTES.items():
        path = os.path.join(root, "geo", name)
        size = os.path.getsize(path)
        if not 20_000 < size < limit:
            errors.append(f"{name}: размер {size} вне 20000..{limit}")
        try:
            bases[name] = load(path)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name}: не читается ({e})")
            continue
        if prev_dir and os.path.exists(os.path.join(prev_dir, name)):
            try:
                old = load(os.path.join(prev_dir, name))
            except Exception:  # noqa: BLE001
                old = {}
            for tag, n in old.items():
                new = bases[name].get(tag, 0)
                if n and new < n * (1 - MAX_DROP):
                    errors.append(f"{name}: тег {tag} уменьшился {n} → {new}")
    for prof in sorted(glob.glob(os.path.join(root, "HAPP", "*.JSON"))):
        d = json.load(open(prof, encoding="utf-8"))
        for key, base in (("DirectSites", "geosite.dat"), ("ProxySites", "geosite.dat"), ("BlockSites", "geosite.dat"),
                          ("DirectIp", "geoip.dat"), ("ProxyIp", "geoip.dat"), ("BlockIp", "geoip.dat")):
            for item in d.get(key, []):
                if not item.lower().startswith(("geosite:", "geoip:")):
                    continue  # домены и CIDR вписаны напрямую
                tag = item.split(":", 1)[1].lower()
                if base in bases and tag not in bases[base]:
                    errors.append(f"{os.path.basename(prof)}: {item} нет в {base}")
    for e in errors:
        print("ОШИБКА:", e)
    if not errors:
        print("OK:", {k: len(v) for k, v in bases.items()}, "тегов")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
