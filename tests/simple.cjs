// A aba "Em linguagem simples" tem de renderizar para TODAS as análises completas de data.js (sem exceções, sem undefined/NaN)
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const script = fs.readFileSync('index.html', 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const section = (a, b) => script.slice(script.indexOf(a), script.indexOf(b, script.indexOf(a)));
const D = JSON.parse(fs.readFileSync('data.js', 'utf8').slice('window.DATA='.length));
const ctx = vm.createContext({console, D, T: D.tickers});
vm.runInContext(`
const fin=Number.isFinite,clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const PL={cap:2000},RISKPT={"Baixo":"Baixo","Médio":"Moderado","Alto":"Alto"},E0=v=>"€"+Math.round(v);
const usd=v=>String(v),n=(v,d=0)=>v==null?"–":Number(v).toFixed(d),esc=s=>String(s??""),eur=v=>"€"+v,sg=v=>String(v);
${section('// <exit-targets>', '// </exit-targets>')}
${section('function entryCheck(', 'const zoneTag=')}
${section('function planLevels(', 'const WHT=')}
${section('function simpleHTML(', 'function open(')}
`, ctx);
let n = 0, plans = 0;
for (const k of Object.keys(D.tickers)) {
  const h = vm.runInContext(`simpleHTML(T[${JSON.stringify(k)}],${JSON.stringify(k)})`, ctx);
  assert.ok(!/undefined|NaN|Infinity/.test(h), `${k}: valor inválido na aba simples`);
  for (const s of ['Porque comprar', 'O que ter em conta', 'Quando comprar', 'Quanto comprar', 'Quando vender']) assert.ok(h.includes(s), `${k}: falta «${s}»`);
  n++; if (h.includes('Meta 1')) plans++;
}
console.log(`Aba simples OK: ${n} fichas (${plans} com plano de saída)`);
