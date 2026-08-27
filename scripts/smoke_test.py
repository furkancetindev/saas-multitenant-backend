"""
Smoke test: does the application actually work, and does the isolation hold
when a real request crosses a tenant boundary?

    python scripts/smoke_test.py                                # in-process, against .env's database
    python scripts/smoke_test.py https://your-app.onrender.com  # against a live deployment

This runs the scenario from the README's "Try it yourself" section and asserts
what that section claims — including the part nobody checks by eye: that the 404
another tenant gets for a real task is *byte-identical* to the 404 for an ID that
was never issued. Two 404s that differ by a single character are an existence
oracle, and reading them side by side in a terminal will not tell you.

`check_db_setup.py` verifies the database. This verifies the application sitting
on top of it — login, token issuing, and the per-request tenant context that
Row-Level Security depends on. A database can be configured perfectly while the
application forgets to say which tenant is asking, and only a real request
through the real stack shows that.

Needs the demo data: python scripts/seed_demo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TAMAM = "  [OK]   "
HATA = "  [FAIL] "
NOT = "  [ .. ] "

# Kaynak: scripts/seed_demo.py. Orada değişirse burada da değişmeli —
# ve testin ilk adımı zaten bunu yakalar (giriş başarısız olur).
PAROLA = "Parola123"
KUZEY_ADMIN = "admin@kuzey.example.com"
AY_ADMIN = "admin@ayyapi.example.com"
KUZEY_GOREV = "aaaa0000-0000-0000-0000-000000000001"

# Hiç var olmamış bir kimlik. Yabancı bir göreve verilen cevapla
# karşılaştırmak için gerekli — ikisi ayırt edilemez olmalı.
OLMAYAN_GOREV = "ffffffff-ffff-ffff-ffff-ffffffffffff"


def istemci_kur(hedef):
    """
    İki mod, tek arayüz: httpx.Client ve TestClient aynı çağrıları kabul eder.

    Canlı modda `main` import EDİLMEZ — bir dağıtımı sınamak için kimsenin
    yerelinde çalışan bir .env'e ihtiyacı olmamalı.
    """
    if hedef:
        import httpx

        # Render'ın ücretsiz katmanı uykudayken ilk istek ~1 dakika sürebilir.
        return httpx.Client(base_url=hedef.rstrip("/"), timeout=90.0, follow_redirects=True)

    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app)


def giris_yap(istemci, eposta, sonuc):
    cevap = istemci.post(
        "/api/v1/login", data={"username": eposta, "password": PAROLA}
    )
    if cevap.status_code == 429:
        print(
            f"{HATA}{eposta}: 429 — hız sınırına takıldı.\n"
            "         /login dakikada 5 denemeye izin veriyor. Bir dakika bekleyip tekrar çalıştır.\n"
            "         (Sınırın çalışıyor olması iyi haber, ama bu testi burada bitiriyor.)"
        )
        sonuc.append(False)
        return None
    if cevap.status_code != 200:
        print(f"{HATA}{eposta}: giriş başarısız ({cevap.status_code}) {cevap.text[:200]}")
        sonuc.append(False)
        return None
    token = cevap.json().get("access_token")
    if not token:
        print(f"{HATA}{eposta}: cevapta access_token yok")
        sonuc.append(False)
        return None
    print(f"{TAMAM}{eposta}: giriş başarılı, token alındı")
    sonuc.append(True)
    return {"Authorization": f"Bearer {token}"}


def main() -> int:
    hedef = sys.argv[1] if len(sys.argv) > 1 else None
    istemci = istemci_kur(hedef)
    sonuc = []

    print(f"\nHedef: {hedef or 'bellek içi uygulama (.env yapılandırması)'}")
    if hedef:
        print("Uyuyan bir servis ilk isteği ~1 dakikada cevaplayabilir, bekle.")

    print("\n=== 1. Servis ayakta mı ===")
    kok = istemci.get("/")
    if kok.status_code == 200:
        print(f"{TAMAM}GET / : 200")
        sonuc.append(True)
    else:
        print(f"{HATA}GET / : {kok.status_code}")
        sonuc.append(False)

    print("\n=== 2. Girişler ===")
    kuzey = giris_yap(istemci, KUZEY_ADMIN, sonuc)
    ay = giris_yap(istemci, AY_ADMIN, sonuc)
    if not kuzey or not ay:
        print("\nGiriş yapılamadı, izolasyon kontrolleri atlanıyor.")
        print("Demo verisi yüklü mü?  python scripts/seed_demo.py")
        return 1

    print("\n=== 3. Kendi görevine erişim ===")
    kendi = istemci.get(f"/api/v1/tasks/{KUZEY_GOREV}", headers=kuzey)
    if kendi.status_code == 200 and kendi.json().get("id") == KUZEY_GOREV:
        print(f"{TAMAM}Kuzey Lojistik kendi görevini görüyor: 200")
        sonuc.append(True)
    else:
        print(f"{HATA}Kuzey kendi görevini alamadı: {kendi.status_code} {kendi.text[:200]}")
        sonuc.append(False)

    print("\n=== 4. Yabancı göreve erişim ===")
    yabanci = istemci.get(f"/api/v1/tasks/{KUZEY_GOREV}", headers=ay)
    if yabanci.status_code == 404:
        print(f"{TAMAM}Ay Yapı, Kuzey'in görevini isteyince: 404 (403 değil)")
        sonuc.append(True)
    elif yabanci.status_code == 200:
        print(f"{HATA}SIZINTI: Ay Yapı, Kuzey Lojistik'in görevini okuyabildi.")
        sonuc.append(False)
    else:
        print(f"{HATA}Beklenen 404, gelen {yabanci.status_code}: {yabanci.text[:200]}")
        sonuc.append(False)

    print("\n=== 5. Yabancı görev ile olmayan görev ayırt edilebiliyor mu ===")
    # Bu testin sebebi: 404 dönmek yetmez. Yabancı bir kayda verilen cevap,
    # hiç var olmamış bir kayda verilen cevaptan farklıysa, aradaki fark
    # "bu kimlik gerçek" demektir — platformdaki her kimlik için sorgulanabilir.
    olmayan = istemci.get(f"/api/v1/tasks/{OLMAYAN_GOREV}", headers=ay)
    if (yabanci.status_code, yabanci.content) == (olmayan.status_code, olmayan.content):
        print(f"{TAMAM}İki cevap bayt bayt aynı — varlık sızıntısı yok")
        sonuc.append(True)
    else:
        print(
            f"{HATA}Cevaplar farklı:\n"
            f"           yabancı görev : {yabanci.status_code} {yabanci.content[:120]!r}\n"
            f"           olmayan görev : {olmayan.status_code} {olmayan.content[:120]!r}"
        )
        sonuc.append(False)

    print("\n=== 6. Listeler kesişiyor mu ===")
    kuzey_liste = istemci.get("/api/v1/tasks/", headers=kuzey)
    ay_liste = istemci.get("/api/v1/tasks/", headers=ay)
    if kuzey_liste.status_code != 200 or ay_liste.status_code != 200:
        print(f"{HATA}Liste alınamadı: {kuzey_liste.status_code} / {ay_liste.status_code}")
        sonuc.append(False)
    else:
        kuzey_idler = {g["id"] for g in kuzey_liste.json()}
        ay_idler = {g["id"] for g in ay_liste.json()}
        ortak = kuzey_idler & ay_idler
        if not kuzey_idler or not ay_idler:
            print(f"{HATA}Listelerden biri boş — demo verisi eksik olabilir")
            sonuc.append(False)
        elif ortak:
            print(f"{HATA}SIZINTI: {len(ortak)} görev iki kiracıda birden görünüyor: {sorted(ortak)}")
            sonuc.append(False)
        else:
            print(
                f"{TAMAM}Kuzey {len(kuzey_idler)} görev, Ay Yapı {len(ay_idler)} görev, "
                "kesişim yok"
            )
            sonuc.append(True)

    basarisiz = sonuc.count(False)
    print()
    if basarisiz:
        print(f"{basarisiz} kontrol başarısız.")
        return 1
    print(f"{len(sonuc)} kontrolün hepsi geçti. Uygulama çalışıyor, izolasyon ayakta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
