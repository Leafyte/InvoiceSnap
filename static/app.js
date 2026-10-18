const $ = id => document.getElementById(id);
const KEY = "invoicesnap.expenses";
let expenses = [];
try { expenses = JSON.parse(localStorage.getItem(KEY)) || []; } catch { expenses = []; }

const save = () => { try { localStorage.setItem(KEY, JSON.stringify(expenses)); } catch { } };
const say = (text, cls = "info") => { $("msg").innerHTML = text ? `<span class="${cls}"></span>` : ""; if (text) $("msg").firstChild.textContent = text; };

function render() {
  const body = $("rows");
  body.innerHTML = "";
  expenses.forEach((e, i) => {
    const tr = document.createElement("tr");
    if (e.review) tr.className = "review";
    tr.innerHTML = `<td><input data-k="merchant" aria-label="Merchant"></td>
      <td><input data-k="date" type="date" aria-label="Date"></td>
      <td><input data-k="total" class="num" type="number" step="0.01" min="0" aria-label="Total"></td>
      <td><select data-k="category" aria-label="Category">${CATEGORIES.map(c => `<option>${c}</option>`).join("")}</select></td>
      <td><button class="del ghost" title="Remove" aria-label="Remove expense">✕</button></td>`;
    tr.querySelectorAll("[data-k]").forEach(el => {
      el.value = e[el.dataset.k];
      el.addEventListener("input", () => { e[el.dataset.k] = el.dataset.k === "total" ? parseFloat(el.value) || 0 : el.value; save(); sum(); });
    });
    tr.querySelector(".del").onclick = () => { expenses.splice(i, 1); save(); render(); };
    body.appendChild(tr);
  });
  $("empty").hidden = expenses.length > 0;
  $("export").disabled = $("clear").disabled = !expenses.length;
  $("count").textContent = expenses.length ? `(${expenses.length})` : "";
  sum();
}
const sum = () => $("sum").textContent = expenses.reduce((s, e) => s + (e.total || 0), 0).toFixed(2);

async function scan(file) {
  const fd = new FormData(); fd.append("receipt", file);
  const r = await fetch("/api/scan", { method: "POST", body: fd });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || `Server error (${r.status})`);
  return d;
}

async function handle(files) {
  const list = [...files]; const errors = []; let warn = "";
  for (let i = 0; i < list.length; i++) {
    say(`Scanning ${list[i].name} (${i + 1}/${list.length})… the first scan can take a minute while Gemma loads.`);
    try {
      const d = await scan(list[i]);
      expenses.push({ ...d.expense, review: d.source === "fallback" });
      if (d.warning) warn = d.warning;
      save(); render();
    } catch (e) { errors.push(`${list[i].name}: ${e.message}`); }
  }
  if (errors.length) say(errors.join(" | "), "err");
  else say(warn || (list.length ? "Done. Review the fields below and fix anything that looks off." : ""), warn ? "warn" : "info");
}

const csvCell = v => { let s = String(v ?? ""); if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; return `"${s.replace(/"/g, '""')}"`; };
$("export").onclick = () => {
  const rows = [["Merchant", "Date", "Total", "Category"], ...expenses.map(e => [e.merchant, e.date, (+e.total || 0).toFixed(2), e.category])];
  const blob = new Blob(["\ufeff" + rows.map(r => r.map(csvCell).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" });
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `expenses-${new Date().toISOString().slice(0, 10)}.csv` });
  a.click(); URL.revokeObjectURL(a.href);
};
$("clear").onclick = () => { if (confirm("Remove all expenses?")) { expenses = []; save(); render(); } };

const drop = $("drop");
drop.onclick = () => $("file").click();
drop.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("file").click(); } };
$("file").onchange = e => { handle(e.target.files); e.target.value = ""; };
["dragover", "dragenter"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(t => drop.addEventListener(t, e => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", e => handle([...e.dataTransfer.files].filter(f => f.type.startsWith("image/"))));

fetch("/api/health").then(r => r.json()).then(h => {
  const p = (ok, t) => `<span class="pill ${ok ? "ok" : "bad"}">${t}: ${ok ? "ready" : "not found"}</span>`;
  $("status").innerHTML = p(h.tesseract, "Tesseract") + p(h.ollama, `Gemma (${h.model})`);
}).catch(() => { });
render();
