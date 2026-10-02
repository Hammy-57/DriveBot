"""
The look of the website (admin panel + instructor page): styles, small scripts and
reusable HTML pieces. Nothing here touches the database or WhatsApp, so the design
can be changed without risking the logic.

Design notes: neutral palette with one accent (the original yellow), system fonts
(no third-party requests), tabular numbers, logical CSS properties (so Arabic / RTL
works), and a few purposeful animations that all switch off for people who ask their
system for reduced motion.
"""
import html

from i18n import LANGS, RTL, T, current, current_path

esc = html.escape

CSS = """
:root{
  --bg:#101113; --surface:#16171a; --raised:#1c1d21; --line:#26272c; --line-strong:#34363c;
  --text:#ececee; --muted:#8d9097; --faint:#62656c;
  --accent:#f5c451; --accent-ink:#f5c451; --on-accent:#17181c; --accent-soft:rgba(245,196,81,.14);
  --ok:#3fb27f; --warn:#e5a23b; --info:#6b9bff; --bad:#ef5b61;
  --ok-soft:rgba(63,178,127,.14); --warn-soft:rgba(229,162,59,.14); --info-soft:rgba(107,155,255,.14); --bad-soft:rgba(239,91,97,.14);
  --radius:10px; color-scheme:dark;
}
:root[data-theme="light"]{
  --bg:#f6f6f3; --surface:#ffffff; --raised:#f1f1ed; --line:#e5e5df; --line-strong:#d3d3cb;
  --text:#18181b; --muted:#66666e; --faint:#9a9aa2;
  --accent:#f5c451; --accent-ink:#8a5a00; --on-accent:#17181c; --accent-soft:rgba(245,196,81,.3);
  --ok:#1f8f5f; --warn:#a96a00; --info:#2f5fd0; --bad:#d23c43;
  --ok-soft:rgba(31,143,95,.12); --warn-soft:rgba(169,106,0,.12); --info-soft:rgba(47,95,208,.1); --bad-soft:rgba(210,60,67,.1);
  color-scheme:light;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);
  font:15px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
  font-feature-settings:"tnum" 1;-webkit-font-smoothing:antialiased}
.theme-anim,.theme-anim *{transition:background-color .25s ease,border-color .25s ease,color .25s ease!important}
a{color:var(--accent-ink);text-decoration:none}
a:hover{text-decoration:underline;text-underline-offset:3px}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}
::selection{background:var(--accent);color:var(--on-accent)}
p{margin:0}
code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px;background:var(--raised);
  border:1px solid var(--line);border-radius:6px;padding:2px 6px;word-break:break-all}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px}
.num{font-variant-numeric:tabular-nums}
.muted{color:var(--muted)}

/* top bar */
#bar{position:fixed;inset-block-start:0;inset-inline:0;height:2px;background:var(--accent);z-index:60;
  transform:scaleX(0);transform-origin:left;opacity:0}
[dir=rtl] #bar{transform-origin:right}
#bar.run{opacity:1;transform:scaleX(.9);transition:transform 6s cubic-bezier(.1,.6,.2,1)}
.topbar{position:sticky;inset-block-start:0;z-index:30;background:var(--bg);border-bottom:1px solid var(--line)}
.topbar-in{max-width:1040px;margin:0 auto;padding:0 20px;height:56px;display:flex;align-items:center;justify-content:space-between;gap:12px}
.brand{display:flex;align-items:center;gap:10px;color:var(--text);font-weight:650;font-size:16px;letter-spacing:-.01em}
.brand:hover{text-decoration:none}
.brand svg{width:28px;height:28px;padding:4px;border-radius:8px;background:var(--accent);color:var(--on-accent);
  transition:transform .5s cubic-bezier(.3,1.4,.5,1)}
.brand:hover svg{transform:rotate(90deg)}
.tools{display:flex;align-items:center;gap:8px}
.lang{position:relative;display:flex;align-items:center;margin:0}
.lang svg{position:absolute;inset-inline-start:10px;width:15px;height:15px;color:var(--muted);pointer-events:none}
.lang select{height:34px;width:auto;padding-inline:32px 30px;font-size:13.5px;border-radius:8px;cursor:pointer}
.icon-btn{width:34px;height:34px;display:grid;place-items:center;border-radius:8px;border:1px solid var(--line-strong);
  background:var(--surface);color:var(--text);cursor:pointer;transition:background-color .15s,border-color .15s,transform .1s}
.icon-btn:hover{background:var(--raised);border-color:var(--faint)}
.icon-btn:active{transform:scale(.94)}
.icon-btn svg{width:17px;height:17px}
.i-moon{display:none}
:root[data-theme="light"] .i-moon{display:block}
:root[data-theme="light"] .i-sun{display:none}

/* layout */
.wrap{max-width:1040px;margin:0 auto;padding:30px 20px 90px}
.page-head{margin-bottom:20px}
.crumb{display:inline-block;font-size:13px;color:var(--muted);margin-bottom:12px}
.crumb:hover{color:var(--text);text-decoration:none}
h1{font-size:26px;line-height:1.2;font-weight:650;letter-spacing:-.02em;margin:0}
.sub{color:var(--muted);margin-top:6px;max-width:68ch}
.pill{display:inline-block;margin-top:8px;padding:2px 10px;border-radius:999px;background:var(--raised);border:1px solid var(--line);color:var(--muted)}
.note{margin-top:10px;font-size:13.5px;color:var(--muted);padding:10px 14px;border:1px solid var(--line);
  border-inline-start:3px solid var(--accent);border-radius:8px;background:var(--surface);max-width:68ch}
.section{margin-top:36px}
.section-head{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.section-head h2{font-size:15px;font-weight:650;margin:0;letter-spacing:-.005em}
.count{font-size:12px;color:var(--muted);background:var(--raised);border:1px solid var(--line);border-radius:999px;padding:1px 9px}
.card{border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);padding:16px 18px}
.hint{color:var(--muted);font-size:13.5px;margin:4px 0 12px}
.label-strong{font-weight:650}
.alert{margin:22px 0 0;padding:14px 16px;border:1px solid var(--line);border-inline-start:3px solid var(--bad);
  border-radius:var(--radius);background:var(--surface)}
.alert strong{color:var(--bad)}
.alert p{margin-top:8px}

/* KPI strip */
.kpis{display:grid;grid-template-columns:repeat(5,1fr);border:1px solid var(--line);border-radius:var(--radius);
  background:var(--surface);margin-top:24px;overflow:hidden}
.kpi{padding:15px 18px;border-inline-end:1px solid var(--line)}
.kpi:last-child{border-inline-end:0}
.kpi-num{font-size:28px;font-weight:650;letter-spacing:-.02em;line-height:1.1;font-variant-numeric:tabular-nums}
.kpi-label{font-size:12.5px;color:var(--muted);margin-top:5px}

/* tables */
.tbl{border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);overflow-x:auto}
table{width:100%;border-collapse:collapse}
th{font-size:12px;font-weight:600;color:var(--muted);text-align:start;padding:10px 16px;background:var(--raised);
  border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:12px 16px;border-bottom:1px solid var(--line);vertical-align:middle;white-space:nowrap}
td.breakable{white-space:normal;min-width:130px}
tbody tr:last-child td{border-bottom:0}
tbody tr{transition:background-color .15s ease}
tbody tr:hover{background:var(--raised)}
td.actions{text-align:end;white-space:nowrap}
td.actions form{display:inline-block;margin-inline-start:6px}
.empty{padding:34px 20px;text-align:center;color:var(--muted)}
.empty svg{width:28px;height:28px;margin-bottom:8px;color:var(--faint)}
.history{margin-top:12px}
.history>summary{cursor:pointer;color:var(--muted);font-size:13.5px;padding:6px 2px;list-style:none;display:flex;align-items:center;gap:8px}
.history>summary::-webkit-details-marker{display:none}
.history>summary::before{content:"";width:7px;height:7px;border-inline-end:2px solid currentColor;border-bottom:2px solid currentColor;
  transform:rotate(-45deg);transition:transform .2s}
[dir=rtl] .history>summary::before{transform:rotate(135deg)}
.history[open]>summary::before{transform:rotate(45deg)}
.history>.tbl{margin-top:8px;animation:rise .25s ease-out}

/* badges */
.badge{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:600;padding:3px 10px;border-radius:999px;
  background:var(--raised);color:var(--muted);white-space:nowrap}
.badge::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.badge.ok{color:var(--ok);background:var(--ok-soft)}
.badge.warn{color:var(--warn);background:var(--warn-soft)}
.badge.info{color:var(--info);background:var(--info-soft)}
.badge.bad{color:var(--bad);background:var(--bad-soft)}

/* buttons */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;height:36px;padding:0 14px;border-radius:8px;
  border:1px solid var(--line-strong);background:var(--surface);color:var(--text);font:inherit;font-size:14px;font-weight:600;
  cursor:pointer;position:relative;white-space:nowrap;text-decoration:none;
  transition:background-color .15s,border-color .15s,transform .08s,filter .15s}
.btn:hover{background:var(--raised);border-color:var(--faint);text-decoration:none}
.btn:active{transform:translateY(1px)}
.btn-primary{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.btn-primary:hover{background:var(--accent);border-color:var(--accent);filter:brightness(1.07)}
.btn-danger{color:var(--bad)}
.btn-danger:hover{background:var(--bad-soft);border-color:var(--bad)}
.btn-sm{height:30px;padding:0 11px;font-size:13px;border-radius:7px}
.btn.is-done{color:var(--ok);border-color:var(--ok)}
.btn.is-loading{color:transparent!important;pointer-events:none}
.btn.is-loading::after{content:"";position:absolute;width:15px;height:15px;border-radius:50%;
  border:2px solid var(--muted);border-inline-end-color:transparent;animation:spin .6s linear infinite}
.btn-primary.is-loading::after{border-color:var(--on-accent);border-inline-end-color:transparent}

/* forms */
.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 16px}
.field{display:flex;flex-direction:column;gap:6px;min-width:0}
.field.full{grid-column:1/-1}
.field label{font-size:13px;color:var(--muted);font-weight:500}
.form-actions{margin-top:18px}
input,select{height:38px;width:100%;padding:0 12px;border-radius:8px;border:1px solid var(--line-strong);background:var(--surface);
  color:var(--text);font:inherit;font-size:14px;transition:border-color .15s,box-shadow .15s}
input::placeholder{color:var(--faint)}
input:focus,select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
input[readonly]{background:var(--raised)}
select{appearance:none;-webkit-appearance:none;cursor:pointer;padding-inline-end:34px;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' fill='none' stroke='%238d9097' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M1 1.5l5 5 5-5'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 12px center}
[dir=rtl] select{background-position:left 12px center}
.lang select{background-position:right 10px center}
[dir=rtl] .lang select{background-position:left 10px center}
details.panel{margin-top:14px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface)}
details.panel>summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:10px;padding:12px 16px;
  font-weight:600;font-size:14px;border-radius:var(--radius)}
details.panel>summary::-webkit-details-marker{display:none}
details.panel>summary:hover{background:var(--raised)}
details.panel .plus{width:20px;height:20px;display:grid;place-items:center;border-radius:6px;background:var(--accent);
  color:var(--on-accent);transition:transform .22s ease}
details.panel[open]>summary .plus{transform:rotate(45deg)}
details.panel[open]>summary{border-bottom:1px solid var(--line);border-bottom-left-radius:0;border-bottom-right-radius:0}
details.panel>.panel-body{padding:16px 16px 18px;animation:rise .25s ease-out}
.linkbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.linkbar input{flex:1;min-width:220px;width:auto}
.linkbar form{margin:0}

/* system check */
.check{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:11px 0;border-bottom:1px solid var(--line)}
.checks .check:last-child{border-bottom:0}
.check .sub-hint{color:var(--muted);font-size:12.5px;margin-top:2px}
.state{display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:600;color:var(--muted)}
.state::before{content:"";width:8px;height:8px;border-radius:50%;background:currentColor}
.state.ok{color:var(--ok)}.state.bad{color:var(--bad)}
.nested{margin:0 0 0 0;padding:0;list-style:none}
.test-form{margin-top:18px;padding-top:18px;border-top:1px solid var(--line)}

/* result / error screens */
.result{max-width:560px;margin:56px auto 0;text-align:center}
.result .ico{width:52px;height:52px;border-radius:50%;display:grid;place-items:center;margin:0 auto 16px}
.result .ico svg{width:26px;height:26px}
.result .ico.ok{background:var(--ok-soft);color:var(--ok)}
.result .ico.bad{background:var(--bad-soft);color:var(--bad)}
.result h1{font-size:22px}
.result .card{margin-top:18px;text-align:start}
.result .actions-row{margin-top:20px}
.code-line{margin-top:14px;color:var(--faint);font-size:12.5px}

/* motion */
@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@keyframes spin{to{transform:rotate(360deg)}}
.reveal{animation:rise .45s cubic-bezier(.2,.7,.2,1) both;animation-delay:calc(var(--i,0)*55ms)}
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation:none!important;transition:none!important}
}

/* phones: tables become stacked cards */
@media (max-width:760px){
  .kpis{grid-template-columns:repeat(2,1fr)}
  .kpi{border-bottom:1px solid var(--line)}
  .kpi:nth-child(2n){border-inline-end:0}
  .kpi:last-child{grid-column:1/-1;border-bottom:0;border-inline-end:0}
}
@media (max-width:680px){
  .wrap{padding:22px 14px 70px}
  h1{font-size:22px}
  .form-grid{grid-template-columns:1fr}
  .tbl table,.tbl tbody,.tbl tr,.tbl td{display:block;width:100%}
  .tbl thead{display:none}
  .tbl tbody tr{padding:12px 14px;border-bottom:1px solid var(--line)}
  .tbl tbody tr:last-child{border-bottom:0}
  .tbl td{white-space:normal;border:0;padding:4px 0;display:flex;justify-content:space-between;align-items:center;gap:16px;text-align:end}
  .tbl td[data-label]::before{content:attr(data-label);color:var(--muted);font-size:12.5px;text-align:start;flex:0 0 38%}
  .tbl td.actions{justify-content:flex-start;padding-top:10px;flex-wrap:wrap}
  .tbl td.actions form{margin-inline-start:0;margin-inline-end:6px}
  .lang select{padding-inline:30px 26px}
}
"""

