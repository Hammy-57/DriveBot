"""
Shared look & feel for the admin panel and the instructor portal.

Pure server-rendered HTML + one small stylesheet: no JavaScript framework, no
external fonts or CDN, so pages stay fast, private and work offline-ish.
Supports light and dark mode automatically (follows the device setting).
"""
import html

esc = html.escape

LOGO = (
    '<svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true">'
    '<rect width="32" height="32" rx="9" fill="url(#g)"/>'
    '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
    '<stop offset="0" stop-color="#22c997"/><stop offset="1" stop-color="#0b8f6a"/></linearGradient></defs>'
    '<path d="M9 21.5V13a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3h-6.2L10 25v-3.5z" '
    'fill="none" stroke="#fff" stroke-width="1.8" stroke-linejoin="round"/>'
    '<path d="M13 15.5h6M13 18h3.5" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg>'
)

ICON_BACK = ('<svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><path d="M12 4l-6 6 6 6" '
             'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
ICON_OK = ('<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true"><circle cx="12" cy="12" r="11" fill="currentColor" opacity=".15"/>'
           '<path d="M7 12.5l3.2 3.2L17 9" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
ICON_ERR = ('<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true"><circle cx="12" cy="12" r="11" fill="currentColor" opacity=".15"/>'
            '<path d="M12 7v6m0 3.5v.01" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>')

STYLE = """
<style>
  :root {
    --bg: #f4f6f9; --surface: #ffffff; --surface-2: #f8fafc;
    --text: #0f172a; --muted: #64748b; --border: #e3e8ef;
    --brand: #0b8f6a; --brand-hover: #097a5a; --brand-soft: rgba(11,143,106,.10);
    --nav: #0b1220; --nav-text: #f1f5f9;
    --ok: #0b7a55;   --ok-bg: rgba(16,185,129,.14);
    --warn: #9a5b00; --warn-bg: rgba(245,158,11,.18);
    --bad: #b42318;  --bad-bg: rgba(239,68,68,.12);
    --info: #1d4ed8; --info-bg: rgba(59,130,246,.12);
    --neutral: #475569; --neutral-bg: rgba(100,116,139,.14);
    --shadow: 0 1px 2px rgba(15,23,42,.05), 0 4px 14px rgba(15,23,42,.05);
    --radius: 14px;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0a101c; --surface: #111a2c; --surface-2: #0e1626;
      --text: #e8edf5; --muted: #8a97ad; --border: #1f2c45;
      --brand: #22c997; --brand-hover: #3ddcad; --brand-soft: rgba(34,201,151,.12);
      --nav: #070c16; --nav-text: #f1f5f9;
      --ok: #4ade9b;   --ok-bg: rgba(34,197,94,.16);
      --warn: #fbbf4d; --warn-bg: rgba(245,158,11,.18);
      --bad: #ff8a80;  --bad-bg: rgba(239,68,68,.18);
      --info: #8ab4ff; --info-bg: rgba(59,130,246,.18);
      --neutral: #aab6c9; --neutral-bg: rgba(148,163,184,.14);
      --shadow: 0 1px 2px rgba(0,0,0,.35), 0 6px 20px rgba(0,0,0,.25);
    }
  }
  * { box-sizing: border-box; }
  html { -webkit-text-size-adjust: 100%; }
  body {
    margin: 0; background: var(--bg); color: var(--text); line-height: 1.5; font-size: 15px;
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  a { color: var(--brand); text-decoration: none; font-weight: 500; }
  a:hover { color: var(--brand-hover); text-decoration: underline; }
  code { background: var(--surface-2); border: 1px solid var(--border); padding: 1px 6px; border-radius: 6px;
         font-size: .86em; word-break: break-word; }

  /* ---------- top bar ---------- */
  .topbar { background: var(--nav); color: var(--nav-text); position: sticky; top: 0; z-index: 10;
            border-bottom: 1px solid rgba(255,255,255,.06); }
  .topbar-inner { max-width: 1040px; margin: 0 auto; padding: 12px 20px; display: flex; align-items: center; gap: 12px; }
  .brand { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 1.05rem; letter-spacing: -.01em; }
  .brand small { font-weight: 500; opacity: .6; font-size: .82rem; margin-left: 2px; }
  .topbar .spacer { flex: 1; }
  .pill { font-size: .75rem; padding: 4px 10px; border-radius: 999px; background: rgba(255,255,255,.1);
          color: var(--nav-text); font-weight: 600; letter-spacing: .02em; }

  /* ---------- layout ---------- */
  .wrap { max-width: 1040px; margin: 0 auto; padding: 28px 20px 72px; }
  .page-head { margin: 4px 0 22px; }
  .page-head h1 { font-size: 1.75rem; line-height: 1.2; letter-spacing: -.02em; margin: 6px 0 6px; }
  .page-head p { margin: 0; color: var(--muted); max-width: 70ch; }
  .crumb { display: inline-flex; align-items: center; gap: 4px; font-size: .86rem; color: var(--muted); font-weight: 500; }
  .crumb:hover { color: var(--text); text-decoration: none; }

  section { margin: 34px 0 0; }
  .section-head { display: flex; align-items: baseline; gap: 10px; margin: 0 0 12px; }
  .section-head h2 { font-size: 1.12rem; letter-spacing: -.01em; margin: 0; }
  .count { font-size: .78rem; font-weight: 600; color: var(--muted); background: var(--neutral-bg);
           padding: 2px 9px; border-radius: 999px; }

  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
          box-shadow: var(--shadow); padding: 20px 22px; margin: 14px 0; }
  .card h3 { margin: 0 0 4px; font-size: 1rem; letter-spacing: -.01em; }
  .card > p.hint { margin: 0 0 14px; }
  .card.danger { border-color: var(--bad); }
  .card.flush { padding: 0; overflow: hidden; }
  .hint { color: var(--muted); font-size: .88rem; }

  /* ---------- stats ---------- */
  .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 0 0 14px; }
  .stat { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
          padding: 14px 16px; box-shadow: var(--shadow); position: relative; overflow: hidden; }
  .stat::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--brand); opacity: .85; }
  .stat b { display: block; font-size: 1.9rem; line-height: 1.1; letter-spacing: -.03em; }
  .stat span { font-size: .82rem; color: var(--muted); }

  /* ---------- tables ---------- */
  .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  table { width: 100%; border-collapse: collapse; font-size: .92rem; }
  th { text-align: left; font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color: var(--muted);
       font-weight: 600; padding: 11px 16px; background: var(--surface-2); border-bottom: 1px solid var(--border);
       white-space: nowrap; }
  td { padding: 12px 16px; border-bottom: 1px solid var(--border); vertical-align: middle; }
  tr:last-child td { border-bottom: none; }
  tbody tr:hover td { background: var(--surface-2); }
  td.empty { text-align: center; color: var(--muted); padding: 28px 16px; }
  td.nowrap { white-space: nowrap; }
  .strong { font-weight: 600; }
  .actions { display: flex; gap: 6px; justify-content: flex-end; flex-wrap: wrap; }
  .actions form { margin: 0; }

  details { margin: 12px 0 0; }
  summary { cursor: pointer; color: var(--muted); font-weight: 500; font-size: .9rem; padding: 6px 2px; }
  summary:hover { color: var(--text); }
  details .card { margin-top: 8px; }

  /* ---------- badges ---------- */
  .badge, .status { display: inline-flex; align-items: center; gap: 6px; font-size: .76rem; font-weight: 600;
                    padding: 3px 10px; border-radius: 999px; background: var(--neutral-bg); color: var(--neutral);
                    white-space: nowrap; }
  .badge::before, .status::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .b-ok { background: var(--ok-bg); color: var(--ok); }
  .b-warn { background: var(--warn-bg); color: var(--warn); }
  .b-bad { background: var(--bad-bg); color: var(--bad); }
  .b-info { background: var(--info-bg); color: var(--info); }

  /* ---------- forms ---------- */
  .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px 16px; margin-top: 14px; }
  .form-grid .full { grid-column: 1 / -1; }
  .field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  label { font-size: .82rem; font-weight: 600; color: var(--text); }
  label .opt { color: var(--muted); font-weight: 400; }
  input, select {
    width: 100%; font: inherit; color: var(--text); background: var(--surface-2);
    border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; min-height: 42px;
    transition: border-color .15s, box-shadow .15s, background .15s;
  }
  input::placeholder { color: var(--muted); opacity: .7; }
  input:focus, select:focus { outline: none; border-color: var(--brand); background: var(--surface);
                              box-shadow: 0 0 0 3px var(--brand-soft); }
  input[readonly] { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .85rem; }

  /* ---------- buttons ---------- */
  button, .btn {
    font: inherit; font-weight: 600; font-size: .9rem; cursor: pointer; border: 1px solid transparent;
    background: var(--brand); color: #fff; padding: 10px 18px; border-radius: 10px; min-height: 42px;
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
    transition: background .15s, transform .05s, border-color .15s;
  }
  @media (prefers-color-scheme: dark) { button, .btn { color: #04271c; } button.danger { color: var(--bad); } }
  button:hover, .btn:hover { background: var(--brand-hover); text-decoration: none; }
  button:active { transform: translateY(1px); }
  button.small { padding: 5px 12px; min-height: 32px; font-size: .8rem; border-radius: 8px; }
  button.secondary { background: transparent; color: var(--text); border-color: var(--border); }
  button.secondary:hover { background: var(--surface-2); border-color: var(--muted); }
  button.danger { background: transparent; color: var(--bad); border-color: var(--border); }
  button.danger:hover { background: var(--bad-bg); border-color: var(--bad); }
  .form-actions { margin-top: 16px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  form.inline { display: inline; margin: 0; }
  .copy-row { display: flex; gap: 8px; margin-top: 10px; }
  .copy-row input { flex: 1; }

  /* ---------- result / error pages ---------- */
  .result { display: flex; gap: 16px; align-items: flex-start; }
  .result .icon { flex: none; }
  .result.ok .icon { color: var(--ok); }
  .result.err .icon { color: var(--bad); }
  .result h1 { margin: 0 0 8px; font-size: 1.35rem; letter-spacing: -.02em; }
  .result p { margin: 0 0 8px; }

  .checks { list-style: none; margin: 10px 0 4px; padding: 0; }
  .checks li { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 9px 0;
               border-bottom: 1px solid var(--border); font-size: .92rem; }
  .checks li:last-child { border-bottom: none; }

  @media (max-width: 640px) {
    .wrap { padding: 20px 14px 56px; }
    .page-head h1 { font-size: 1.45rem; }
    .form-grid { grid-template-columns: 1fr; }
    .card { padding: 16px; }
    th, td { padding: 10px 12px; }
    .topbar-inner { padding: 10px 14px; }
    .stats { grid-template-columns: repeat(2, 1fr); }
  }

  /* ---------- polish layer ---------- */
  body { background:
           radial-gradient(900px 340px at 85% -80px, var(--brand-soft), transparent 70%),
           var(--bg); background-attachment: fixed; }
  .topbar { background: linear-gradient(180deg, #0f1a2e 0%, var(--nav) 100%); box-shadow: 0 6px 24px rgba(5,10,20,.18); }
  .brand span { background: linear-gradient(90deg,#fff,#b9f3dd); -webkit-background-clip: text; background-clip: text; color: transparent; }
  .pill { border: 1px solid rgba(255,255,255,.14); }

  .page-head { background: linear-gradient(135deg, var(--surface) 0%, var(--surface-2) 100%);
               border: 1px solid var(--border); border-radius: 18px; padding: 24px 26px; box-shadow: var(--shadow);
               position: relative; overflow: hidden; margin-bottom: 8px; }
  .page-head::after { content: ""; position: absolute; right: -60px; top: -60px; width: 220px; height: 220px; border-radius: 50%;
                      background: radial-gradient(circle, var(--brand-soft), transparent 68%); pointer-events: none; }
  .page-head h1 { font-size: 1.9rem; }

  .section-head { padding-bottom: 10px; border-bottom: 1px solid var(--border); margin-bottom: 16px; }
  .section-head h2 { font-size: 1.05rem; text-transform: none; }

  .card { transition: box-shadow .2s, transform .2s; }
  .card:hover { box-shadow: 0 2px 4px rgba(15,23,42,.05), 0 10px 28px rgba(15,23,42,.08); }

  .stat { transition: transform .15s; }
  .stat:hover { transform: translateY(-2px); }
  .stat:nth-child(1)::before { background: #3b82f6; }
  .stat:nth-child(2)::before { background: #10b981; }
  .stat:nth-child(3)::before { background: #94a3b8; }
  .stat:nth-child(4)::before { background: #f59e0b; }
  .stat:nth-child(5)::before { background: #8b5cf6; }
  .stat b { font-variant-numeric: tabular-nums; }

  .person { display: flex; align-items: center; gap: 11px; font-weight: 600; }
  .avatar { flex: none; width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center;
            font-size: .78rem; font-weight: 700; color: #fff; letter-spacing: .02em;
            box-shadow: inset 0 -2px 0 rgba(0,0,0,.12); }

  button:not(.secondary):not(.danger) { background: linear-gradient(180deg, var(--brand) 0%, var(--brand-hover) 100%);
                                       box-shadow: 0 1px 2px rgba(11,143,106,.35), 0 4px 12px rgba(11,143,106,.22); }
  button:not(.secondary):not(.danger):hover { filter: brightness(1.06); }
  button.small { box-shadow: none !important; }

  th { background: transparent; }
  tbody tr { transition: background .12s; }

  .footer { text-align: center; color: var(--muted); font-size: .8rem; padding: 8px 0 32px; }
  .footer b { color: var(--text); font-weight: 600; }

  @keyframes rise { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
  .wrap > * { animation: rise .35s ease both; }
  @media (prefers-reduced-motion: reduce) { .wrap > *, .card, .stat { animation: none; transition: none; } }
  @media (max-width: 640px) { .page-head { padding: 18px; } .page-head h1 { font-size: 1.5rem; } }
</style>
"""

_COPY_JS = """
<script>
  function copyLink(btn, id) {
    var el = document.getElementById(id); el.select();
    try { navigator.clipboard.writeText(el.value); } catch (e) { document.execCommand('copy'); }
    var old = btn.textContent; btn.textContent = btn.dataset.done || 'Copied'; setTimeout(function(){ btn.textContent = old; }, 1600);
  }
</script>
"""


def page(title: str, body: str, *, lang: str = "en", context: str = "Admin", extra_head: str = "") -> str:
    return (
        f'<!DOCTYPE html><html lang="{lang}"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta name="color-scheme" content="light dark">'
        f'<title>{esc(title)}</title>{extra_head}{STYLE}</head><body>'
        f'<header class="topbar"><div class="topbar-inner">'
        f'<div class="brand">{LOGO}<span>DriveBot</span></div>'
        f'<div class="spacer"></div><span class="pill">{esc(context)}</span></div></header>'
        f'<main class="wrap">{body}</main>'
        f'<footer class="footer"><b>DriveBot</b> &middot; WhatsApp reminders for driving instructors</footer>'
        f'{_COPY_JS}</body></html>'
    )


def page_head(title: str, subtitle: str = "", back: tuple | None = None) -> str:
    crumb = f'<a class="crumb" href="{esc(back[0])}">{ICON_BACK} {esc(back[1])}</a>' if back else ""
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    return f'<div class="page-head">{crumb}<h1>{title}</h1>{sub}</div>'


def section(title: str, content: str, count=None) -> str:
    badge = f'<span class="count">{count}</span>' if count is not None else ""
    return f'<section><div class="section-head"><h2>{esc(title)}</h2>{badge}</div>{content}</section>'


def table(headers, rows_html: str, empty: str = "", cols: int | None = None) -> str:
    """Card-wrapped table. `rows_html` is a string of <tr>…</tr>; if empty, shows `empty`."""
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    n = cols or len(headers)
    body = rows_html or f'<tr><td class="empty" colspan="{n}">{esc(empty)}</td></tr>'
    return (f'<div class="card flush"><div class="table-wrap"><table>'
            f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></div>')


def form_card(title: str, action: str, fields_html: str, submit: str, hint: str = "") -> str:
    hint_html = f'<p class="hint" style="margin:12px 0 0">{hint}</p>' if hint else ""
    return (f'<div class="card"><h3>{esc(title)}</h3>'
            f'<form method="post" action="{esc(action)}"><div class="form-grid">{fields_html}</div>'
            f'<div class="form-actions"><button type="submit">{esc(submit)}</button></div></form>{hint_html}</div>')


def field(label: str, control: str, *, full: bool = False, optional: str = "") -> str:
    opt = f' <span class="opt">{esc(optional)}</span>' if optional else ""
    cls = "field full" if full else "field"
    return f'<div class="{cls}"><label>{esc(label)}{opt}</label>{control}</div>'


_STATUS_CLASS = {
    "scheduled": "b-info", "confirmed": "b-ok", "cancelled": "b-bad",
    "reschedule_requested": "b-warn", "no_show": "b-bad", "completed": "",
}


def badge(label: str, status: str = "") -> str:
    return f'<span class="badge {_STATUS_CLASS.get(status, status)}">{esc(label)}</span>'


_AVATAR_COLORS = ["#0b8f6a", "#2563eb", "#7c3aed", "#db2777", "#ea580c", "#0891b2", "#4f46e5", "#65a30d"]


def person(name: str) -> str:
    """Name with a colored initials avatar (color is stable per name)."""
    parts = [p for p in (name or "?").split() if p]
    initials = (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper() if parts else "?"
    color = _AVATAR_COLORS[sum(ord(c) for c in (name or "")) % len(_AVATAR_COLORS)]
    return (f'<div class="person"><span class="avatar" style="background:{color}">{esc(initials)}</span>'
            f'<span>{esc(name)}</span></div>')
