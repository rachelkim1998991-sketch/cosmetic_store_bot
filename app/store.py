"""Xotiradagi vaqtinchalik ma'lumotlar (bot qayta ishga tushsa tozalanadi)."""

# {telegram_user_id: {product_id: miqdor}}
carts: dict[int, dict[int, int]] = {}

# Savatda BELGILANMAGAN mahsulotlar: {telegram_user_id: {product_id, ...}}.
# Yangi qo'shilgan mahsulot odatda belgilangan bo'ladi.
unchecked: dict[int, set[int]] = {}

# Savat ko'rinishi uchun oxirgi olingan mahsulot ma'lumotlari (har belgilashda API'ga murojaat qilmaslik uchun)
cart_cache: dict[int, list[dict]] = {}

# {telegram_user_id: oxirgi qidiruv matni}: mahsulotdan "Orqaga" qaytish uchun
last_search: dict[int, str] = {}