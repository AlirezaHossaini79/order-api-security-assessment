# بررسی و اصلاح امنیت API سفارش‌ها

این راهنما به ترتیب اجرا نوشته شده است: ابتدا برنامه را آماده کنید، سپس هر مشکل و تغییر کد را بخوانید و با دستور لینوکسی نتیجه را بررسی کنید. قطعه‌های Python، SQL و YAML برای توضیح تغییرات هستند؛ فقط دستورهای `bash` را در ترمینال اجرا کنید. توضیح زیر هر قطعه، خط‌به‌خطِ همان بخش تغییرکرده است.

## ۱. آماده‌سازی محیط بررسی

### اگر روی سرور فعلی هستید

داخل SSH، این دستورها را در یک ترمینال اجرا کنید. نام پروژهٔ فعلی `lab` است:

```bash
cd /root/direct/lab
PROJECT=lab
BASE=http://127.0.0.1:18080
python3 tools/smoke.py --url "$BASE"
```

انتظار: `PASS: live, ready, create, read`؛ یعنی برنامه و دیتابیس آماده‌اند و ثبت و خواندن سفارش کار می‌کند.

### اگر از محیط خالی شروع می‌کنید

Docker Compose v2 و Python 3.10 یا بالاتر باید نصب باشند. این مسیر را به‌جای دستورهای سرور فعلی اجرا کنید:

```bash
git clone https://github.com/AlirezaHossaini79/order-api-security-assessment.git
cd order-api-security-assessment/lab
PROJECT=hr-hosseini
BASE=http://127.0.0.1:18080
python3 tools/setup_secrets.py
docker compose -p "$PROJECT" up -d --build
python3 tools/smoke.py --url "$BASE"
```

متغیر `PROJECT` نام مجموعهٔ کانتینرها و `BASE` آدرس برنامه است. پورت `18080` روی میزبان به پورت `8080` داخل کانتینر وصل می‌شود؛ با وردپرس روی پورت `8080` میزبان تداخل ندارد. در ادامه همان ترمینال و همین متغیرها را نگه دارید.

## ۲. بررسی هویت و مجوز کاربران

در این تمرین، `lab-alice` توکن آلیس، `lab-bob` توکن باب و `lab-ops` توکن مسئول عملیات است. توکن فقط مشخص می‌کند کاربر کیست؛ مجوز هر مسیر و سفارش جدا بررسی می‌شود.