HEAD_JS = 'try{var t=localStorage.getItem("theme");if(t)document.documentElement.setAttribute("data-theme",t)}catch(e){}'

BODY_JS = r"""
function toggleTheme(){var r=document.documentElement;r.classList.add("theme-anim");
var n=r.getAttribute("data-theme")==="light"?"dark":"light";r.setAttribute("data-theme",n);
try{localStorage.setItem("theme",n)}catch(e){}setTimeout(function(){r.classList.remove("theme-anim")},350)}
(function(){
var d=document,rm=window.matchMedia&&matchMedia("(prefers-reduced-motion: reduce)").matches,bar=d.getElementById("bar");
d.querySelectorAll("[data-count]").forEach(function(el){
  var to=parseInt(el.getAttribute("data-count"),10)||0;if(rm||to===0){el.textContent=to;return}
  var t0=null,dur=650;el.textContent="0";
  (function step(t){if(!t0)t0=t;var p=Math.min((t-t0)/dur,1);el.textContent=Math.round(to*(1-Math.pow(1-p,3)));if(p<1)requestAnimationFrame(step)})(performance.now());
});
function busy(){if(bar)bar.classList.add("run")}
function idle(){if(bar)bar.classList.remove("run");
  d.querySelectorAll(".is-loading").forEach(function(b){b.classList.remove("is-loading");b.disabled=false})}
window.addEventListener("pageshow",function(e){if(e.persisted)idle()});
d.addEventListener("submit",function(e){
  var f=e.target,msg=f.getAttribute("data-confirm");
  if(msg&&!window.confirm(msg)){e.preventDefault();return}
  var b=e.submitter||f.querySelector("button");
  if(b){b.classList.add("is-loading");setTimeout(function(){b.disabled=true},0)}
  busy()});
d.addEventListener("click",function(e){
  var c=e.target.closest("[data-copy]");
  if(c){var inp=d.querySelector(c.getAttribute("data-copy"));inp.select();
    var done=function(){var o=c.textContent;c.textContent=c.getAttribute("data-done");c.classList.add("is-done");
      setTimeout(function(){c.textContent=o;c.classList.remove("is-done")},1600)};
    if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(inp.value).then(done,function(){d.execCommand("copy");done()})}
    else{d.execCommand("copy");done()}
    return}
  var a=e.target.closest("a[href]");
  if(a&&a.origin===location.origin&&!a.target&&!e.metaKey&&!e.ctrlKey&&a.getAttribute("href").charAt(0)!=="#")busy()});
})();
"""

