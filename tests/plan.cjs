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
const usd=v=>String(v),n=(v,d=0)=>Number(v).toFixed(d);
const eurPx=k=>T[k].price*fxOf(k)/D.eurusd,volOfW=()=>null,WHT=()=>.15;
${section('// <exit-targets>', '// </exit-targets>')}
${section('function entryCheck(', 'const zoneTag=')}
${section('function planLevels(', 'const WHT=')}
${section('function planPool(', '// pesos:')}
${section('function planWeights(', 'function volOfW(')}
${section('function planCalc(', 'function planRender(')}
`, ctx);
const run = code => vm.runInContext(code, ctx);
run(`T.A={price:100,atr:3,vol:25,fair:150,buy_below:127.5,dy:3,payout:40,fcfy:5,nd:1,
  risk:'Baixo',sector:'Technology',rank:80,elite:true,
  cons:{total:20,buy_pct:90},q:{qscore:80,trap:false,norm:{}},high:140,ext:{pct:50,x75:97,d:1,n:400}};`);
// --- probabilidades (modelo de volatilidade, inalterado) ---
assert.ok(Math.abs(run('Phi(0)') - .5) < 1e-6 && Math.abs(run('Phi(1.96)') - .975) < 1e-4);
assert.ok(Math.abs(run('pTouch(100,100*Math.exp(.4538*.25),{vol:25})') - .65) < .004);
assert.equal(run('pTouch(100,99,{vol:25})'), 1);
assert.ok(run('pTouch(100,130,{vol:25},.25)') < run('pTouch(100,130,{vol:25},1)'));
// --- alvos: máximo de 52 semanas, valor justo e teto de valuation (sem fórmula de volatilidade) ---
let X = run('exitTargets(T.A)');
assert.equal(X.k, 'hi52'); assert.equal(X.k2, 'fair'); assert.equal(X.m1.v, 140); assert.equal(X.m2.v, 150);
assert.ok(X.m1.nh === null && X.m2.nh > 0); // 150 exige novo máximo de 52 semanas
assert.ok(run('exitTargets(T.A,undefined,3)').m1.pr < run('exitTargets(T.A,undefined,12)').m1.pr);
run('T.A.high=100; T.A.fair=101');
assert.equal(run('exitTargets(T.A)'), null); // nada a mais de +3%: sem alvo
run('T.A.high=140; delete T.A.fair; T.A.q.hist_pe={now:20,max:30}');
X = run('exitTargets(T.A)'); assert.equal(X.k, 'hi52'); assert.equal(X.k2, 'pecap'); assert.equal(X.m2.v, 150); // 100 × 30/20
run('delete T.A.q.hist_pe; T.A.fair=150');
// --- entrada: não esticada e abaixo do valor justo => já ---
let levels = run('planLevels(T.A)');
assert.equal(levels.inZone, true); assert.equal(levels.entry, 100); assert.equal(levels.entry1, 100); assert.equal(levels.entry2, null);
assert.ok(levels.stop >= 70 && levels.stop <= 90 && levels.t1 < levels.t2);
assert.ok((levels.ref - levels.stop) / levels.ref >= .1);
assert.equal(run('call(T.A)[0]'), 'g');
let result = run('planCalc()');
assert.ok(Math.abs(result.rows[0].sh * levels.ref - 2000) < 1e-8);
assert.ok(Math.abs(result.g1 - result.rows[0].sh * (levels.t1 - levels.ref)) < 1e-8);
assert.ok(Math.abs(result.ml - result.rows[0].sh * (levels.ref - levels.stop)) < 1e-8);
assert.equal(result.pending, 0);
assert.ok(Math.abs(result.dvg - result.rows[0].sh * 3) < 1e-8);
// --- esticada (percentil >= 90): sem entrada boa, espera pelo nível onde o esticamento volta ao P75 ---
run('T.A.ext={pct:95,x75:92,d:3,n:400}');
levels = run('planLevels(T.A)');
assert.equal(levels.inZone, false); assert.equal(levels.entry, 92); assert.equal(levels.entry1, null); assert.equal(levels.entry2, 92);
assert.ok(levels.E.stretched && !levels.E.rich && /esticada/.test(levels.E.why[0]));
assert.equal(run('call(T.A)[0]'), 'a');
assert.equal(run('planCalc().pending'), 2000);
// --- acima do valor justo: espera pelo valor justo; muito acima (> 25% de recuo) => sem plano realista ---
run('T.A.ext={pct:50,x75:97}; T.A.buy_below=90');
levels = run('planLevels(T.A)'); assert.equal(levels.entry, 90); assert.ok(levels.E.rich);
run('T.A.buy_below=60');
assert.equal(run('planLevels(T.A)'), null); assert.equal(run('entryCheck(T.A).realistic'), false);
run('T.A.ext={pct:95,x75:92}; T.A.buy_below=95'); // esticada e rica: o mais baixo dos dois
assert.equal(run('entryCheck(T.A).wait'), 92);
run('T.A.buy_below=127.5; T.A.ext={pct:50,x75:97}');
// --- crivos: armadilha de valor e Altman em perigo => sem plano ---
run('T.A.q.trap=true'); assert.equal(run('planLevels(T.A)'), null); run('T.A.q.trap=false');
run('T.A.q.altman={zone:"perigo"}'); assert.equal(run('planLevels(T.A)'), null); run('delete T.A.q.altman');
// --- sem esticamento e sem valor justo: sem base para decidir ---
run('delete T.A.ext; delete T.A.buy_below'); assert.equal(run('entryCheck(T.A)'), null);
run('T.A.buy_below=127.5');
run('T.A.elite=false');
assert.equal(run('planPool("bal").length'), 0);
run('T.A.elite=true; T.A.ext=undefined; T.A.buy_below=undefined; T.A.fair=undefined; T.A.target=undefined;');
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