در [app.py](lab/app/app.py#L111-L118)، احراز هویت قبل از مسیرهای حفاظت‌شده قرار گرفته است:

```python
authorization = self.headers.get('Authorization', '')
actor = TOKENS.get(authorization[7:]) if authorization.startswith('Bearer ') else None
if not actor:
    return self.send(401, {'error': 'authentication required'})
```

1. خط اول هدر `Authorization` را می‌خواند؛ نبود هدر به رشتهٔ خالی تبدیل می‌شود.
2. خط دوم فقط قالب `Bearer TOKEN` را می‌پذیرد و توکن شناخته‌شده را به نام کاربر تبدیل می‌کند.
3. خط سوم بررسی می‌کند هویت معتبر پیدا شده است یا نه.
4. خط چهارم در صورت توکن غایب یا نامعتبر، پاسخ `401` می‌دهد و ادامهٔ درخواست را متوقف می‌کند.

مسیرهای سلامت `/live` و `/ready` عمداً عمومی‌اند. بخش‌های مدیریتی علاوه بر توکن، نقش `ops` می‌خواهند.

## ۳. مشکل اول: خواندن سفارش دیگران

**وضعیت اولیه:** آلیس با دانستن شناسهٔ سفارش باب، اطلاعات آن را دریافت می‌کرد؛ مالک سفارش در جست‌وجوی دیتابیس بررسی نمی‌شد.

**قبل:**

```sql
WHERE id=%s
```

**بعد؛ در [app.py](lab/app/app.py#L164-L177):**

```python
row = connection.execute(
    'SELECT id,owner,item,request_key FROM orders WHERE id=%s AND (owner=%s OR %s)',
    (order_id, actor, actor == 'ops')
).fetchone()
if not row:
    return self.send(404, {'error': 'missing'})
```

1. خط اول دستور جست‌وجو را اجرا می‌کند.
2. خط دوم علاوه بر شناسه، مالکیت یا مجوز نقش عملیاتی را شرط می‌کند.
3. خط سوم پارامترها را جدا از متن SQL می‌فرستد: شناسه، نام کاربر و نتیجهٔ بررسی `ops` بودن.
4. خط چهارم نتیجهٔ یک سفارش را دریافت می‌کند.
5. خط پنجم نبود نتیجهٔ مجاز را بررسی می‌کند.
6. خط آخر برای سفارش ناموجود یا غیرمجاز، `404` برمی‌گرداند؛ اطلاعات سفارش افشا نمی‌شود.

### بررسی روی لینوکس

ابتدا باب یک سفارش تازه می‌سازد و شناسه مستقیماً از پاسخ خوانده می‌شود:

```bash
BOB_RESPONSE=$(curl -fsS "$BASE/orders" \
  -H 'Authorization: Bearer lab-bob' \
  -H 'Content-Type: application/json' \
  -d '{"item":"bob-private-order"}') || exit 1
BOB_ID=$(printf '%s' "$BOB_RESPONSE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])') || exit 1
printf 'Bob order ID: %s\n' "$BOB_ID"
```

در دستور اول، `-H` هدرها و `-d` بدنهٔ JSON را می‌فرستد و پاسخ در `BOB_RESPONSE` ذخیره می‌شود. خط بعد با Python فقط `id` را از پاسخ می‌گیرد؛ بنابراین به شناسهٔ ثابت وابسته نیستیم. `curl -i` در دستورهای بعد، کد HTTP و بدنه را با هم نشان می‌دهد.

سپس همان سفارش را با سه نقش بخوانید:

```bash
curl -i "$BASE/orders/$BOB_ID" -H 'Authorization: Bearer lab-bob'
curl -i "$BASE/orders/$BOB_ID" -H 'Authorization: Bearer lab-alice'
curl -i "$BASE/orders/$BOB_ID" -H 'Authorization: Bearer lab-ops'
```

انتظار به ترتیب: **باب `200`، آلیس `404` و ops `200`**. پاسخ آلیس نباید `owner`، `item` یا اطلاعات سفارش باب را داشته باشد. جهت عکس، یعنی خواندن سفارش آلیس توسط باب، در تست خودکار هم بررسی می‌شود.

## ۴. مشکل دوم: افشای رمز و تنظیمات دیتابیس

**وضعیت اولیه:** `/debug/config` بدون توکن، DSN را برمی‌گرداند؛ DSN همان رشتهٔ اتصال شامل نام کاربری و رمز دیتابیس است.

**قبل:**

```python
self.send(200, {'database_url': DSN, 'mode': 'synthetic-lab'})
```

**بعد؛ در [app.py](lab/app/app.py#L116-L138):**

```python
if path in {'/lab/control', '/debug/config', '/metrics'}:
    if actor != 'ops':
        return self.send(403, {'error': 'forbidden'})
```

1. خط اول سه مسیر مدیریتی را مشخص می‌کند.
2. خط دوم نقش کاربر احراز هویت‌شده را بررسی می‌کند.
3. خط سوم کاربران غیر ops را با `403` متوقف می‌کند.

پاسخ مجاز config هم تغییر کرده است:

```python
if path == '/debug/config':
    return self.send(200, {'mode': 'synthetic-lab'})
```

1. خط اول مسیر تنظیمات را تشخیص می‌دهد.
2. خط دوم فقط مقدار بی‌خطر `mode` را برمی‌گرداند؛ حتی ops هم DSN یا رمز را دریافت نمی‌کند.

### بررسی روی لینوکس

```bash
curl -i "$BASE/debug/config"
curl -i "$BASE/debug/config" -H 'Authorization: Bearer lab-alice'
curl -i "$BASE/debug/config" -H 'Authorization: Bearer lab-ops'
```

انتظار به ترتیب: **`401`، `403` و `200`**. بدنهٔ پاسخ آخر فقط `{"mode": "synthetic-lab"}` است.

## ۵. مشکل سوم: کنترل سرویس بدون مجوز

**وضعیت اولیه:** هر فردی می‌توانست از `/lab/control` برای تغییر تأخیر و ایجاد خطای مصنوعی استفاده کند.

**تغییر:** همان کنترل نقشِ بخش قبل، مسیر کنترل را هم به ops محدود می‌کند. در [app.py](lab/app/app.py#L119-L134)، ورودی‌ها هم بررسی می‌شوند؛ برای نمونه:

```python
if 'delay_ms' in body and (type(body['delay_ms']) is not int or not 0 <= body['delay_ms'] <= 10000):
    raise ValueError('invalid delay')
```

1. خط اول فقط تأخیرِ عدد صحیح بین صفر و ۱۰٬۰۰۰ میلی‌ثانیه را می‌پذیرد؛ مقدار boolean هم به‌جای عدد پذیرفته نمی‌شود.
2. خط دوم ورودی نامعتبر را رد می‌کند؛ مدیریت خطای درخواست آن را به پاسخ `400` تبدیل می‌کند.

کلید ناشناخته، نوع نامعتبر `business_fail` و برچسب نامعتبر `release` نیز رد می‌شوند. در [control.py](lab/tools/control.py#L7-L13) ارسال هدر Bearer اضافه شده تا ابزار کنترل بعد از اصلاح همچنان کار کند.

### بررسی روی لینوکس

بدنهٔ خالی، هیچ تنظیمی را تغییر نمی‌دهد:

```bash
curl -i "$BASE/lab/control" -H 'Content-Type: application/json' -d '{}'
curl -i "$BASE/lab/control" -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer lab-alice' -d '{}'
curl -i "$BASE/lab/control" -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer lab-ops' -d '{}'
```

انتظار به ترتیب: **`401`، `403` و `200`**. اکنون ورودی نامعتبر را با نقش مجاز امتحان کنید:

```bash
curl -i "$BASE/lab/control" -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer lab-ops' -d '{"delay_ms":-1}'
```

انتظار: **`400`**؛ تأخیر فعلی تغییر نمی‌کند.

## ۶. مشکل چهارم: افشای URL و مصرف نامحدود حافظه در پایش

**وضعیت اولیه:** مسیر کامل درخواست و پارامترهای بعد از `?` در لاگ و metrics عمومی ثبت می‌شدند. مسیرهای متنوع و فهرست تمام زمان‌های پاسخ هم در حافظه باقی می‌ماندند.

**قبل:**

```python
counts[(self.path, str(status))] += 1
durations.append(time.monotonic() - start)
```

**بعد؛ در [app.py](lab/app/app.py#L42-L50):**

```python
path = urlsplit(self.path).path
if re.fullmatch(r'/orders/[0-9]+', path):
    return '/orders/:id'
return path if path in {'/orders', '/live', '/ready', '/metrics', '/debug/config', '/lab/control'} else '/unknown'
```

1. خط اول فقط بخش مسیر را می‌گیرد و query را کنار می‌گذارد.
2. خط دوم مسیر سفارش با شناسهٔ عددی را تشخیص می‌دهد.
3. خط سوم همهٔ شناسه‌ها را به یک نام ثابت تبدیل می‌کند.
4. خط آخر فقط مسیرهای مشخص را نگه می‌دارد؛ بقیه یک برچسب مشترک دارند و شمارندهٔ نامحدود ایجاد نمی‌کنند.

همین تابع برای لاگ و metrics استفاده می‌شود. ثبت زمان در [خطوط ۹۴ تا ۹۶](lab/app/app.py#L94-L96) هم تغییر کرده است:

```python
counts[(self.route_label(), str(status))] += 1
duration_sum += time.monotonic() - start
duration_count += 1
```

1. خط اول تعداد درخواست‌ها را با برچسب ثابت ثبت می‌کند.
2. خط دوم فقط مجموع زمان‌ها را افزایش می‌دهد.
3. خط سوم فقط تعداد پاسخ‌ها را افزایش می‌دهد؛ دیگر فهرست تمام زمان‌ها نگه‌داری نمی‌شود.

### بررسی روی لینوکس

```bash
curl -fsS "$BASE/live?probe=synthetic-query-marker"
curl -i "$BASE/metrics"
METRICS=$(curl -fsS "$BASE/metrics" -H 'Authorization: Bearer lab-ops') || exit 1
if printf '%s\n' "$METRICS" | grep -Fq 'synthetic-query-marker'; then
  printf 'FAIL: query data is visible\n'
else
  printf 'PASS: query data is absent\n'
fi
```

انتظار: health check موفق، درخواست metrics بدون توکن **`401`** و بررسی آخر **`PASS`**. برای بررسی لاگ هم:

```bash
docker compose -p "$PROJECT" logs --since 2m api | grep -F 'synthetic-query-marker'
```

نباید خروجی داشته باشد. نبود تطابق باعث خروج با کد ۱ توسط `grep` می‌شود و در این بررسی طبیعی است.

## ۷. مشکل پنجم: رمز ثابت و دسترسی زیاد دیتابیس

**وضعیت اولیه:** رمز داخل Compose نوشته شده بود و API با نقش راه‌انداز دیتابیس متصل می‌شد.

**تغییر اول؛ در [compose.yaml](lab/compose.yaml#L23-L29):**

```yaml
DB_USER: lab_app
DB_PASSWORD_FILE: /run/secrets/db_app_password
```

1. خط اول، نقش مستقل و محدود API را انتخاب می‌کند.
2. خط دوم فقط مسیر فایل رمز را به API می‌دهد؛ مقدار رمز داخل متغیر محیطی قرار نمی‌گیرد. بخش `secrets` فایل را فقط‌خواندنی به کانتینر می‌رساند.

در [app.py](lab/app/app.py#L15)، رمز از همان فایل خوانده می‌شود:

```python
DB_PASSWORD = Path(os.environ.get('DB_PASSWORD_FILE', '/run/secrets/db_app_password')).read_text().strip()
```

این خط مسیر فایل را از تنظیمات می‌گیرد، محتوای آن را می‌خواند و فاصله یا پایان‌خط اضافه را حذف می‌کند. پاسخ API شامل این مقدار نیست.

**تغییر دوم؛ در [init.sh](lab/db/init.sh#L8-L14):**

```sql
ALTER ROLE lab_app NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO lab_app;
```

1. خط اول قابلیت‌های مدیریتی و عبور از RLS را از نقش برنامه می‌گیرد.
2. خط دوم امکان ساخت اشیا در schema عمومی از طریق نقش PUBLIC را حذف می‌کند.
3. خط سوم اجازهٔ استفاده از schema موجود را می‌دهد؛ اجازهٔ ساخت جدول جدید نیست.

مجوز جدول هم در [خطوط ۲۵ تا ۲۷](lab/db/init.sh#L25-L27) محدود شده است:

```sql
REVOKE ALL ON orders FROM lab_app;
GRANT SELECT, INSERT ON orders TO lab_app;
GRANT USAGE, SELECT ON SEQUENCE orders_id_seq TO lab_app;
```

1. خط اول مجوزهای مستقیم قبلیِ نقش برنامه روی جدول را پاک می‌کند.
2. خط دوم فقط خواندن و ثبت سفارش را مجاز می‌کند؛ UPDATE و DELETE داده نمی‌شوند.
3. خط سوم استفاده از شمارندهٔ شناسه را برای ثبت سفارش ممکن می‌کند.

[setup_secrets.py](lab/tools/setup_secrets.py) دو رمز تصادفی مستقل می‌سازد و فایل موجود را بازنویسی نمی‌کند. در ارتقای محیط قبلی، [init.sh](lab/db/init.sh#L7) رمز اولیهٔ مدیر را هم تغییر می‌دهد. شبکهٔ DB در [Compose](lab/compose.yaml#L48-L51) داخلی است و پورت دیتابیس روی میزبان منتشر نشده است.

### بررسی روی لینوکس

فقط نام و دسترسی فایل‌ها را ببینید؛ محتوای رمز را چاپ نکنید:

```bash
ls -ld secrets
ls -l secrets
```

انتظار روی لینوکس: پوشه با دسترسی `0700` و دو فایل رمز مستقل. فایل‌ها `0644` هستند تا کاربر کانتینر بتواند mount را بخواند؛ ورود به پوشهٔ میزبان محدود است.

نقش واقعی اتصال API را بررسی کنید:

```bash
docker compose -p "$PROJECT" exec -T api python -c \
  'import app; c=app.db(); print(c.execute("SELECT current_user").fetchone()[0]); c.close()'
```

انتظار: **`lab_app`**. بررسی کامل نبود مجوز مدیریتی و محدودبودن مجوز جدول، در مرحلهٔ ۹ اجرا می‌شود.

## ۸. مشکل ششم: سطح دسترسی غیرضروری کانتینر

**وضعیت اولیه:** API با root و فایل‌سیستم قابل نوشتن اجرا می‌شد؛ این وضعیت اثر نفوذ احتمالی را بیشتر می‌کند.

**تغییر در [Dockerfile](lab/app/Dockerfile#L7):**

```dockerfile
USER 10001:10001
```

این خط اجرای پردازش API را به UID و GID غیر root تغییر می‌دهد.

**تغییر در [compose.yaml](lab/compose.yaml#L35-L42):**

```yaml
read_only: true
tmpfs:
  - /tmp:size=16m,noexec,nosuid
cap_drop:
  - ALL
security_opt:
  - no-new-privileges:true
pids_limit: 128
```

1. `read_only` فایل‌سیستم اصلی کانتینر را فقط‌خواندنی می‌کند.
2. `tmpfs` یک فضای موقت در حافظه تعریف می‌کند.
3. خط `/tmp` حجم آن را به ۱۶ مگابایت محدود و اجرای مستقیم فایل و اثر بیت setuid را غیرفعال می‌کند.
4. `cap_drop` فهرست قابلیت‌های حذف‌شونده را مشخص می‌کند.
5. مقدار `ALL` همهٔ قابلیت‌های اضافی لینوکس را حذف می‌کند.
6. `security_opt` تنظیمات امنیتی پردازش را تعریف می‌کند.
7. `no-new-privileges` مانع افزایش امتیاز از طریق اجرای برنامهٔ دیگر می‌شود.
8. `pids_limit` تعداد taskها، شامل threadها، را محدود می‌کند.

### بررسی روی لینوکس

```bash
API_ID=$(docker compose -p "$PROJECT" ps -q api)
docker compose -p "$PROJECT" exec -T api id -u
docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$API_ID"
docker inspect --format '{{json .HostConfig.CapDrop}}' "$API_ID"
docker inspect --format '{{json .HostConfig.SecurityOpt}}' "$API_ID"
```

انتظار به ترتیب: **`10001`، `true`، فهرست شامل `ALL` و فهرست شامل `no-new-privileges:true`**.

## ۹. اجرای یک‌جای بررسی‌ها و مشاهدهٔ شواهد

به‌جای تکرار دستی همهٔ حالت‌ها، این دو دستور را از همان پوشهٔ `lab` اجرا کنید:

```bash
python3 tests/security_checks.py --url "$BASE" --expect fixed \
  --evidence ../evidence/local-security.json
python3 tools/runtime_checks.py --project "$PROJECT" \
  --evidence ../evidence/local-runtime.json
```

دستور اول **۳۵ تست** دارد: مالک، کاربر دیگر، ops، توکن غایب و نامعتبر، کنترل سرویس، تنظیمات، metrics و معتبرماندن عملکرد سفارش. انتظار: **`35/35 checks passed`**.

دستور دوم **۱۰ بررسی واقعی** روی کانتینر و مجوزهای DB انجام می‌دهد. انتظار: **۱۰ پیام PASS**. خروجی هر بررسی همراه زمان و فرمان اجرا در فایل JSON ذخیره می‌شود.

برای بررسی نصب از صفر با دیتابیس و رمز تازه:

```bash
python3 tools/verify_clean.py
```

این دستور پروژهٔ موقت جدا می‌سازد و فقط منابع همان پروژه را در پایان پاک می‌کند. دادهٔ محیط اصلی حذف نمی‌شود. نتایج قبلی در [evidence](evidence/) موجودند؛ `before.json` بازتولید وضعیت اولیه و `after.json` و `runtime.json` نتیجهٔ پس از اصلاح‌اند. در نصب تازه نیز تست‌ها موفق و ۱۰۰ درخواست نمونه از ۱۰۰ درخواست موفق بوده‌اند.

## ۱۰. تغییرات تکمیلی و مشاهدهٔ تفاوت فایل‌ها

علاوه بر شش مورد بالا، این تغییرات در [app.py](lab/app/app.py) اعمال شده‌اند:

- بدنهٔ درخواست باید JSON object و حداکثر ۱۶ کیلوبایت باشد؛ `item` باید متن غیرخالی و حداکثر ۱۰۰۰ کاراکتر باشد.
- روش HTTP مسیرها بررسی می‌شود؛ روش نامناسب پاسخ `405` می‌گیرد.
- خطاهای داخلی و DB با پیام عمومی پاسخ داده می‌شوند؛ متن حساس خطا به کاربر برنمی‌گردد.
- هدرهای `Cache-Control: no-store` و `X-Content-Type-Options: nosniff` به پاسخ‌ها اضافه شده‌اند.
- ساخت schema از پردازش API به اسکریپت راه‌اندازی DB منتقل شده و ابزارهای کنترل و smoke با تنظیمات جدید سازگار شده‌اند.

برای دیدن تفاوت سورس اولیه و اصلاحات، از پوشهٔ `lab` اجرا کنید:

```bash
git diff 56f5338 229e75a -- app/app.py compose.yaml app/Dockerfile db/init.sh tools/
```

`56f5338` نسخهٔ اولیه و `229e75a` اصلاحات امنیتی است. این دستور فقط تفاوت‌ها را نمایش می‌دهد و نسخهٔ در حال اجرا را تغییر نمی‌دهد.

برای توقف محیطی که خودتان ساخته‌اید، بدون حذف سفارش‌ها:

```bash
docker compose -p "$PROJECT" down
```

توکن‌ها همچنان ساختگی و ثابت‌اند؛ این تمرین جایگزین احراز هویت production و TLS نیست. جداسازی مالکیت در API انجام می‌شود و RLS به DB اضافه نشده است.