_ICON_WHEEL = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">'
               '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="2.2"/><path d="M3.5 10.5l6.3.8M20.5 10.5l-6.3.8M12 14.2v6.5"/></svg>')
_ICON_GLOBE = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">'
               '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18"/></svg>')
_ICON_SUN = ('<svg class="i-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">'
             '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M18.7 5.3l-1.6 1.6M6.9 17.1l-1.6 1.6"/></svg>')
_ICON_MOON = ('<svg class="i-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
              '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/></svg>')
_ICON_PLUS = ('<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" aria-hidden="true">'
              '<path d="M12 5v14M5 12h14"/></svg>')
_ICON_CAL = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">'
             '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>')
_ICON_OK = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
            '<path d="M5 12.5l4.5 4.5L19 7.5"/></svg>')
_ICON_BAD = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true">'
             '<path d="M6 6l12 12M18 6L6 18"/></svg>')

_BADGE_KIND = {"confirmed": "ok", "active": "ok", "scheduled": "warn", "reschedule_requested": "info",
               "cancelled": "bad", "no_show": "bad", "completed": "", "inactive": ""}


# ------------------------------------------------------------------ page shell
def _tools() -> str:
    lang, path = current.get(), current_path.get()
    options = "".join(
        f'<option value="{code}"{" selected" if code == lang else ""}>{esc(name)}</option>' for code, name in LANGS.items()
    )
    label, theme = esc(T("language")), esc(T("theme"))
    return (f'<div class="tools"><form class="lang" method="get" action="/set-lang">{_ICON_GLOBE}'
            f'<input type="hidden" name="next" value="{esc(path)}">'
            f'<select name="lang" title="{label}" aria-label="{label}" onchange="this.form.submit()">{options}</select>'
            f'<noscript><button class="btn btn-sm" type="submit">OK</button></noscript></form>'
            f'<button type="button" class="icon-btn" id="themeBtn" onclick="toggleTheme()" title="{theme}" aria-label="{theme}">'
            f'{_ICON_SUN}{_ICON_MOON}</button></div>')


