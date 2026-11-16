# ارزیابی و اصلاح امنیت API سفارش‌ها

## معرفی پروژه

این مخزن شامل ارزیابی امنیتی و اصلاح یک API ثبت سفارش مبتنی بر Python و PostgreSQL است. ارزیابی نسخهٔ اولیه، ضعف در کنترل مالکیت سفارش، افشای اطلاعات اتصال دیتابیس و دسترسی غیرمجاز به مسیرهای مدیریتی را نشان داد. اصلاحات با حفظ قابلیت ثبت و مشاهدهٔ سفارش و همراه با تست‌های مثبت و منفی پیاده‌سازی شده‌اند.

Docker Compose دو سرویس `api` و `db` را اجرا می‌کند. رابط سرویس HTTP و قالب پاسخ‌ها JSON است. داده‌ها و اعتبارنامه‌های محیط آزمایشی ساختگی‌اند.

## کاربران و نقش‌ها

- **Alice — `lab-alice`:** ثبت سفارش و مشاهدهٔ سفارش‌های متعلق به خود.
- **Bob — `lab-bob`:** ثبت سفارش و مشاهدهٔ سفارش‌های متعلق به خود؛ بدون دسترسی به سفارش‌های Alice.
- **Ops — `lab-ops`:** مشاهدهٔ سفارش‌ها و دسترسی به مسیرهای کنترل، تنظیمات غیرحساس و پایش.

احراز هویت از طریق هدر `Authorization: Bearer TOKEN` انجام می‌شود و مجوز دسترسی مستقل از آن بررسی می‌شود. توکن غایب یا نامعتبر در مسیرهای حفاظت‌شده پاسخ `401` و نقش غیرمجاز در مسیرهای مدیریتی پاسخ `403` دریافت می‌کند. اطلاعات اتصال دیتابیس در هیچ پاسخ مجازی نمایش داده نمی‌شود.

## مسیرهای سرویس

- **`POST /orders`:** سفارش جدید می‌سازد؛ مالک از توکن مشخص می‌شود.
- **`GET /orders/ID`:** یک سفارش را می‌خواند؛ فقط مالک یا ops مجاز است.
- **`POST /lab/control`:** شبیه‌سازی تأخیر و خطای تجاری برای بررسی رفتار سرویس؛ محدود به نقش ops.
- **`GET /debug/config`:** اطلاعات تشخیصی تنظیمات را می‌دهد؛ در نسخهٔ اصلاح‌شده فقط برای ops و بدون رمز یا رشتهٔ اتصال است.
- **`GET /metrics`:** آمار درخواست‌ها و زمان پاسخ را برای ops نمایش می‌دهد.
- **`GET /live` و `GET /ready`:** سلامت برنامه و اتصال به دیتابیس را بررسی می‌کنند و عمداً عمومی‌اند.

یافته‌ها به‌ترتیب همراه با شدت، محل، پیش‌شرط، اثر، اصلاح و فرمان بررسی مستند شده‌اند. فرمان‌های اجرایی برای Bash لینوکس و قطعه‌های Python و SQL، نمونهٔ تغییرات کد هستند.

## مدل تهدید و محدوده

- **دارایی‌ها:** سفارش‌ها و مالکیت آن‌ها، رمز DB، تنظیمات کنترل سرویس و اطلاعات پایش.
- **مهاجم:** مراجعه‌کنندهٔ بدون توکن یا کاربر عادی که تلاش می‌کند اطلاعات کاربر دیگر یا بخش مدیریتی را ببیند.
- **مرزهای اعتماد:** کاربر به API، هویت استخراج‌شده از توکن به مجوز دسترسی، API به DB و کانتینر به میزبان.
- **محدوده:** فقط همین lab و داده‌های ساختگی؛ بدون DoS، حمله به میزبان یا دریافت دادهٔ واقعی. بررسی HTTP غیرمخرب بود و control با بدنهٔ خالی، وضعیت سرویس را تغییر نداد.

## اجرا از محیط پاک

پیش‌نیازها: Docker Compose v2، Python 3.10 یا بالاتر و دسترسی اینترنت برای دریافت image و dependency. اجرای سرویس و تست اولیه:

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

**اولویت ۱ ـ شدت بالا.** محل اولیه: `lab/app/app.py:78–84` در commit `56f5338`. پیش‌شرط: توکن یک کاربر عادی و شناسهٔ سفارش دیگری. اثر: افشای سفارش و مالک آن.

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

**اولویت ۱ ـ شدت بالا.** محل اولیه: `lab/app/app.py:56–57` در commit `56f5338`. پیش‌شرط: دسترسی HTTP؛ توکن لازم نبود. اثر: افشای اعتبارنامهٔ DB؛ استفاده از آن برای اتصال مستقیم به دسترسی شبکه نیز نیاز دارد.

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

**اولویت ۲ ـ شدت بالا.** محل اولیه: `lab/app/app.py:50–55` در commit `56f5338`. پیش‌شرط: دسترسی HTTP بدون توکن. اثر: تغییر غیرمجاز رفتار سرویس، تأخیر و خطای تجاری.

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

