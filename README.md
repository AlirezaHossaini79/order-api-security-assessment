# اصلاحات امنیتی API سفارش‌ها

شش مشکل امنیتی و پیکربندی در نسخهٔ اولیه رفع شده‌اند. بخش‌های زیر تغییر کد و روش بررسی هر مورد را نشان می‌دهند. دستورها برای Bash لینوکس هستند.

## محیط بررسی

روی سرور فعلی، برنامه از قبل اجرا شده است:

```bash
cd /root/direct/lab
PROJECT=lab
BASE=http://127.0.0.1:18080
```

راه‌اندازی در محیط خالی، با Docker Compose v2 و Python 3.10 یا بالاتر:

```bash
git clone https://github.com/AlirezaHossaini79/order-api-security-assessment.git
cd order-api-security-assessment/lab
PROJECT=hr-hosseini
BASE=http://127.0.0.1:18080
python3 tools/setup_secrets.py
docker compose -p "$PROJECT" up -d --build
python3 tools/smoke.py
```

## ۱. دسترسی به سفارش دیگران

**مشکل:** جست‌وجو فقط با شناسهٔ سفارش انجام می‌شد؛ آلیس می‌توانست سفارش باب را ببیند.

**تغییر در `lab/app/app.py`:**

```sql
-- قبل: فقط شناسه
WHERE id=%s

-- بعد: شناسه به همراه مالکیت یا مجوز ops
WHERE id=%s AND (owner=%s OR %s)
```

پارامترها به ترتیب شناسهٔ سفارش، نام کاربر و نتیجهٔ `actor == 'ops'` هستند. دسترسی غیرمجاز پاسخ `404` می‌گیرد.

**بررسی با یک سفارش تازهٔ باب:**

```bash
BOB_ID=$(curl -fsS "$BASE/orders" \
  -H 'Authorization: Bearer lab-bob' \
  -H 'Content-Type: application/json' \
  -d '{"item":"bob-private"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

curl -i "$BASE/orders/$BOB_ID" -H 'Authorization: Bearer lab-bob'
curl -i "$BASE/orders/$BOB_ID" -H 'Authorization: Bearer lab-alice'
curl -i "$BASE/orders/$BOB_ID" -H 'Authorization: Bearer lab-ops'
```

نتیجهٔ مورد انتظار: باب `200`، آلیس `404` و ops `200`.

## ۲. افشای رمز دیتابیس

**مشکل:** مسیر `/debug/config` بدون توکن، رشتهٔ اتصال شامل رمز دیتابیس را نمایش می‌داد.

**تغییر در `lab/app/app.py`:** مسیر به ops محدود و پاسخ حساس حذف شد.

```python
# قبل: نمایش رشتهٔ اتصال
{'database_url': DSN, 'mode': 'synthetic-lab'}

# بعد: فقط اطلاعات غیرحساس، حتی برای ops
{'mode': 'synthetic-lab'}
```

**بررسی:**

```bash
curl -i "$BASE/debug/config"
curl -i "$BASE/debug/config" -H 'Authorization: Bearer lab-alice'
curl -i "$BASE/debug/config" -H 'Authorization: Bearer lab-ops'
```

نتیجهٔ مورد انتظار: `401`، `403` و `200`. پاسخ آخر فقط شامل `mode` است.

## ۳. کنترل سرویس بدون مجوز

**مشکل:** مسیر `/lab/control` بدون مجوز امکان تغییر تأخیر و خطای مصنوعی را می‌داد.

**تغییر در `lab/app/app.py`:** کنترل نقش به مسیرهای مدیریتی اضافه شد:

```python
if actor != 'ops':                          # بررسی نقش
    return self.send(403, {'error': 'forbidden'})  # توقف دسترسی غیرمجاز
```

توکن غایب یا نامعتبر پیش از این مرحله `401` می‌گیرد. ورودی کنترل نیز اعتبارسنجی می‌شود؛ مثلاً تأخیر منفی پذیرفته نیست. ابزار `control.py` اکنون توکن ops می‌فرستد.

**بررسی بدون تغییر تنظیمات:**

```bash
curl -i "$BASE/lab/control" -H 'Content-Type: application/json' -d '{}'
curl -i "$BASE/lab/control" -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer lab-alice' -d '{}'
curl -i "$BASE/lab/control" -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer lab-ops' -d '{}'
```