def page(title: str, body: str, home: str = "/admin/") -> str:
    lang = current.get()
    direction = "rtl" if lang in RTL else "ltr"
    return (f'<!DOCTYPE html><html lang="{lang}" dir="{direction}"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="robots" content="noindex, nofollow"><meta name="referrer" content="no-referrer">'
            '<meta name="theme-color" content="#101113">'
            f'<title>{esc(title)}</title><script>{HEAD_JS}</script><style>{CSS}</style></head><body>'
            f'<div id="bar"></div>'
            f'<header class="topbar"><div class="topbar-in"><a class="brand" href="{esc(home)}">{_ICON_WHEEL}<span>DriveBot</span></a>'
            f'{_tools()}</div></header>'
            f'<main class="wrap">{body}</main><script>{BODY_JS}</script></body></html>')


# ------------------------------------------------------------------ building blocks
def header(title_html: str, sub: str = "", crumb_href: str = "", crumb_label: str = "", extra_html: str = "") -> str:
    crumb = f'<a class="crumb" href="{esc(crumb_href)}">{esc(crumb_label)}</a><br>' if crumb_href else ""
    sub_html = f'<p class="sub">{esc(sub)}</p>' if sub else ""
    return f'<div class="page-head reveal" style="--i:0">{crumb}<h1>{title_html}</h1>{sub_html}{extra_html}</div>'


