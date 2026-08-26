from fastapi import Request
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address

from core.config import settings


def kimlik_bazli_anahtar(request: Request) -> str:
    """
    Hız sınırı (rate limit) anahtarını üretir.

    Kimlik doğrulanmış isteklerde anahtar, token'ın içindeki kullanıcı kimliğidir.
    Böylece aynı ofis/NAT IP'sinin arkasındaki iki farklı müşteri birbirinin
    kotasını yemez; tek bir kötü niyetli hesap da bütün bir IP'yi kilitleyemez.

    Token yoksa ya da geçersizse IP'ye düşeriz. `/login` ve `/tenants/register`
    kimlik bilinmeden çalışır — orada zaten IP'den başka tutamak yoktur.

    Neden kiracı değil de kullanıcı bazlı: JWT yalnızca `sub` (kullanıcı kimliği)
    taşır, `tenant_id` taşımaz. Kiracı bazlı anahtar için ya token'a bir kiracı
    claim'i eklemek ya da her istekte bir veritabanı sorgusu yapmak gerekirdi;
    ikincisi hız sınırının varlık sebebine aykırı. Bkz. README "Bilinen sınırlar".
    """
    auth_header = request.headers.get("Authorization", "")
    scheme, _, token = auth_header.partition(" ")

    if scheme.lower() == "bearer" and token:
        try:
            payload = jwt.decode(
                token, settings.secret_key, algorithms=[settings.algorithm]
            )
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except JWTError:
            # Süresi dolmuş / kurcalanmış token: kimliğe güvenmeyiz, IP'ye düşeriz.
            pass

    return get_remote_address(request)


limiter = Limiter(key_func=kimlik_bazli_anahtar)
