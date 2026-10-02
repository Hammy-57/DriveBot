"""
Site translations (admin panel + instructor page). To add a language: add its code
to LANGS and one more entry to every tuple in _T (order: en, it, fr, es, ar).
Student WhatsApp messages are separate (bot_logic.py: Italian and English).
"""
from contextvars import ContextVar

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

LANGS = {"en": "English", "it": "Italiano", "fr": "Français", "es": "Español", "ar": "العربية"}
RTL = {"ar"}
_ORDER = ("en", "it", "fr", "es", "ar")

current: ContextVar[str] = ContextVar("lang", default="en")
current_path: ContextVar[str] = ContextVar("path", default="/")

_T = {
 "language": ("Language", "Lingua", "Langue", "Idioma", "اللغة"),
 "theme": ("Light / dark mode", "Tema chiaro / scuro", "Mode clair / sombre", "Modo claro / oscuro", "الوضع الفاتح / الداكن"),
 "copy": ("Copy", "Copia", "Copier", "Copiar", "نسخ"),
 "copied": ("Copied", "Copiato", "Copié", "Copiado", "تم النسخ"),
 "confirm": ("Are you sure?", "Sei sicuro?", "Êtes-vous sûr ?", "¿Estás seguro?", "هل أنت متأكد؟"),
 "not_set": ("not set", "non impostato", "non défini", "no configurado", "غير مُعيَّن"),
 "back": ("← Back", "← Indietro", "← Retour", "← Volver", "→ رجوع"),
 "back_instructors": ("← All instructors", "← Tutti gli istruttori", "← Tous les moniteurs", "← Todos los instructores", "→ كل المدربين"),
 "admin_title": ("DriveBot Admin", "Admin DriveBot", "Admin DriveBot", "Admin DriveBot", "إدارة DriveBot"),
 "admin_sub": ("Manage instructors, students and lessons.", "Gestisci istruttori, allievi e lezioni.", "Gérez les moniteurs, les élèves et les leçons.", "Gestiona instructores, alumnos y clases.", "إدارة المدربين والطلاب والدروس."),
 "instructors": ("Instructors", "Istruttori", "Moniteurs", "Instructores", "المدربون"),
 "name": ("Name", "Nome", "Nom", "Nombre", "الاسم"),
 "phone": ("Phone", "Telefono", "Téléphone", "Teléfono", "الهاتف"),
 "open": ("Open", "Apri", "Ouvrir", "Abrir", "فتح"),
 "no_instructors": ("No instructors yet. Add one below.", "Nessun istruttore. Aggiungine uno qui sotto.", "Aucun moniteur pour l'instant. Ajoutez-en un ci-dessous.", "Aún no hay instructores. Añade uno abajo.", "لا يوجد مدربون بعد. أضف مدرباً أدناه."),
 "add_instructor": ("Add instructor", "Aggiungi istruttore", "Ajouter un moniteur", "Añadir instructor", "إضافة مدرب"),
 "wa_phone_cc": ("WhatsApp phone (with country code)", "Telefono WhatsApp (con prefisso)", "Téléphone WhatsApp (avec indicatif)", "Teléfono de WhatsApp (con prefijo)", "هاتف واتساب (مع رمز الدولة)"),
 "setup": ("Setup", "Configurazione", "Configuration", "Configuración", "الإعداد"),
 "system_check": ("System check", "Controllo sistema", "Vérification du système", "Verificación del sistema", "فحص النظام"),
 "twilio_loaded": ("Twilio credentials loaded", "Credenziali Twilio caricate", "Identifiants Twilio chargés", "Credenciales de Twilio cargadas", "تم تحميل بيانات Twilio"),
 "wa_sender": ("WhatsApp sender", "Mittente WhatsApp", "Expéditeur WhatsApp", "Remitente de WhatsApp", "مُرسِل واتساب"),
 "sandbox_mode": ("Sandbox demo mode", "Modalità demo Sandbox", "Mode démo Sandbox", "Modo demo Sandbox", "وضع التجربة Sandbox"),
 "sandbox_hint": ("on = demo only, off = production", "attivo = solo demo, spento = produzione", "activé = démo seulement, désactivé = production", "activado = solo demo, desactivado = producción", "مفعّل = للتجربة فقط، متوقف = للإنتاج"),
 "templates_set": ("Approved template IDs", "ID dei template approvati", "ID des modèles approuvés", "ID de plantillas aprobadas", "معرّفات القوالب المعتمدة"),
 "yes": ("yes", "sì", "oui", "sí", "نعم"),
 "no": ("NO", "NO", "NON", "NO", "لا"),
 "send_test_label": ("Send a test WhatsApp message to (with country code)", "Invia un messaggio WhatsApp di prova a (con prefisso)", "Envoyer un message WhatsApp de test à (avec indicatif)", "Enviar un mensaje de prueba de WhatsApp a (con prefijo)", "إرسال رسالة واتساب تجريبية إلى (مع رمز الدولة)"),
 "send_test": ("Send test", "Invia prova", "Envoyer le test", "Enviar prueba", "إرسال تجربة"),
 "last_problem": ("Last WhatsApp sending problem", "Ultimo problema di invio WhatsApp", "Dernier problème d'envoi WhatsApp", "Último problema de envío de WhatsApp", "آخر مشكلة في إرسال واتساب"),
 "private_page": ("Private page for this instructor", "Pagina privata di questo istruttore", "Page privée de ce moniteur", "Página privada de este instructor", "الصفحة الخاصة بهذا المدرب"),
 "private_hint": ("Send him this link on WhatsApp. Anyone with the link can manage only this instructor's students and lessons.", "Invia questo link su WhatsApp all'istruttore. Chiunque abbia il link può gestire solo gli allievi e le lezioni di questo istruttore.", "Envoyez-lui ce lien sur WhatsApp. Toute personne ayant le lien peut gérer uniquement les élèves et les leçons de ce moniteur.", "Envíale este enlace por WhatsApp. Quien tenga el enlace solo podrá gestionar los alumnos y clases de este instructor.", "أرسل له هذا الرابط عبر واتساب. أي شخص لديه الرابط يمكنه إدارة طلاب ودروس هذا المدرب فقط."),
 "reset_link": ("Reset link (old link stops working)", "Rigenera il link (il vecchio smette di funzionare)", "Réinitialiser le lien (l'ancien ne fonctionnera plus)", "Restablecer el enlace (el anterior dejará de funcionar)", "إعادة تعيين الرابط (يتوقف الرابط القديم)"),
 "students": ("Students", "Allievi", "Élèves", "Alumnos", "الطلاب"),
 "lessons": ("Lessons", "Lezioni", "Leçons", "Clases", "الدروس"),
 "waitlist": ("Waitlist", "Lista d'attesa", "Liste d'attente", "Lista de espera", "قائمة الانتظار"),
 "status": ("Status", "Stato", "Statut", "Estado", "الحالة"),
 "active": ("Active", "Attivo", "Actif", "Activo", "نشط"),
 "inactive": ("Inactive", "Non attivo", "Inactif", "Inactivo", "غير نشط"),
 "deactivate": ("Deactivate", "Disattiva", "Désactiver", "Desactivar", "تعطيل"),
 "add_student": ("Add student", "Aggiungi allievo", "Ajouter un élève", "Añadir alumno", "إضافة طالب"),
 "new_student": ("New student", "Nuovo allievo", "Nouvel élève", "Nuevo alumno", "طالب جديد"),
 "student": ("Student", "Allievo", "Élève", "Alumno", "الطالب"),
 "message_language": ("Message language", "Lingua dei messaggi", "Langue des messages", "Idioma de los mensajes", "لغة الرسائل"),
 "lang_it": ("Italian", "Italiano", "Italien", "Italiano", "الإيطالية"),
 "lang_en": ("English", "Inglese", "Anglais", "Inglés", "الإنجليزية"),
 "when_rome": ("When (Rome time)", "Quando (ora italiana)", "Quand (heure de Rome)", "Cuándo (hora de Roma)", "الموعد (توقيت روما)"),
 "location": ("Location", "Luogo", "Lieu", "Lugar", "المكان"),
 "location_opt": ("Location (optional)", "Luogo (facoltativo)", "Lieu (facultatif)", "Lugar (opcional)", "المكان (اختياري)"),
 "date_time": ("Date & time (Rome local time)", "Data e ora (ora italiana)", "Date et heure (heure de Rome)", "Fecha y hora (hora de Roma)", "التاريخ والوقت (توقيت روما)"),
 "reminder_to": ("Reminder to the student", "Promemoria all'allievo", "Rappel pour l'élève", "Recordatorio para el alumno", "تذكير للطالب"),
 "rem_auto": ("Automatic (24h and 2h before)", "Automatico (24 ore e 2 ore prima)", "Automatique (24 h et 2 h avant)", "Automático (24 h y 2 h antes)", "تلقائي (قبل 24 ساعة وساعتين)"),
 "rem_now": ("Send right now", "Invia subito", "Envoyer maintenant", "Enviar ahora", "إرسال الآن"),
 "rem_2min": ("Send in 2 minutes", "Invia tra 2 minuti", "Envoyer dans 2 minutes", "Enviar en 2 minutos", "إرسال بعد دقيقتين"),
 "schedule_lesson": ("Schedule lesson", "Aggiungi lezione", "Planifier la leçon", "Programar clase", "جدولة الدرس"),
 "new_lesson": ("New lesson", "Nuova lezione", "Nouvelle leçon", "Nueva clase", "درس جديد"),
 "send_now": ("Send now", "Invia ora", "Envoyer", "Enviar ahora", "أرسل الآن"),
 "send_in_2": ("Send in 2 min", "Invia tra 2 min", "Envoyer dans 2 min", "Enviar en 2 min", "أرسل بعد دقيقتين"),
 "cancel": ("Cancel", "Cancella", "Annuler", "Cancelar", "إلغاء"),
 "remove": ("Remove", "Rimuovi", "Retirer", "Quitar", "إزالة"),
 "no_students": ("No students yet.", "Nessun allievo.", "Aucun élève.", "Ningún alumno.", "لا يوجد طلاب."),
 "no_upcoming": ("No upcoming lessons.", "Nessuna lezione in programma.", "Aucune leçon à venir.", "No hay clases próximas.", "لا توجد دروس قادمة."),
 "past_cancelled": ("Past and cancelled lessons ({n})", "Lezioni passate e cancellate ({n})", "Leçons passées et annulées ({n})", "Clases pasadas y canceladas ({n})", "الدروس السابقة والملغاة ({n})"),
 "stat_upcoming": ("upcoming lessons", "lezioni in programma", "leçons à venir", "clases próximas", "دروس قادمة"),
 "stat_confirmed": ("confirmed", "confermate", "confirmées", "confirmadas", "مؤكدة"),
 "stat_waiting": ("waiting for reply", "in attesa di risposta", "en attente de réponse", "esperando respuesta", "بانتظار الرد"),
 "stat_resched": ("want to reschedule", "vogliono spostare", "veulent reporter", "quieren cambiar", "يريدون إعادة الجدولة"),
 "stat_students": ("active students", "allievi attivi", "élèves actifs", "alumnos activos", "طلاب نشطون"),
 "waiting": ("Waiting", "In attesa", "En attente", "En espera", "بالانتظار"),
 "offered_slot": ("Slot offered", "Slot proposto", "Créneau proposé", "Hueco ofrecido", "تم عرض موعد"),
 "waitlist_empty": ("Waitlist empty.", "Lista d'attesa vuota.", "Liste d'attente vide.", "Lista de espera vacía.", "قائمة الانتظار فارغة."),
 "add_to_waitlist": ("Add to waitlist", "Aggiungi alla lista d'attesa", "Ajouter à la liste d'attente", "Añadir a la lista de espera", "إضافة إلى قائمة الانتظار"),
 "add": ("Add", "Aggiungi", "Ajouter", "Añadir", "إضافة"),
 "add_student_first": ("Add a student first", "Aggiungi prima un allievo", "Ajoutez d'abord un élève", "Añade primero un alumno", "أضف طالباً أولاً"),
 "status_scheduled": ("Scheduled", "In programma", "Planifiée", "Programada", "مجدولة"),
 "status_confirmed": ("Confirmed", "Confermata", "Confirmée", "Confirmada", "مؤكدة"),
 "status_cancelled": ("Cancelled", "Cancellata", "Annulée", "Cancelada", "ملغاة"),
 "status_reschedule_requested": ("Wants to reschedule", "Vuole spostarla", "Demande un report", "Pide cambiarla", "يطلب إعادة الجدولة"),
 "status_no_show": ("No-show", "Assente", "Absent", "No se presentó", "غائب"),
 "status_completed": ("Completed", "Completata", "Terminée", "Completada", "مكتملة"),
 "hello": ("Hello {name}", "Ciao {name}", "Bonjour {name}", "Hola {name}", "مرحباً {name}"),
 "portal_intro": ("Students get a WhatsApp reminder 24 hours and 2 hours before each lesson and can confirm or cancel by replying. If someone cancels, the slot is offered to the waitlist. Times are in Italian time.", "Gli allievi ricevono un promemoria su WhatsApp 24 ore e 2 ore prima della lezione e possono confermare o cancellare rispondendo. Se qualcuno cancella, lo slot viene proposto alla lista d'attesa. Gli orari sono in ora italiana.", "Les élèves reçoivent un rappel WhatsApp 24 h et 2 h avant chaque leçon et peuvent confirmer ou annuler en répondant. Si quelqu'un annule, le créneau est proposé à la liste d'attente. Les horaires sont à l'heure italienne.", "Los alumnos reciben un recordatorio por WhatsApp 24 h y 2 h antes de cada clase y pueden confirmar o cancelar respondiendo. Si alguien cancela, el hueco se ofrece a la lista de espera. Las horas son en horario italiano.", "يتلقى الطلاب تذكيراً عبر واتساب قبل 24 ساعة وقبل ساعتين من كل درس ويمكنهم التأكيد أو الإلغاء بالرد. إذا ألغى أحدهم يُعرض الموعد على قائمة الانتظار. الأوقات حسب التوقيت الإيطالي."),
 "tip_whatsapp": ("Tip: you can also add students by WhatsApp. Text the bot: aggiungi Giulia +393331234567", "Suggerimento: puoi aggiungere allievi anche da WhatsApp. Scrivi al bot: aggiungi Giulia +393331234567", "Astuce : vous pouvez aussi ajouter des élèves par WhatsApp. Écrivez au bot : aggiungi Giulia +393331234567", "Consejo: también puedes añadir alumnos por WhatsApp. Escribe al bot: aggiungi Giulia +393331234567", "نصيحة: يمكنك أيضاً إضافة الطلاب عبر واتساب. اكتب للبوت: aggiungi Giulia +393331234567"),
 "consent_note": ("Let the student know they will receive WhatsApp reminders from this number.", "Avvisa l'allievo che riceverà messaggi WhatsApp di promemoria da questo numero.", "Prévenez l'élève qu'il recevra des rappels WhatsApp de ce numéro.", "Avisa al alumno de que recibirá recordatorios por WhatsApp desde este número.", "أخبر الطالب أنه سيتلقى تذكيرات واتساب من هذا الرقم."),
 "sent_twilio": ("Sent to Twilio", "Inviato a Twilio", "Envoyé à Twilio", "Enviado a Twilio", "أُرسل إلى Twilio"),
 "sent_twilio_detail": ("Twilio accepted the message for {phone}. Check that phone's WhatsApp.", "Twilio ha accettato il messaggio per {phone}. Controlla WhatsApp su quel telefono.", "Twilio a accepté le message pour {phone}. Vérifiez WhatsApp sur ce téléphone.", "Twilio aceptó el mensaje para {phone}. Revisa WhatsApp en ese teléfono.", "قبلت Twilio الرسالة إلى {phone}. تحقق من واتساب على ذلك الهاتف."),
 "send_failed": ("Send failed", "Invio non riuscito", "Échec de l'envoi", "Error al enviar", "فشل الإرسال"),
 "reminder_sent": ("Reminder sent", "Promemoria inviato", "Rappel envoyé", "Recordatorio enviado", "تم إرسال التذكير"),
 "reminder_sent_to": ("Sent to {name} ({phone}). They can reply SI or NO.", "Inviato a {name} ({phone}). Può rispondere SI o NO.", "Envoyé à {name} ({phone}). Il/elle peut répondre SI ou NO.", "Enviado a {name} ({phone}). Puede responder SI o NO.", "أُرسل إلى {name} ({phone}). يمكنه الرد بـ SI أو NO."),
 "reminder_sent_lesson": ("Lesson added and the reminder was sent. The student can reply SI or NO.", "Lezione aggiunta e promemoria inviato. L'allievo può rispondere SI o NO.", "Leçon ajoutée et rappel envoyé. L'élève peut répondre SI ou NO.", "Clase añadida y recordatorio enviado. El alumno puede responder SI o NO.", "تمت إضافة الدرس وإرسال التذكير. يمكن للطالب الرد بـ SI أو NO."),
 "reminder_scheduled": ("Reminder scheduled", "Promemoria programmato", "Rappel programmé", "Recordatorio programado", "تمت جدولة التذكير"),
 "reminder_scheduled_detail": ("Lesson added. The reminder will be sent at {time} (in about 2 minutes).", "Lezione aggiunta. Il promemoria partirà alle {time} (tra circa 2 minuti).", "Leçon ajoutée. Le rappel sera envoyé à {time} (dans environ 2 minutes).", "Clase añadida. El recordatorio se enviará a las {time} (en unos 2 minutos).", "تمت إضافة الدرس. سيُرسل التذكير في {time} (بعد حوالي دقيقتين)."),
 "hint_check": ("If it doesn't arrive, check the System check box on the admin home page. If the server restarts before then, the reminder is skipped.", "Se non arriva, controlla il riquadro Controllo sistema nella home admin. Se il server si riavvia prima, il promemoria viene saltato.", "S'il n'arrive pas, consultez la vérification du système sur l'accueil admin. Si le serveur redémarre avant, le rappel est ignoré.", "Si no llega, revisa la verificación del sistema en el inicio de admin. Si el servidor se reinicia antes, el recordatorio se omite.", "إذا لم يصل، راجع فحص النظام في الصفحة الرئيسية للإدارة. إذا أُعيد تشغيل الخادم قبل ذلك يُتخطى التذكير."),
 "reminder_failed": ("Lesson added, but the reminder failed", "Lezione aggiunta, ma il promemoria non è partito", "Leçon ajoutée, mais le rappel a échoué", "Clase añadida, pero falló el recordatorio", "تمت إضافة الدرس لكن فشل التذكير"),
 "reminder_failed_detail": ("The lesson was saved, but sending failed:", "La lezione è stata salvata, ma l'invio non è riuscito:", "La leçon a été enregistrée, mais l'envoi a échoué :", "La clase se guardó, pero el envío falló:", "تم حفظ الدرس لكن الإرسال فشل:"),
 "err_title": ("Something went wrong", "Qualcosa non ha funzionato", "Un problème est survenu", "Algo salió mal", "حدث خطأ ما"),
 "err_server": ("Server error. Please try again shortly. If it keeps happening, tell whoever set up the service for you.", "Errore del server. Riprova tra poco; se continua, avvisa chi ti ha attivato il servizio.", "Erreur du serveur. Réessayez dans un instant ; si cela continue, prévenez la personne qui a activé le service.", "Error del servidor. Inténtalo de nuevo en un momento; si continúa, avisa a quien activó el servicio.", "خطأ في الخادم. حاول مرة أخرى بعد قليل، وإن استمر أخبر من فعّل الخدمة لك."),
 "err_code": ("Error {n}", "Errore {n}", "Erreur {n}", "Error {n}", "خطأ {n}"),
 "err_fields": ("Some fields are missing or invalid. Go back and check the form.", "Alcuni campi mancano o non sono validi. Torna indietro e controlla.", "Certains champs sont manquants ou invalides. Revenez en arrière et vérifiez.", "Faltan campos o no son válidos. Vuelve atrás y revisa el formulario.", "بعض الحقول ناقصة أو غير صالحة. ارجع وتحقق من النموذج."),
 "err_invalid_phone": ("Invalid phone number. Use the format +393331234567.", "Numero non valido. Usa il formato +393331234567.", "Numéro invalide. Utilisez le format +393331234567.", "Número no válido. Usa el formato +393331234567.", "رقم غير صالح. استخدم الصيغة +393331234567."),
 "err_phone_dup": ("This number is already registered as a student.", "Questo numero è già registrato.", "Ce numéro est déjà enregistré comme élève.", "Este número ya está registrado como alumno.", "هذا الرقم مسجل بالفعل كطالب."),
 "err_bad_datetime": ("Invalid date or time.", "Data o ora non valida.", "Date ou heure invalide.", "Fecha u hora no válida.", "تاريخ أو وقت غير صالح."),
 "err_past": ("That date/time is in the past.", "La data è nel passato.", "Cette date est dans le passé.", "Esa fecha ya pasó.", "هذا التاريخ في الماضي."),
 "err_not_found": ("Not found. The link may be wrong or out of date.", "Non trovato. Il link potrebbe essere sbagliato o scaduto.", "Introuvable. Le lien est peut-être incorrect ou périmé.", "No encontrado. El enlace puede ser incorrecto o estar caducado.", "غير موجود. قد يكون الرابط خاطئاً أو منتهياً."),
}

STRINGS = {k: dict(zip(_ORDER, v)) for k, v in _T.items()}


def T(key: str, **kw) -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key
    text = entry.get(current.get()) or entry["en"]
    return text.format(**kw) if kw else text


def set_lang(code: str) -> None:
    current.set(code if code in LANGS else "en")


def get_lang(request: Request) -> str:
    code = request.cookies.get("lang", "")
    if code in LANGS:
        return code
    return "it" if request.url.path.startswith("/i/") else "en"


async def use_request_lang(request: Request) -> None:
    """Router dependency: remembers this request's language and path (read by T() and the page header)."""
    current.set(get_lang(request))
    current_path.set(request.url.path)


router = APIRouter()


@router.get("/set-lang")
def set_language(lang: str = "en", next: str = "/"):
    if not next.startswith("/") or next.startswith("//") or "\\" in next or len(next) > 300:
        next = "/"
    response = RedirectResponse(url=next, status_code=303)
    if lang in LANGS:
        response.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365, samesite="lax", path="/")
    return response