**اولویت ۳ ـ شدت متوسط.** محل اولیه: `lab/app/app.py:41–43,58–67` و تابع `log_message` در commit `56f5338`. پیش‌شرط افشا: وجود داده در URL و دسترسی به metrics عمومی. اثر: افشای query و افزایش مصرف حافظه با تنوع مسیرها. بررسی حافظه بر اساس ساختار کد انجام شده و شامل آزمون مختل‌کننده نبوده است.

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

**اولویت ۲ ـ شدت بالا، وابسته به دسترسی به سورس یا پردازش API.** محل اولیه: `lab/compose.yaml:6,18` و `lab/app/app.py:6,12` در commit `56f5338`. اثر: دسترسی به رمز و افزایش دامنهٔ خسارت در صورت نفوذ به API.

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

**تزریق secret:** فرمان `python3 tools/setup_secrets.py` فایل‌های `lab/secrets/db_admin_password` و `lab/secrets/db_app_password` را می‌سازد. Compose آن‌ها را در `/run/secrets/` به‌صورت فقط‌خواندنی mount می‌کند. DB رمز مدیر را از `POSTGRES_PASSWORD_FILE` و API رمز نقش محدود را از `DB_PASSWORD_FILE` می‌خواند. API رمز مدیر را دریافت نمی‌کند. این فایل‌ها در `.gitignore` هستند؛ Compose secrets محلی فایل‌محور است و ذخیره‌سازی رمزنگاری‌شده ایجاد نمی‌کند.

**بررسی نقش واقعی اتصال API، بدون نمایش رمز:**

```bash
docker compose -p "$PROJECT" exec -T api python -c \
  'import app; c=app.db(); print(c.execute("SELECT current_user").fetchone()[0]); c.close()'
```

نتیجهٔ مورد انتظار: `lab_app`.

## ۶. دسترسی غیرضروری کانتینر

**اولویت ۳ ـ شدت متوسط.** محل اولیه: `lab/app/Dockerfile` و بخش api در `lab/compose.yaml` در commit `56f5338`. پیش‌شرط سوءاستفاده: نفوذ به پردازش API. اثر: افزایش دامنهٔ دسترسی پردازش API در صورت نفوذ.

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

## شواهد اثبات و اجرای پاک

در [before.json](evidence/before.json)، درخواست پالایش‌شدهٔ آلیس به `GET /orders/5` پاسخ `200` با `owner: bob` گرفته است. درخواست بدون توکن به `GET /debug/config` نیز `200` با فیلد `database_url` داشته؛ مقدار آن پیش از ذخیره با `[REDACTED]` پوشانده شده است. شناسهٔ ۵ نتیجهٔ همان اجراست و در تست‌ها ثابت فرض نمی‌شود.

تست قابل اجرا در `lab/tests/security_checks.py` قرار دارد. حالت `--expect vulnerable` برای اثبات وضعیت اولیه در lab جداست؛ حالت `--expect fixed` روی نسخهٔ اصلاح‌شده، هم دسترسی مجاز و هم منع دسترسی را بررسی می‌کند. یافتهٔ metrics نیز با marker ساختگی در همین شواهد اثبات شده است. یافته‌های رمز و اجرای root از سورس اولیه مشخص‌اند؛ [runtime.json](evidence/runtime.json) مجوزهای واقعی پس از اصلاح را ثبت می‌کند. روش ارزیابی شامل بررسی سورس، تست HTTP و بررسی تنظیمات واقعی کانتینر و مجوزهای DB بوده است.

اجرای `python3 tools/verify_clean.py` نصب را با پروژه، volume و رمز تازه بررسی می‌کند. خروجی ثبت‌شده در [clean-run.log](evidence/clean-run.log)، [clean-security.json](evidence/clean-security.json) و [clean-runtime.json](evidence/clean-runtime.json) موجود است؛ تست‌های امنیت، عملکرد و مجوزها در آن محیط نیز موفق بوده‌اند.

## اصلاح انجام‌شده و ریسک باقی‌مانده

**رفع‌شده:** دسترسی بین کاربران، افشای DSN، کنترل بدون مجوز، ثبت query در پایش، رمز ثابت در تنظیمات جدید و دسترسی غیرضروری API به DB و محیط کانتینر. ثبت سفارش و دسترسی مالک و ops حفظ شده‌اند.

**ریسک پذیرفته‌شده در محیط آزمایشی:** توکن‌های ثابت فاقد انقضا و لغو هستند و افشای هر توکن امکان جعل هویت متناظر را ایجاد می‌کند. جداسازی سفارش‌ها در API اعمال می‌شود و RLS پیاده‌سازی نشده است. حفاظت از پردازش API همچنان برای محرمانگی داده‌های قابل خواندن توسط نقش برنامه ضروری است.

**الزامات محیط عملیاتی:** مدیریت هویت، توکن‌های دارای انقضا و امکان لغو، TLS و secret manager با چرخهٔ تعویض رمز. بررسی CVE و آزمون DoS در محدودهٔ این ارزیابی انجام نشده‌اند.
