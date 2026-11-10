const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('index.html', 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
new vm.Script(script); // Verifica também a sintaxe de toda a aplicação.
const section = (start, end) => script.slice(script.indexOf(start), script.indexOf(end, script.indexOf(start)));
const ctx = vm.createContext({console});
vm.runInContext(`
const fin=Number.isFinite,clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
let T={},D={eurusd:1},PL={cap:2000,prof:'bal'};
const fxOf=k=>D.rows?D.rows.find(r=>r[0]===k)?.[D.cols.indexOf('fx')]:1;
const eurPx=k=>T[k].price*fxOf(k)/D.eurusd,volOfW=()=>null,WHT=()=>.15;
${section('function planLevels(', 'const WHT=')}
${section('function planPool(', '// pesos:')}
${section('function planWeights(', 'function volOfW(')}
${section('function planCalc(', 'function planRender(')}
`, ctx);
const run = code => vm.runInContext(code, ctx);
run(`T.A={price:100,atr:3,vol:25,fair:150,buy_below:85,dy:3,payout:40,fcfy:5,nd:1,
  risk:'Baixo',sector:'Technology',rank:80,elite:true,
  cons:{total:20,buy_pct:90},q:{qscore:80,trap:false,norm:{}},sr:{sup:[{p:94}],res:[]}};`);
let levels = run('planLevels(T.A)');
assert.ok(levels.entry2);
assert.ok(Math.abs(levels.ref - 2 / (1 / levels.entry1 + 1 / levels.entry2)) < 1e-10);
let result = run('planCalc()');
assert.ok(Math.abs(result.rows[0].sh * levels.ref - 2000) < 1e-8);
assert.ok(Math.abs(result.g1 - result.rows[0].sh * (levels.t1 - levels.ref)) < 1e-8);
assert.ok(Math.abs(result.ml - result.rows[0].sh * (levels.ref - levels.stop)) < 1e-8);
assert.equal(result.pending, 1000);
assert.ok(Math.abs(result.dvg - result.rows[0].sh * 3) < 1e-8);
run('T.A.buy_below=120');
levels = run('planLevels(T.A)');
assert.equal(levels.entry2, null);
assert.equal(levels.ref, 101);
assert.equal(run('planCalc().pending'), 0);
run('T.A.elite=false');
assert.equal(run('planPool("bal").length'), 0);
run('T.A.elite=true; T.A.buy_below=0; T.A.sr={};');
assert.equal(run('planLevels(T.A)'), null);
for (let count = 1; count <= 5; count++) {
  run(`T=Object.fromEntries(Array.from({length:${count}},(_,i)=>['S'+i,{vol:i?100:12,q:{qscore:i?50:100}}]));`);
  const weights = run('planWeights(Object.keys(T))');
  assert.ok(Math.abs(weights.reduce((a,b)=>a+b,0)-1) < 1e-10);
  assert.ok(Math.max(...weights) <= Math.max(.35, 1/count) + 1e-9);
}
ctx.snapshot = JSON.parse(fs.readFileSync('data.js','utf8').slice('window.DATA='.length));
run('T=snapshot.tickers;D=snapshot');
for (const profile of ['bal','div','gro']) {
  run(`PL.prof='${profile}'`);
  const plan = run('planCalc()');
  assert.ok(plan.ks.length <= 5);
  if(!plan.ks.length)continue; // Um perfil pode legitimamente ficar sem candidatas.
  assert.equal(plan.rows.reduce((sum,r)=>sum+r.amt,0),2000);
  assert.ok(plan.pending >= 0 && plan.pending <= plan.tot);
  assert.ok(Number.isFinite(plan.g1) && Number.isFinite(plan.ml));
  if(profile==='bal')assert.ok(plan.rows.every(r=>r.t.elite));
  for(const row of plan.rows)assert.ok(row.pl.ref>row.pl.stop);
}
console.log('Plano: entradas, quantidades, retornos, crivo e pesos OK');