def section(title: str, body: str, count=None, i: int = 1) -> str:
    c = f'<span class="count">{count}</span>' if count is not None else ""
    return f'<section class="section reveal" style="--i:{i}"><div class="section-head"><h2>{esc(title)}</h2>{c}</div>{body}</section>'


def kpis(items, i: int = 1) -> str:
    cells = "".join(
        f'<div class="kpi"><div class="kpi-num" data-count="{int(v)}">{int(v)}</div><div class="kpi-label">{esc(lbl)}</div></div>'
        for v, lbl in items
    )
    return f'<div class="kpis reveal" style="--i:{i}">{cells}</div>'


def badge(status: str) -> str:
    kind = _BADGE_KIND.get(status, "")
    return f'<span class="badge {kind}">{esc(T("status_" + status) if status not in ("active", "inactive") else T(status))}</span>'


def empty(text: str) -> str:
    return f'<div class="tbl empty">{_ICON_CAL}<p>{esc(text)}</p></div>'


def tr(headers, cells, actions: str | None = None, wrap=()) -> str:
    """One table row. `cells` are ready-made HTML; `headers` become the mobile labels;
    columns listed in `wrap` may wrap onto two lines (others stay on one line)."""
    tds = "".join(f'<td data-label="{esc(h)}"{" class=breakable" if n in wrap else ""}>{c}</td>'
                  for n, (h, c) in enumerate(zip(headers, cells)))
    if actions is not None:
        tds += f'<td class="actions">{actions}</td>'
    return f"<tr>{tds}</tr>"


