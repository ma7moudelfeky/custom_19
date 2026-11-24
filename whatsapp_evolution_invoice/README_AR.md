# واتساب مجاني لـ Odoo 19 عبر Evolution API

## المحتويات
```
evolution-api/            ← ستاك Evolution API (API + Postgres + Redis)
whatsapp_evolution_invoice/ ← موديول واحد فيه كل حاجة: الإعدادات، القوالب، الإرسال الجماعي،
                              الفواتير، CRM، وتنبيه انتهاء مستندات العملاء
odoo-docker-compose.yml   ← ملف الكومبوز الخاص بك بعد إضافة الشبكة
```
بيعتمد على: account, crm, firm_customize, customer_extra_fields (كلهم متثبتين عندك).

---

## 1) تشغيل Evolution API
```bash
cd /opt/evolution-api
bash setup.sh odoo        # يطبع الـ API Key — احتفظ به
```

## 2) ربط Odoo بنفس الشبكة
استبدل docker-compose.yml بتاع Odoo بـ `odoo-docker-compose.yml` ثم:
```bash
docker compose up -d odoo
docker compose exec odoo curl -s http://evolution_api:8080/   # لازم يرد
```

## 3) تثبيت الموديولات
انسخ فولدر `whatsapp_evolution_invoice` لنفس فولدر الـ docker-compose.yml (هو الـ addons path عندك)، ثم:
```bash
docker compose restart odoo
```
Apps → Update Apps List → ثبّت **WhatsApp Evolution (Invoices, CRM, Documents)**.

## 4) الإعدادات
**WhatsApp → Settings**: URL = `http://evolution_api:8080`، API Key، Instance = `odoo`، Delay 8–20 ثانية، ثم **Test Connection**.

## 5) مسح الـ QR (مرة واحدة)
من الكونسول بتاع السيرفر:
```bash
apt install -y qrencode jq
cd /opt/evolution-api
KEY=$(grep '^AUTHENTICATION_API_KEY=' .env | cut -d= -f2)
curl -s http://127.0.0.1:8080/instance/connect/odoo -H "apikey: $KEY" | jq -r .code | qrencode -t ansiutf8
```
واتساب ← الأجهزة المرتبطة ← ربط جهاز ← امسح.

---

## الاستخدام

### أ) تنبيه انتهاء المستندات (Documents / Alerts)
- **تلقائي**: كل ساعة يتم فحص المستندات؛ لو `تاريخ الانتهاء − Alert Days ≤ النهارده` (والمستند لسه ما انتهاش وحالته مش Not Active) تتبعت رسالة لكل يوزر في **Alert Users** على موبايله.
- مرة واحدة لكل مستند لكل تاريخ انتهاء — لو جددت المستند وغيرت التاريخ، التنبيه يشتغل تاني.
- **يدوي**: زرار **WhatsApp** جنب "Action Send Activity" في تاب Documents / Alerts بالعميل، وزرار في فورم المستند.
- رقم اليوزر بيتقرأ من موبايل الموظف (Employee) أو Phone بتاع اليوزر.
- الرسالة: العميل، نوع المستند، رقم المستند، تاريخ الانتهاء — تقدر تعدلها من **WhatsApp → Templates → Document expiry alert**.

### ب) CRM — إرسال جماعي
1. CRM ← اختار مجموعة Leads/فرص ← **Actions ⚙ → Send WhatsApp**.
2. تظهر شاشة: اختار قالب أو اكتب النص، وأضف مرفقات (اختياري).
3. **Send All WhatsApp** ← الرسائل تدخل الطابور وتتبعت بفاصل عشوائي.
- النص يقبل متغيرات: `{{ object.contact_name }}`، `{{ object.name }}`، `{{ object.partner_id.name }}`.
- نفس زرار Send WhatsApp موجود في العملاء والفواتير والمستندات.

### ج) CRM — تلقائي
من **WhatsApp → Templates** افتح قالب CRM واختار **When**:
| الخيار | يعمل إيه |
|---|---|
| **When the lead reaches a stage** | أول ما الفرصة توصل للمرحلة المحددة تتبعت الرسالة (مرة واحدة لكل فرصة لكل مرحلة) |
| **Scheduled (every hour, by filter)** | كل ساعة: أي فرصة تطابق الفلتر (مثلاً المرحلة = New) ولسه ما استلمتش الرسالة دي تتبعتلها |
| **Manual only** | يظهر بس في شاشة الإرسال الجماعي |

### القوالب — ليه قالب واحد لكل حاجة
كل قالب مربوط بـ Model (فواتير / CRM / مستندات / عملاء) وفيه: النص، المرفقات الثابتة، تقرير PDF، المستلم (العميل / يوزرز من حقل / أرقام ثابتة)، والتشغيل (يدوي / مرحلة / كل ساعة / انتهاء مستند). اعمل أكتر من قالب لنفس الـ Model براحتك.

### المتابعة
**WhatsApp → Messages**: كل رسالة وحالتها (Pending / Sent / Failed) والسبب، مع Retry / Cancel / Send Now، وكل إرسال بيتسجل في Chatter السجل.

---

## ⚠️ مشكلتين في كود firm_customize الحالي (custom_19)
في `firm_customize/models/firm_contract.py`:
1. **`action_schedule_document`** الشرط `last_update_date + alert_days >= today` بيطلع True لكل مستند لسه ما انتهاش ⇒ الكرون اليومي بيعمل Activities لكل المستندات كل يوم. الصح:
   ```python
   if record.last_update_date - timedelta(days=record.alert_days) <= today <= record.last_update_date:
   ```
2. **`action_send_activity`**: `'Renew Document For ' + rec.partner_id.name` بيضرب TypeError لو المستند مالوش عميل (فيه مستند كده فعلاً في الداتابيز). الصح: `(rec.partner_id.name or '')`.

موديول الواتساب مش معتمد على الكود ده — بيستخدم منطقه الخاص الصحيح.

## تحذيرات
- Evolution API **غير رسمي**؛ الرقم ممكن يتحظر. استخدم رقم مخصص للشركة وابدأ بأعداد قليلة — خصوصاً مع الإرسال الجماعي لـ CRM.
- جرّب على نسخة من الداتابيز الأول: قالب الفواتير مفعّل تلقائياً عند التأكيد (اقفله من Templates لو مش عايزه).
