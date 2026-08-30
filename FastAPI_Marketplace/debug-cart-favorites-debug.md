# debug-cart-favorites-debug.md

**Session ID:** `cart-favorites-debug`  
**Status:** [OPEN]  
**Created:** 2026-08-29  
**Goal:** Діагностика та виправлення функціоналу Кошика (Cart) та Обраного (Favorites): авторизація (401), JS fetch headers/credentials, toggle-logic в Favorites, increment quantity в Cart, оновлення UI badgeів, Toast-сповіщення, try/catch в JS.

---

## Гіпотези (фальсифіковані)

1. **H1 — Відсутня кнопка "В кошик" у картках товарів**  
   В catalog.html присутня лише кнопка «Додати в обране» / «Переглянути», але немає явної кнопки «В кошик» з `data-product-id`, тому `add-to-cart` не працює взагалі.

2. **H2 — JS fetch-запити favorites/cart не передають cookies авторизації або Content-Type**  
   Обробники `bindFavoriteClickHandlers` можуть не передавати:
   - `credentials: 'same-origin'` або `'include'`  
   - `headers: { 'Content-Type': 'application/json' }`  
   Із-за цього бекенд відхиляє запити (401 або 400) або не парсить тіло, і UI не оновлюється (silent failure без try/catch).

3. **H3 — Неактивний/неіснуючий синхронізатор UI (badge + favorite-active)**  
   Після натискання кнопки Обране не перемикається клас `favorite-active`, не оновлюється `#fav-count`, не показується Toast. Аналогічно для Кошика: після успішного додавання в /cart не оновлюється `#cart-count` і немає Toast.

4. **H4 — Бекенд Favorites / Cart не повертає 401 з коректним `detail` для guest**  
   Якщо `get_current_user` використовує `HTTPBearer`/header, а токен лежить тільки в cookie `access_token` — запит без явного Authorization-заголовка *повертає 401 але без redirect, і фронтенд не знає, що треба запропонувати вхід*.

5. **H5 — Не передбачено обробку неавторизованого сценарію та alert/toast помилок**  
   Фетч-запити не обгорнуті в повний try/catch, який би при 401 показав alert з пропозицією увійти, при 400/500 показав відповідне повідомлення (а не silent).

---

## План

1. **Інструментація** — додати debug-point логування в:
   - [routers/favorites.py `toggle_favorite`](file:///c:/Users/Admin/Desktop/FastAPI_Marketplace/routers/favorites.py#L83-L100)
   - [routers/cart.py `add_to_cart`](file:///c:/Users/Admin/Desktop/FastAPI_Marketplace/routers/cart.py#L106-L130)
   - [dependencies.py `get_current_user`](file:///c:/Users/Admin/Desktop/FastAPI_Marketplace/dependencies.py#L37-L64)
   - [templates/catalog.html `bindFavoriteClickHandlers`, `syncFavoriteButtons`](file:///c:/Users/Admin/Desktop/FastAPI_Marketplace/templates/catalog.html)
   - [Templates/base.html `updateCartCount`, `updateFavoritesCount` + нові addToCart JS](file:///c:/Users/Admin/Desktop/FastAPI_Marketplace/Templates/base.html)

2. **Запуск Debug Server**, відтворення сценаріїв.
3. **Аналіз логів** — підтвердження гіпотез.
4. **Виправлення бекенду + фронтенду (H1..H5)**.
5. **Переперевірка** (post-fix logs).
6. **Cleanup (тільки після підтвердження)**.