نتیجهٔ مورد انتظار: `401`، `403` و `200`.

## ۴. افشای URL و رشد حافظه در پایش

**مشکل:** مسیر کامل و پارامترهای URL در لاگ و metrics عمومی ثبت می‌شدند. تمام زمان‌های پاسخ نیز در حافظه نگه‌داری می‌شدند.

**تغییر در `lab/app/app.py`:**

```python
path = urlsplit(self.path).path  # حذف query از مسیر
# شناسه‌های سفارش در آمار به الگوی ثابت /orders/:id تبدیل می‌شوند.
duration_sum += time.monotonic() - start  # نگه‌داری مجموع زمان
duration_count += 1                       # نگه‌داری تعداد، به‌جای فهرست زمان‌ها
```

دسترسی metrics نیز به ops محدود شده است.

**بررسی:**

```bash
curl -fsS "$BASE/live?probe=synthetic-query-marker"
curl -i "$BASE/metrics"
curl -fsS "$BASE/metrics" -H 'Authorization: Bearer lab-ops' \
  | grep -F 'synthetic-query-marker'
```

نتیجهٔ مورد انتظار: metrics بدون توکن `401` می‌گیرد؛ عبارت ساختگی در پاسخ مجاز دیده نمی‌شود. نبود خروجی `grep` در صورت موفقیت curl، نتیجهٔ درست است.

## ۵. رمز ثابت و دسترسی زیاد دیتابیس

**مشکل:** رمز در Compose نوشته شده بود و API با نقش راه‌انداز دیتابیس متصل می‌شد.

**تغییرات:**

- `setup_secrets.py`: ساخت دو رمز تصادفی مستقل، بدون بازنویسی فایل موجود.
- `compose.yaml`: تزریق رمز با فایل secret؛ API فقط رمز خودش را دریافت می‌کند.
- `app.py`: اتصال با نقش مستقل `lab_app`.
- `db/init.sh`: حذف قابلیت‌های مدیریتی و محدودسازی مجوزها:

```sql
REVOKE ALL ON orders FROM lab_app;          -- حذف مجوزهای مستقیم قبلی
GRANT SELECT, INSERT ON orders TO lab_app;  -- فقط خواندن و ثبت سفارش
```

مجوز استفاده از شمارندهٔ شناسه نیز برای ثبت سفارش حفظ شده است. در ارتقای محیط قبلی، رمز اولیهٔ مدیر تغییر می‌کند.

**بررسی نقش واقعی اتصال API، بدون نمایش رمز:**

```bash
docker compose -p "$PROJECT" exec -T api python -c \
  'import app; c=app.db(); print(c.execute("SELECT current_user").fetchone()[0]); c.close()'
```

نتیجهٔ مورد انتظار: `lab_app`.

## ۶. دسترسی غیرضروری کانتینر

**مشکل:** API با root و فایل‌سیستم قابل نوشتن اجرا می‌شد؛ این وضعیت اثر نفوذ احتمالی را افزایش می‌داد.

**تغییر در Dockerfile:**

```dockerfile
USER 10001:10001
```

پردازش با کاربر غیر root اجرا می‌شود. در Compose نیز فایل‌سیستم اصلی فقط‌خواندنی، قابلیت‌های اضافی حذف و افزایش امتیاز ممنوع شده است.

**بررسی:**

```bash
API_ID=$(docker compose -p "$PROJECT" ps -q api)
docker compose -p "$PROJECT" exec -T api id -u
docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$API_ID"
docker inspect --format '{{json .HostConfig.CapDrop}}' "$API_ID"
docker inspect --format '{{json .HostConfig.SecurityOpt}}' "$API_ID"
```

نتیجهٔ مورد انتظار: `10001`، سپس `true`، فهرست شامل `ALL` و فهرست شامل `no-new-privileges:true`.

## تست یکپارچه و شواهد

```bash
python3 tests/security_checks.py --url "$BASE" --expect fixed \
  --evidence ../evidence/local-security.json
python3 tools/runtime_checks.py --project "$PROJECT" \
  --evidence ../evidence/local-runtime.json
```

نتیجهٔ ثبت‌شده: **۳۵ تست امنیت و عملکرد و ۱۰ بررسی کانتینر و دیتابیس موفق**. خروجی‌های قبل و بعد در [evidence](evidence/) موجودند. توکن‌ها همچنان ثابت و مخصوص همین آزمایشگاه‌اند.