def table(headers, rows, empty_text: str = "", has_actions: bool = True) -> str:
    if not rows:
        return empty(empty_text) if empty_text else ""
    ths = "".join(f"<th>{esc(h)}</th>" for h in headers) + ("<th></th>" if has_actions else "")
    return f'<div class="tbl"><table><thead><tr>{ths}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def button_form(action: str, label: str, kind: str = "danger", confirm: bool = True, small: bool = True) -> str:
    cls = {"danger": "btn btn-danger", "ghost": "btn", "primary": "btn btn-primary"}[kind] + (" btn-sm" if small else "")
    conf = f' data-confirm="{esc(T("confirm"))}"' if confirm else ""
    return f'<form method="post" action="{esc(action)}"{conf}><button type="submit" class="{cls}">{esc(label)}</button></form>'


def field(label: str, name: str, type: str = "text", placeholder: str = "", required: bool = True,
          full: bool = False, ltr: bool = False) -> str:
    attrs = (f' placeholder="{esc(placeholder)}"' if placeholder else "") + (" required" if required else "") + (' dir="ltr"' if ltr else "")
    return f'<div class="field{" full" if full else ""}"><label>{esc(label)}</label><input type="{type}" name="{name}"{attrs}></div>'


def select_field(label: str, name: str, options_html: str, full: bool = False) -> str:
    return f'<div class="field{" full" if full else ""}"><label>{esc(label)}</label><select name="{name}" required>{options_html}</select></div>'


def form(action: str, fields_html: str, submit_label: str) -> str:
    return (f'<form method="post" action="{esc(action)}"><div class="form-grid">{fields_html}</div>'
            f'<div class="form-actions"><button type="submit" class="btn btn-primary">{esc(submit_label)}</button></div></form>')


def panel(summary: str, inner_html: str) -> str:
    return (f'<details class="panel"><summary><span class="plus">{_ICON_PLUS}</span>{esc(summary)}</summary>'
            f'<div class="panel-body">{inner_html}</div></details>')


def history(summary: str, table_html: str) -> str:
    return f'<details class="history"><summary>{esc(summary)}</summary>{table_html}</details>'


def alert(title: str, body_html: str) -> str:
    return f'<div class="alert reveal" style="--i:1"><strong>{esc(title)}</strong><p>{body_html}</p></div>'


def state(ok: bool) -> str:
    return f'<span class="state {"ok" if ok else "bad"}">{esc(T("yes") if ok else T("no"))}</span>'


def check_row(label: str, right_html: str, hint: str = "") -> str:
    hint_html = f'<div class="sub-hint">{esc(hint)}</div>' if hint else ""
    return f'<div class="check"><div>{esc(label)}{hint_html}</div><div>{right_html}</div></div>'


def linkbar(url: str, copy_label: str, copied_label: str, extra_html: str = "") -> str:
    return (f'<div class="linkbar"><input id="portalLink" class="mono" readonly value="{esc(url)}" dir="ltr" onclick="this.select()">'
            f'<button type="button" class="btn" data-copy="#portalLink" data-done="{esc(copied_label)}">{esc(copy_label)}</button>{extra_html}</div>')


def result_view(ok: bool, title: str, detail_html: str, back: str, back_label: str, code_line: str = "") -> str:
    ico = f'<div class="ico {"ok" if ok else "bad"}">{_ICON_OK if ok else _ICON_BAD}</div>'
    code = f'<p class="code-line">{esc(code_line)}</p>' if code_line else ""
    return (f'<div class="result reveal" style="--i:0">{ico}<h1>{esc(title)}</h1>'
            f'<div class="card reveal" style="--i:1"><p>{detail_html}</p></div>{code}'
            f'<div class="actions-row"><a class="btn" href="{esc(back)}">{esc(back_label)}</a></div></div>')
