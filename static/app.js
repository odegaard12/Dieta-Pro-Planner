let state=null; let page='home'; let mealItems=[]; let selectedDate=localStorage.getItem('selectedDate')||''; let selectedFoodPhoto='';
const PAGES=[['home','🏠','Resumen'],['register','⚡','Registrar'],['sport','🏋️','Deporte'],['templates','🍽️','Plantillas'],['foods','🥫','Alimentos'],['plan','📅','Plan'],['weights','⚖️','Historial peso'],['integrations','🔗','Integraciones'],['history','📚','Historial']];
const $=s=>document.querySelector(s); const fmt=n=>Number(n||0).toLocaleString('es-ES',{maximumFractionDigits:1});
const today=()=>state?.today||new Date().toISOString().slice(0,10); const nowHM=()=>state?.now||new Date().toTimeString().slice(0,5); const day=()=>selectedDate||today();
function toast(msg){const t=$('#toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2200)}
async function api(path,opts={}){const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts}); if(!r.ok){let e='Error';try{e=(await r.json()).error||e}catch{} throw new Error(e)} return r.json()}
async function apiForm(path,form){const r=await fetch(path,{method:'POST',body:form}); if(!r.ok){let e='Error';try{e=(await r.json()).error||e}catch{} throw new Error(e)} return r.json()}
async function load(){state=await api('/api/state'); if(!selectedDate){selectedDate=today(); localStorage.setItem('selectedDate',selectedDate)} renderNav(); render()}
function renderNav(){ $('#nav').innerHTML=PAGES.map(([id,ico,label])=>`<button class="${page===id?'active':''}" data-page="${id}">${ico}<span>${label}</span></button>`).join(''); document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{page=b.dataset.page; renderNav(); render()}) }
function setTitle(t){$('#pageTitle').textContent=t}
function go(p){page=p;renderNav();render()}
function byDate(arr,d=day()){return arr.filter(x=>x.date===d)}
function mealTotals(meals){return meals.reduce((a,m)=>{a.kcal+=(m.totals?.kcal||0);a.protein+=(m.totals?.protein||0);a.oil+=(m.items||[]).filter(i=>/aceite/i.test(i.food_name)).reduce((x,i)=>x+Number(i.grams||0),0);return a},{kcal:0,protein:0,oil:0})}
function workoutTotals(ws){return ws.reduce((a,w)=>a+Number(w.kcal||0),0)}
function latestWeight(){return [...state.weights].sort((a,b)=>(b.date+b.time).localeCompare(a.date+a.time))[0]}
function officialWeights(){return state.weights.filter(w=>w.official).sort((a,b)=>(a.date+a.time).localeCompare(b.date+b.time))}
function foodByName(n){return state.foods.find(f=>f.name===n)} function foodById(id){return state.foods.find(f=>Number(f.id)===Number(id))}
function calcFood(f,g){const factor=Number(g||0)/100; return {food_id:f.id,food_name:f.name,grams:Number(g||0),kcal:f.kcal*factor,protein:f.protein*factor,carbs:f.carbs*factor,fat:f.fat*factor,sugar:f.sugar*factor,salt:f.salt*factor}}
function calcList(items){return items.reduce((a,i)=>{a.kcal+=Number(i.kcal||0);a.protein+=Number(i.protein||0);a.fat+=Number(i.fat||0);a.carbs+=Number(i.carbs||0);a.oil+=/aceite/i.test(i.food_name)?Number(i.grams||0):0;return a},{kcal:0,protein:0,fat:0,carbs:0,oil:0})}
function mealAdvice(items){const t=calcList(items); let cls='good',label='BIEN',text='Buen plato para bajar peso y mantener fuerza.'; if(t.kcal<250){cls='warn';label='POCO';text='Puede quedarse corto: añade proteína o fruta si toca entrenar.'} if(t.protein<20){cls='warn';label='MÁS PROTEÍNA';text='Sube pollo, huevos, atún, yogur o queso fresco.'} if(t.kcal>850){cls='bad';label='ALTO';text='Ración alta: reduce carbohidrato, pan o cantidad total.'} if(t.oil>10){cls='bad';label='ACEITE ALTO';text='Aceite alto: 5 g normal, 10 g máximo.'} if(t.kcal>=350&&t.kcal<=750&&t.protein>=25&&t.oil<=10){cls='good';label='BIEN';text='Buen plato: saciante, proteína decente y aceite controlado.'} return {cls,label,text,t}}
function assistantFor(d=day()){
  const meals=byDate(state.meals,d);
  const workouts=byDate(state.workouts,d);
  const mt=mealTotals(meals);
  const sport=workoutTotals(workouts);
  const lw=latestWeight();
  const tips=[];
  const names=meals.flatMap(m=>[m.name,m.notes||'',...(m.items||[]).map(i=>i.food_name)]).join(' ').toLowerCase();
  const hasSweet=/chocolate|galleta|piruleta|dulce|tirma/.test(names);
  const hasCarb=/pasta|arroz|pan|plátano|platano|tortita/.test(names);
  const dinnerDone=meals.some(m=>/cena/i.test(m.name));

  if(!lw) tips.push('Registra un peso oficial por la mañana para empezar tendencia.');
  else if(!lw.official) tips.push('Último peso es referencia: el bueno es por la mañana, después baño y antes de desayunar.');

  if(mt.protein<90) tips.push('Proteína baja: prioriza pollo, huevos, atún, yogur proteico, jamón cocido extra o queso fresco batido.');
  else if(mt.protein<130) tips.push('Proteína bastante bien, pero intenta acercarte a 130 g si hoy entrenas o cenas tarde.');
  else tips.push('Proteína cubierta hoy.');

  if(mt.oil>15) tips.push('Aceite alto hoy: próxima comida con sartén antiadherente y 0–5 g.');
  else if(mt.oil>10) tips.push('Aceite algo alto: no pases de 5 g en la siguiente comida.');

  if(hasSweet && sport<500) tips.push('Ya hubo dulce: cena limpia, sin pan/arroz extra y con verdura + proteína.');
  if(hasSweet && sport>=500) tips.push('Hubo dulce, pero también deporte: no castigues; cena proteica y carbo controlado si hay hambre real.');

  if(sport>=900) tips.push('Día de mucho gasto: puedes meter carbo controlado, pero mantén proteína y no conviertas el deporte en barra libre.');
  else if(sport>=300) tips.push('Buen gasto de actividad: recupera con proteína, no con picoteo.');

  if(mt.kcal>2300) tips.push('Kcal altas: resto del día limpio, agua/infusión y sin más snacks.');
  else if(mt.kcal<900 && !dinnerDone) tips.push('Aún vas bajo de comida registrada: no llegues con hambre brutal a la noche.');
  else if(mt.kcal>=900 && mt.kcal<=2100) tips.push('Día razonable: controla aceite, raciones y cena según hambre real.');

  if(!hasCarb && sport>=700) tips.push('Con ese deporte y pocos hidratos, una ración pequeña de arroz/pasta puede tener sentido.');

  return [...new Set(tips)].slice(0,6)
}
function render(){const titles={home:'Resumen',register:'Registrar / comida',templates:'Plantillas rápidas',foods:'Alimentos comprados',sport:'Registrar deporte',plan:'Plan semanal',weights:'Historial de peso',integrations:'Integraciones',history:'Historial completo'}; setTitle(titles[page]); if(page==='home')renderHome(); if(page==='register')renderRegister(); if(page==='templates')renderTemplates(); if(page==='foods')renderFoods(); if(page==='sport')renderSport(); if(page==='plan')renderPlan(); if(page==='weights')renderWeights(); if(page==='integrations')renderIntegrations(); if(page==='history')renderHistory()}
function metric(icon,title,value,sub){return `<div class="card metric"><span class="icon">${icon}</span><div><small>${title}</small><br><b>${value}</b></div><small>${sub}</small></div>`}
function dateBar(){const label=day()===today()?'Día de hoy':'Día seleccionado';return `<div class="datebar"><div class="field"><label>${label}</label><input id="dashDate" type="date" value="${day()}" onchange="selectedDate=this.value;localStorage.setItem('selectedDate',selectedDate);render()"></div><button class="btn secondary" onclick="selectedDate=today();localStorage.setItem('selectedDate',selectedDate);render()">Ir a hoy real</button><span class="muted">Así no se mezclan actividades de ayer con hoy.</span></div>`}
function quickActions(){return `<div class="quick-actions"><button class="quick primary" onclick="go('register')"><span>🍽️</span><b>Registrar comida</b><small>alimentos + gramos</small></button><button class="quick sport" onclick="go('sport')"><span>🏋️</span><b>Registrar entreno</b><small>minutos, kcal o Strava</small></button><button class="quick weight" onclick="go('weights')"><span>⚖️</span><b>Registrar peso</b><small>oficial o referencia</small></button><button class="quick" onclick="go('templates')"><span>⚡</span><b>Usar plantilla</b><small>cambia gramos y guarda</small></button></div>`}
function renderHome(){const lw=latestWeight(); const meals=byDate(state.meals); const workouts=byDate(state.workouts); const mt=mealTotals(meals); const sport=workoutTotals(workouts); $('#view').innerHTML=`${dateBar()}<div class="grid cols-4 dashboard-metrics">${metric('⚖️','Último peso',lw?`${fmt(lw.kg)} kg`:'—',lw?`${lw.date} ${lw.time} · ${lw.official?'oficial':'referencia'}`:'sin datos')}${metric('🍽️','Comido',fmt(mt.kcal),'kcal estimadas')}${metric('💪','Proteína',`${fmt(mt.protein)} g`,'objetivo 130–150 g')}${metric('🔥','Actividad',fmt(sport),'kcal del día seleccionado')}</div><div class="grid cols-2 home-main" style="margin-top:14px"><div class="card assistant compact-assistant"><h3>🤖 Asistente</h3><ul>${assistantFor().map(x=>`<li>${x}</li>`).join('')}</ul></div><div class="card"><h3>📉 Peso oficial</h3>${weightChart()}<p class="muted">Solo pesos oficiales de mañana para tendencia.</p></div></div><div class="day-columns"><section class="card day-panel"><div class="section-title compact-title"><div><h3>🍽️ Comidas</h3><p>${fmt(mt.kcal)} kcal · ${fmt(mt.protein)} g prot.</p></div><button class="btn small" onclick="go('register')">+ Comida</button></div><div class="compact-list">${meals.length?meals.map(mealCardCompact).join(''):'<div class="empty">Sin comidas.</div>'}</div></section><section class="card day-panel"><div class="section-title compact-title"><div><h3>🏋️ Actividad</h3><p>${fmt(sport)} kcal</p></div><button class="btn small" onclick="go('sport')">+ Entreno</button></div><div class="compact-list">${workouts.length?workouts.map(workoutCardCompact).join(''):'<div class="empty">Sin entrenos para este día.</div>'}</div></section></div><div class="footer-space"></div>`}
function weightChart(){const ws=officialWeights().slice(-10); if(ws.length<2)return '<div class="empty">Cuando tengas 2+ pesos oficiales aparece la gráfica.</div>'; const vals=ws.map(w=>+w.kg),min=Math.min(...vals)-.2,max=Math.max(...vals)+.2; const pts=ws.map((w,i)=>{const x=20+i*(260/(ws.length-1)); const y=150-((w.kg-min)/(max-min))*120; return `${x},${y}`}).join(' '); return `<svg class="chart" viewBox="0 0 300 175"><polyline points="${pts}" fill="none" stroke="#0b6b55" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/>${ws.map((w,i)=>{const x=20+i*(260/(ws.length-1)); const y=150-((w.kg-min)/(max-min))*120; return `<circle cx="${x}" cy="${y}" r="5" fill="#0f8a6a"><title>${w.date}: ${w.kg}</title></circle>`}).join('')}<text x="18" y="168" font-size="11" fill="#697670">${ws[0].date}</text><text x="205" y="168" font-size="11" fill="#697670">${ws.at(-1).date}</text></svg>`}
function mealCard(m){return `<article class="list-card"><header><div><h4>${m.date} · ${m.time} · ${m.name}</h4><p class="muted">${m.notes||''}</p></div><button class="btn small danger" onclick="deleteMeal(${m.id})">×</button></header><div class="chips">${m.items.map(i=>`<span class="chip">${i.food_name} ${fmt(i.grams)}g</span>`).join('')}</div><b>${fmt(m.totals.kcal)} kcal · ${fmt(m.totals.protein)} g prot.</b></article>`}
function workoutCard(w){return `<article class="list-card"><header><div><h4>${w.date} · ${w.time} · ${w.name}</h4><p class="muted">${fmt(w.minutes)} min ${w.distance_km?`· ${fmt(w.distance_km)} km`:''} · ${w.notes||''}</p></div><button class="btn small danger" onclick="deleteWorkout(${w.id})">×</button></header><b>${fmt(w.kcal)} kcal</b></article>`}
function itemSummary(items){const shown=(items||[]).slice(0,3).map(i=>`${i.food_name} ${fmt(i.grams)}g`); const extra=(items||[]).length>3?` +${items.length-3}`:''; return shown.join(' · ')+extra}
function mealCardCompact(m){return `<article class="compact-card meal"><div class="compact-head"><div><b>${m.time} · ${m.name}</b><small>${itemSummary(m.items)}</small></div><strong>${fmt(m.totals.kcal)} kcal<br><span>${fmt(m.totals.protein)} g prot.</span></strong><button class="mini-delete" title="Borrar" onclick="deleteMeal(${m.id})">×</button></div>${m.notes?`<p class="compact-note">${m.notes}</p>`:''}</article>`}
function workoutCardCompact(w){return `<article class="compact-card workout"><div class="compact-head"><div><b>${w.time} · ${w.name}</b><small>${fmt(w.minutes)} min${w.distance_km?` · ${fmt(w.distance_km)} km`:''}${w.notes?` · ${w.notes}`:''}</small></div><strong>${fmt(w.kcal)} kcal</strong><button class="mini-delete" title="Borrar" onclick="deleteWorkout(${w.id})">×</button></div></article>`}
async function deleteMeal(id){if(!confirm('¿Borrar comida?'))return; await api('/api/meals/'+id,{method:'DELETE'}); toast('Comida borrada'); await load()} async function deleteWorkout(id){if(!confirm('¿Borrar entreno?'))return; await api('/api/workouts/'+id,{method:'DELETE'}); toast('Entreno borrado'); await load()}
function templateOptions(){return state.templates.map(t=>`<option value="${t.id}">${t.name}</option>`).join('')}
function renderRegister(){
  mealItems=[];
  $('#view').innerHTML=`<div class="register-grid">
    <section class="card register-main">
      <div class="section-title compact-title"><div><h3>🍽️ Nueva comida</h3><p>1) carga plantilla o busca alimentos · 2) cambia gramos · 3) guarda</p></div></div>
      <div class="row">
        <div class="field span-3"><label>Fecha</label><input id="mDate" type="date" value="${day()}"></div>
        <div class="field span-2"><label>Hora</label><input id="mTime" type="time" value="${nowHM()}"></div>
        <div class="field span-3"><label>Tipo</label><select id="mName"><option>Desayuno</option><option>Pre-comida</option><option>Comida</option><option>Merienda</option><option>Cena</option><option>Post-entreno</option></select></div>
        <div class="field span-4"><label>Notas</label><input id="mNotes" placeholder="pasta seca, tupper, post-HIIT..."></div>
      </div>
      <div class="template-loader">
        <div><b>⚡ Cargar plantilla</b><small>Se añade a esta comida y puedes cambiar gramos antes de guardar.</small></div>
        <select id="tplSelect"><option value="">Elegir plantilla...</option>${templateOptions()}</select>
        <button class="btn secondary" onclick="loadTemplateToMeal($('#tplSelect').value)">Cargar</button>
      </div>
      <div id="mealBuilder" class="meal-items"></div>
      <div class="sticky-actions">
        <button class="btn" onclick="saveMeal()">Guardar comida</button>
        <button class="btn secondary" onclick="saveMealAsTemplate()">Guardar como plantilla</button>
        <button class="btn secondary" onclick="clearMeal()">Limpiar</button>
      </div>
    </section>
    <aside class="card add-food-panel">
      <h3>➕ Añadir producto</h3>
      <div class="field"><label>Buscar alimento guardado</label><input id="foodSearch" placeholder="pollo, pasta, yogur..." oninput="renderSuggestions()"></div>
      <div class="field" style="margin-top:10px"><label>Gramos</label><input id="foodGrams" type="number" value="200"></div>
      <div id="suggestions" class="suggestions"></div>
      <p class="muted">Tip: si es una plantilla, cárgala y cambia solo gramos.</p>
    </aside>
    <section class="card weight-mini">
      <h3>⚖️ Peso rápido</h3>
      <div class="row">
        <div class="field span-4"><label>Fecha</label><input id="wDate" type="date" value="${today()}"></div>
        <div class="field span-3"><label>Hora</label><input id="wTime" type="time" value="${nowHM()}"></div>
        <div class="field span-3"><label>Kg</label><input id="wKg" type="number" step="0.01" placeholder="86.70"></div>
        <div class="field span-2"><label>Tipo</label><select id="wOfficial"><option value="1">Oficial</option><option value="0">Referencia</option></select></div>
        <div class="field span-12"><label>Contexto</label><input id="wCtx" placeholder="mañana, después baño"></div>
      </div>
      <button class="btn" onclick="saveWeight()">Guardar peso</button>
    </section>
  </div>`;
  renderMealBuilder(); renderSuggestions();
}
function loadTemplateToMeal(id){
  if(!id){toast('Elige una plantilla');return}
  const t=state.templates.find(x=>String(x.id)===String(id));
  if(!t){toast('Plantilla no encontrada');return}
  let p={items:[]};try{p=JSON.parse(t.payload)}catch{}
  mealItems=(p.items||[]).map(it=>{const f=foodByName(it.food);return f?calcFood(f,it.grams):null}).filter(Boolean);
  if($('#mNotes')&&!$('#mNotes').value) $('#mNotes').value=t.notes||'';
  renderMealBuilder(); toast('Plantilla cargada: cambia gramos y guarda');
}
function addFood(id){const f=foodById(id); const g=Number($('#foodGrams').value||f.typical_g||100); mealItems.push(calcFood(f,g)); $('#foodSearch').value=''; $('#foodGrams').value=f.typical_g||100; renderMealBuilder(); renderSuggestions()}
function renderMealBuilder(){const advice=mealAdvice(mealItems); $('#mealBuilder').innerHTML=`${mealItems.length?mealItems.map((it,idx)=>`<div class="item-row"><div><b>${it.food_name}</b><small>${fmt(it.kcal)} kcal · ${fmt(it.protein)} g prot.</small></div><input type="number" value="${fmt(it.grams)}" onchange="changeMealGram(${idx},this.value)"><button class="btn small danger" onclick="removeMealItem(${idx})">×</button></div>`).join(''):'<div class="empty">Busca un producto y añádelo. Después solo cambias gramos.</div>'}<div class="totals"><span class="pill ${advice.cls}">${advice.label}</span><b>${fmt(advice.t.kcal)} kcal</b><b>${fmt(advice.t.protein)} g proteína</b><span class="muted">${advice.text}</span></div>`}
function changeMealGram(idx,val){const f=foodById(mealItems[idx].food_id); mealItems[idx]=calcFood(f,Number(val||0)); renderMealBuilder()} function removeMealItem(idx){mealItems.splice(idx,1); renderMealBuilder()} function clearMeal(){mealItems=[];renderMealBuilder()}
async function saveMeal(){if(!mealItems.length){toast('Añade alimentos');return} await api('/api/meals',{method:'POST',body:JSON.stringify({date:$('#mDate').value,time:$('#mTime').value,name:$('#mName').value,notes:$('#mNotes').value,items:mealItems.map(i=>({food_id:i.food_id,grams:i.grams}))})}); toast('Comida guardada'); selectedDate=$('#mDate').value; localStorage.setItem('selectedDate',selectedDate); await load(); page='home'; renderNav(); render()}
async function saveWeight(){await api('/api/weights',{method:'POST',body:JSON.stringify({date:$('#wDate').value,time:$('#wTime').value,kg:$('#wKg').value,official:$('#wOfficial').value==='1',context:$('#wCtx').value})}); toast('Peso guardado'); await load(); page='weights'; renderNav(); render()}
async function saveMealAsTemplate(){const name=prompt('Nombre de plantilla'); if(!name||!mealItems.length)return; await api('/api/templates',{method:'POST',body:JSON.stringify({name,notes:$('#mNotes').value,kind:'meal',payload:{items:mealItems.map(i=>({food:i.food_name,grams:i.grams}))}})}); toast('Plantilla guardada'); await load()}
function renderTemplates(){ $('#view').innerHTML=`<div class="section-title"><div><h3>Plantillas rápidas</h3><p>Cambia gramos y guarda en 2 clics</p></div></div><div class="grid cols-2">${state.templates.map(templateCard).join('')}</div>`}
function templateCard(t){let p={items:[]};try{p=JSON.parse(t.payload)}catch{} const items=(p.items||[]).map(it=>{const f=foodByName(it.food);return f?calcFood(f,it.grams):null}).filter(Boolean); const total=calcList(items); return `<div class="card template-card" data-template="${t.id}"><h3>${t.name}</h3><p class="muted">${t.notes||''}</p><div class="template-items">${items.map((it,idx)=>`<div class="template-item"><div><b>${it.food_name}</b><br><small>${fmt(it.kcal)} kcal · ${fmt(it.protein)} g prot.</small></div><input type="number" value="${fmt(it.grams)}" data-tgram="${idx}"></div>`).join('')}</div><div class="totals"><b>${fmt(total.kcal)} kcal</b><b>${fmt(total.protein)} g prot.</b></div><button class="btn" onclick="saveTemplateMeal(${t.id})">Guardar ahora</button></div>`}
async function saveTemplateMeal(id){const t=state.templates.find(x=>x.id===id); const p=JSON.parse(t.payload); const card=document.querySelector(`[data-template="${id}"]`); const grams=[...card.querySelectorAll('[data-tgram]')].map(i=>Number(i.value)); const items=p.items.map((it,idx)=>({food_name:it.food,grams:grams[idx]})); await api('/api/meals',{method:'POST',body:JSON.stringify({date:today(),time:nowHM(),name:t.name,notes:t.notes,items})}); toast('Plantilla registrada'); selectedDate=today(); localStorage.setItem('selectedDate',selectedDate); await load(); page='home'; renderNav(); render()}
function renderFoods(){
  selectedFoodPhoto='';
  $('#view').innerHTML=`<div class="grid cols-2">
    <div class="card"><h3>🥫 Nuevo alimento</h3>
      <div class="photo-box"><div><b>📷 Foto etiqueta</b><small>OCR real local: sube foto, revisa las sugerencias y guarda.</small></div><input id="fPhoto" type="file" accept="image/*" onchange="uploadFoodPhoto()"><div id="photoPreview"></div></div>
      <div class="row">
        <div class="field span-6"><label>Nombre</label><input id="fName" placeholder="Ej. Yogur Eroski +Proteína 120 g"></div>
        <div class="field span-6"><label>Marca</label><input id="fBrand" placeholder="Eroski, ElPozo..."></div>
        <div class="field span-3"><label>kcal / 100 g</label><input id="fKcal" type="number"></div>
        <div class="field span-3"><label>proteína / 100 g</label><input id="fProt" type="number"></div>
        <div class="field span-3"><label>hidratos</label><input id="fCarbs" type="number"></div>
        <div class="field span-3"><label>grasa</label><input id="fFat" type="number"></div>
        <div class="field span-3"><label>azúcar</label><input id="fSugar" type="number"></div>
        <div class="field span-3"><label>sal</label><input id="fSalt" type="number"></div>
        <div class="field span-3"><label>ración g</label><input id="fTypical" type="number" value="100"></div>
        <div class="field span-3"><label>Comprado</label><select id="fPurchased"><option value="1">Sí</option><option value="0">No</option></select></div>
        <div class="field span-12"><label>Nota etiqueta</label><textarea id="fSource" placeholder="Ej. Por unidad 120 g: 68 kcal, 10 g proteína..."></textarea></div>
        <div class="field span-12"><label>Uso</label><input id="fNotes" placeholder="Desayuno, merienda, tupper..."></div>
      </div>
      <button class="btn" onclick="saveFood()">Guardar alimento</button>
    </div>
    <div class="card note-box"><h3>📌 OCR de etiqueta</h3><p>Sube la foto de la etiqueta, copia los valores por 100 g o por ración y guarda. La foto queda asociada al producto para revisarla después.</p><p class="muted">OCR local activo: rellena solo valores plausibles. Revisa siempre antes de guardar.</p></div>
  </div>
  <div class="section-title"><div><h3>Alimentos guardados</h3><p>Se usan en Registrar para cambiar solo gramos.</p></div><input id="foodFilter" placeholder="filtrar..." style="max-width:300px" oninput="renderFoodList()"></div>
  <div id="foodList" class="grid cols-3"></div>`;
  renderFoodList();
}
function renderFoodList(){const q=($('#foodFilter')?.value||'').toLowerCase(); const foods=state.foods.filter(f=>(f.name+' '+f.brand+' '+f.source_note).toLowerCase().includes(q)); $('#foodList').innerHTML=foods.map(f=>`<div class="card food-card">${f.photo_path?`<img class="food-photo" src="${f.photo_path}" alt="foto etiqueta">`:''}<h3>${f.purchased?'✅':'🥫'} ${f.name}</h3><p class="muted">${f.brand||''}</p><div class="chips"><span class="chip">${fmt(f.kcal)} kcal/100g</span><span class="chip">${fmt(f.protein)} g prot</span><span class="chip">típico ${fmt(f.typical_g)} g</span></div><p class="source">${f.source_note||''}</p><p>${f.notes||''}</p></div>`).join('')}
async function uploadFoodPhoto(){
  const file=$('#fPhoto')?.files?.[0];
  if(!file)return;
  const form=new FormData();
  form.append('photo',file);
  try{
    const r=await apiForm('/api/food-photo-ocr',form);
    selectedFoodPhoto=r.photo_path;
    const text=r.ocr_text||'';
    const n=r.nutrition||{};
    if($('#photoPreview')){
      $('#photoPreview').innerHTML=`<img class="food-photo preview" src="${selectedFoodPhoto}" alt="foto etiqueta"><span class="pill good">foto guardada</span>${text?'<span class="pill good">OCR leído</span>':`<span class="pill warn">OCR sin texto</span>`}`;
    }
    if($('#labelText') && text) $('#labelText').value=text;
    const fill=(id,val)=>{const el=$(id); if(el && val!==undefined && val!==null && val!=='') el.value=String(val).replace('.',',').replace(',','.');};
    fill('#fKcal', n.kcal);
    fill('#fProt', n.protein);
    fill('#fCarbs', n.carbs);
    fill('#fFat', n.fat);
    fill('#fSugar', n.sugar);
    fill('#fSalt', n.salt);
    fill('#fTypical', n.typical_g);
    if($('#fSource') && text) $('#fSource').value=(text.length>900?text.slice(0,900)+'…':text);
    toast(text?'Foto guardada y OCR interpretado':'Foto guardada; revisa OCR manual');
  }catch(e){
    toast(e.message);
  }
}
async function saveFood(){await api('/api/foods',{method:'POST',body:JSON.stringify({name:$('#fName').value,brand:$('#fBrand').value,kcal:$('#fKcal').value,protein:$('#fProt').value,carbs:$('#fCarbs').value,fat:$('#fFat').value,sugar:$('#fSugar').value,salt:$('#fSalt').value,typical_g:$('#fTypical').value,purchased:$('#fPurchased').value==='1',source_note:$('#fSource').value,notes:$('#fNotes').value,photo_path:selectedFoodPhoto})}); toast('Alimento guardado'); await load(); page='foods'; renderNav(); render()}
function renderSport(){ $('#view').innerHTML=`<div class="grid cols-2"><div class="card"><h3>🏋️ Nuevo entreno</h3><div class="row"><div class="field span-4"><label>Fecha</label><input id="sDate" type="date" value="${today()}"></div><div class="field span-3"><label>Hora</label><input id="sTime" type="time" value="${nowHM()}"></div><div class="field span-5"><label>Ejercicio</label><select id="sName">${state.exercises.map(e=>`<option>${e.name}</option>`).join('')}</select></div><div class="field span-3"><label>Minutos</label><input id="sMin" type="number"></div><div class="field span-3"><label>Distancia km</label><input id="sKm" type="number"></div><div class="field span-3"><label>Calorías reloj</label><input id="sKcal" type="number" placeholder="vacío = estima"></div><div class="field span-3"><label>&nbsp;</label><button class="btn" onclick="saveWorkout()">Guardar</button></div><div class="field span-12"><label>Notas</label><input id="sNotes"></div></div></div><div class="card"><h3>➕ Nuevo ejercicio</h3><div class="row"><div class="field span-6"><label>Nombre</label><input id="eName"></div><div class="field span-3"><label>MET</label><input id="eMet" type="number" value="5"></div><div class="field span-3"><label>&nbsp;</label><button class="btn" onclick="saveExercise()">Guardar</button></div><div class="field span-12"><label>Notas</label><input id="eNotes"></div></div></div></div><div class="section-title"><h3>Historial deporte</h3></div><div class="list">${state.workouts.map(workoutCard).join('')}</div>`}
async function saveWorkout(){await api('/api/workouts',{method:'POST',body:JSON.stringify({date:$('#sDate').value,time:$('#sTime').value,name:$('#sName').value,minutes:$('#sMin').value,distance_km:$('#sKm').value,kcal:$('#sKcal').value,notes:$('#sNotes').value})}); toast('Entreno guardado'); selectedDate=$('#sDate').value; localStorage.setItem('selectedDate',selectedDate); await load(); page='home'; renderNav(); render()}
async function saveExercise(){await api('/api/exercises',{method:'POST',body:JSON.stringify({name:$('#eName').value,met:$('#eMet').value,notes:$('#eNotes').value})}); toast('Ejercicio guardado'); await load(); page='sport'; renderNav(); render()}
function renderPlan(){const p=state.plans[0]?JSON.parse(state.plans[0].payload):null; $('#view').innerHTML=`<div class="grid cols-2"><div class="card"><h3>📥 Importar plan semanal</h3><p class="muted">Pega JSON que te pase ChatGPT.</p><textarea id="planRaw" style="min-height:220px" placeholder='{"name":"Semana...","days":[...]}'></textarea><button class="btn" onclick="savePlan()">Importar plan</button></div><div class="card"><h3>📅 Plan actual</h3>${p?renderPlanPayload(p):'<div class="empty">Sin plan.</div>'}</div></div>`}
function renderPlanPayload(p){return `<h3>${p.name}</h3><p class="muted">${p.notes||''}</p><div class="grid">${(p.days||[]).map(d=>`<div class="plan-day"><b>${d.day}</b><p><b>Desayuno:</b> ${d.breakfast||''}</p><p><b>Comida:</b> ${d.lunch||''}</p><p><b>Merienda:</b> ${d.snack||''}</p><p><b>Cena:</b> ${d.dinner||''}</p></div>`).join('')}</div>`}
async function savePlan(){await api('/api/plans',{method:'POST',body:JSON.stringify({raw:$('#planRaw').value})}); toast('Plan importado'); await load(); page='plan'; renderNav(); render()}
function renderWeights(){const all=[...state.weights].sort((a,b)=>(b.date+b.time).localeCompare(a.date+a.time)); $('#view').innerHTML=`<div class="grid cols-2"><div class="card"><h3>📉 Gráfica peso oficial</h3>${weightChart()}<p class="muted">La tendencia usa solo pesos oficiales. Las referencias ayudan a entender variaciones por comida/agua.</p></div><div class="card"><h3>⚖️ Registrar peso</h3><div class="row"><div class="field span-4"><label>Fecha</label><input id="wDate" type="date" value="${today()}"></div><div class="field span-3"><label>Hora</label><input id="wTime" type="time" value="${nowHM()}"></div><div class="field span-3"><label>Kg</label><input id="wKg" type="number" step="0.01"></div><div class="field span-2"><label>Tipo</label><select id="wOfficial"><option value="1">Oficial</option><option value="0">Referencia</option></select></div><div class="field span-12"><label>Contexto</label><input id="wCtx"></div></div><button class="btn" onclick="saveWeight()">Guardar peso</button></div></div><div class="section-title"><h3>Historial de peso</h3></div><div class="list">${all.map(w=>`<div class="list-card"><header><div><h4>${w.date} ${w.time} · ${fmt(w.kg)} kg</h4><p class="muted">${w.official?'Oficial':'Referencia'} · ${w.context||''}</p></div><button class="btn small danger" onclick="deleteWeight(${w.id})">×</button></header></div>`).join('')}</div>`}
async function deleteWeight(id){if(!confirm('¿Borrar peso?'))return; await api('/api/weights/'+id,{method:'DELETE'}); toast('Peso borrado'); await load(); render()}

function renderIntegrations(){
  $('#view').innerHTML=`<div class="grid cols-2"><div class="card integration-card"><h3>🔗 Strava</h3><p class="muted">Sincroniza actividades autorizadas de tu cuenta. Los tokens se guardan solo en la Raspberry, dentro de data/.</p><div id="stravaStatus" class="empty">Comprobando Strava...</div><div class="action-row"><button class="btn" onclick="connectStrava()">Conectar Strava</button><button class="btn secondary" onclick="syncStrava()">Sincronizar 14 días</button></div></div><div class="card note-box"><h3>Privacidad</h3><p>El repositorio no sube data/, dieta.db, tokens ni .env. Strava requiere configurar credenciales en la Raspberry.</p><p class="muted">Zepp/Amazfit directo no tiene una API pública sencilla para actividades. Ruta práctica: Zepp → Strava → Dieta Pro.</p></div></div>`;
  loadStravaStatus();
}
async function loadStravaStatus(){
  try{
    const s=await api('/api/strava/status');
    $('#stravaStatus').innerHTML=`<div class="status ${s.connected?'ok':s.configured?'warn':'bad'}"><b>${s.connected?'Conectado':s.configured?'Configurado, falta conectar':'No configurado'}</b><span>${s.message}</span></div>`;
    window.__stravaConnectUrl=s.connect_url;
  }catch(e){$('#stravaStatus').textContent='No se pudo comprobar Strava: '+e.message}
}
function connectStrava(){ if(window.__stravaConnectUrl) location.href=window.__stravaConnectUrl; else toast('Primero configura Strava en .env') }
async function syncStrava(){ try{const r=await api('/api/strava/sync',{method:'POST',body:JSON.stringify({days:14})}); toast(`Strava sincronizado: ${r.imported} nuevas actividades`); await load(); page='home'; renderNav(); render()}catch(e){toast('Strava: '+e.message)} }

function renderHistory(){ $('#view').innerHTML=`<div class="grid cols-2"><div><div class="section-title"><h3>Comidas</h3></div><div class="list">${state.meals.map(mealCard).join('')}</div></div><div><div class="section-title"><h3>Deporte</h3></div><div class="list">${state.workouts.map(workoutCard).join('')}</div></div></div>`}
$('#btnRefresh').onclick=load; load().catch(e=>{document.body.innerHTML='<pre style="padding:20px">Error cargando app: '+e.message+'</pre>'})


// V002_STRAVA_MANUAL_IMPORT_UI
let __stravaPreview = [];

function renderIntegrations(){
  const to = today();
  const from = new Date(Date.now() - 14 * 86400000).toISOString().slice(0,10);

  $('#view').innerHTML = `
    <div class="grid cols-2">
      <div class="card integration-card">
        <h3>🔗 Strava</h3>
        <p class="muted">Conecta Strava, elige fechas, revisa actividades e importa solo las que marques.</p>

        <div id="stravaStatus" class="empty">Comprobando Strava...</div>

        <div class="action-row">
          <button class="btn" onclick="connectStrava()">Conectar Strava</button>
        </div>

        <div class="row" style="margin-top:14px">
          <div class="field span-4">
            <label>Desde</label>
            <input id="stravaFrom" type="date" value="${from}">
          </div>
          <div class="field span-4">
            <label>Hasta</label>
            <input id="stravaTo" type="date" value="${to}">
          </div>
          <div class="field span-4">
            <label>&nbsp;</label>
            <button class="btn secondary" onclick="previewStrava()">Buscar actividades</button>
          </div>
        </div>

        <div id="stravaList" style="margin-top:14px"></div>
      </div>

      <div class="card note-box">
        <h3>Privacidad</h3>
        <p>Strava solo se consulta cuando pulsas buscar/importar.</p>
        <p>Los tokens quedan en la Raspberry dentro de data/ y no se suben al repo.</p>
        <p class="muted">Ruta recomendada: Zepp/Amazfit → Strava → Diet Pro Planner.</p>
      </div>
    </div>
  `;

  loadStravaStatus();
}

async function loadStravaStatus(){
  try{
    const s = await api('/api/strava/status');
    $('#stravaStatus').innerHTML = `
      <div class="status ${s.connected ? 'ok' : s.configured ? 'warn' : 'bad'}">
        <b>${s.connected ? 'Conectado' : s.configured ? 'Configurado, falta conectar' : 'No configurado'}</b>
        <span>${s.connected ? 'Listo para buscar actividades por fecha.' : s.message}</span>
      </div>`;
    window.__stravaConnectUrl = s.connect_url;
  }catch(e){
    $('#stravaStatus').textContent = 'No se pudo comprobar Strava: ' + e.message;
  }
}

function connectStrava(){
  if(window.__stravaConnectUrl) window.open(window.__stravaConnectUrl, '_blank');
  else toast('Primero configura Strava en .env');
}

async function previewStrava(){
  const after_date = $('#stravaFrom').value;
  const before_date = $('#stravaTo').value;

  $('#stravaList').innerHTML = '<div class="empty">Buscando actividades en Strava...</div>';

  try{
    const r = await api('/api/strava/preview', {
      method: 'POST',
      body: JSON.stringify({after_date, before_date})
    });
    __stravaPreview = r.activities || [];
    renderStravaPreview();
  }catch(e){
    $('#stravaList').innerHTML = `<div class="empty">Strava: ${e.message}</div>`;
  }
}

function renderStravaPreview(){
  if(!__stravaPreview.length){
    $('#stravaList').innerHTML = '<div class="empty">No hay actividades en ese rango.</div>';
    return;
  }

  $('#stravaList').innerHTML = `
    <div class="section-title compact-title">
      <div>
        <h3>Actividades encontradas</h3>
        <p>${__stravaPreview.length} actividades · selecciona cuáles importar</p>
      </div>
      <button class="btn" onclick="importSelectedStrava()">Importar seleccionadas</button>
    </div>

    <div class="compact-list">
      ${__stravaPreview.map(a => `
        <label class="compact-card workout" style="display:block;cursor:pointer;opacity:${a.already_imported ? .55 : 1}">
          <div class="compact-head">
            <div>
              <b>${a.date} ${a.time} · ${a.sport_type || a.type}</b>
              <small>${a.title} · ${fmt(a.minutes)} min · ${fmt(a.distance_km)} km · ${fmt(a.kcal)} kcal ${a.already_imported ? '· ya importada' : ''}</small>
            </div>
            <input type="checkbox" data-strava-id="${a.id}" ${a.already_imported ? 'disabled' : 'checked'}>
          </div>
        </label>
      `).join('')}
    </div>
  `;
}

async function importSelectedStrava(){
  const ids = [...document.querySelectorAll('[data-strava-id]:checked')].map(x => x.dataset.stravaId);

  if(!ids.length){
    toast('No seleccionaste actividades');
    return;
  }

  try{
    const r = await api('/api/strava/import', {
      method: 'POST',
      body: JSON.stringify({
        after_date: $('#stravaFrom').value,
        before_date: $('#stravaTo').value,
        ids
      })
    });

    toast(`Importadas: ${r.imported} · duplicadas: ${r.skipped}`);
    await load();
    page = 'home';
    renderNav();
    render();
  }catch(e){
    toast('Strava: ' + e.message);
  }
}

// V004_STRAVA_AUTO_SYNC_UI
async function loadStravaAutoStatus(){
  try{
    const s = await api('/api/strava/auto-status');
    const box = $('#stravaAutoStatus');
    if(!box) return;
    const last = s.last_message || 'Aún no sincronizado automáticamente';
    const result = s.last_result || {};
    box.innerHTML = `
      <div class="status ${s.enabled ? 'ok' : 'warn'}">
        <b>${s.enabled ? 'Auto-sync activado' : 'Auto-sync desactivado'}</b>
        <span>${last}</span>
      </div>
      <p class="muted">Último resultado: ${fmt(result.imported||0)} nuevas · ${fmt(result.skipped||0)} duplicadas · ${fmt(result.received||0)} recibidas</p>
    `;
    const enabled = $('#stravaAutoEnabled');
    const interval = $('#stravaAutoInterval');
    const from = $('#stravaAutoFrom');
    if(enabled) enabled.checked = !!s.enabled;
    if(interval) interval.value = s.interval_minutes || 30;
    if(from && !from.value) from.value = s.after_date || s.latest_import_date || today();
  }catch(e){
    const box = $('#stravaAutoStatus');
    if(box) box.innerHTML = `<div class="empty">Auto-sync: ${e.message}</div>`;
  }
}

async function saveStravaAutoConfig(){
  try{
    const r = await api('/api/strava/auto-config', {
      method: 'POST',
      body: JSON.stringify({
        enabled: $('#stravaAutoEnabled').checked,
        after_date: $('#stravaAutoFrom').value,
        interval_minutes: $('#stravaAutoInterval').value
      })
    });
    toast(r.last_message || 'Auto-sync guardado');
    await loadStravaAutoStatus();
  }catch(e){ toast('Auto-sync: ' + e.message); }
}

async function runStravaAutoNow(){
  const box = $('#stravaAutoStatus');
  if(box) box.innerHTML = '<div class="empty">Sincronizando ahora...</div>';
  try{
    const r = await api('/api/strava/auto-run', {method:'POST', body: JSON.stringify({})});
    toast(r.message || `Importadas: ${r.imported}`);
    await load();
    page = 'integrations';
    renderNav();
    render();
  }catch(e){
    toast('Auto-sync: ' + e.message);
    await loadStravaAutoStatus();
  }
}

function renderIntegrations(){
  const to = today();
  const from = localStorage.getItem('stravaDefaultFrom') || new Date(Date.now() - 14 * 86400000).toISOString().slice(0,10);
  const autoPreview = localStorage.getItem('stravaAutoPreview') === '1';

  $('#view').innerHTML = `
    <div class="grid cols-2">
      <div class="card integration-card">
        <h3>🔗 Strava</h3>
        <p class="muted">Conecta Strava, elige fechas, revisa actividades e importa solo las que marques.</p>
        <div id="stravaStatus" class="empty">Comprobando Strava...</div>
        <div class="action-row"><button class="btn" onclick="connectStrava()">Conectar Strava</button></div>
        <div class="row" style="margin-top:14px">
          <div class="field span-4"><label>Desde</label><input id="stravaFrom" type="date" value="${from}" onchange="localStorage.setItem('stravaDefaultFrom',this.value)"></div>
          <div class="field span-4"><label>Hasta</label><input id="stravaTo" type="date" value="${to}"></div>
          <div class="field span-4"><label>&nbsp;</label><button class="btn secondary" onclick="previewStrava()">Buscar actividades</button></div>
        </div>
        <label class="check-line"><input id="autoPreviewCheck" type="checkbox" ${autoPreview?'checked':''} onchange="localStorage.setItem('stravaAutoPreview',this.checked?'1':'0')"> Cargar la lista automáticamente al abrir esta página</label>
        <div id="stravaList" style="margin-top:14px"></div>
      </div>

      <div class="card note-box">
        <h3>⚙️ Auto-sync en segundo plano</h3>
        <p>Importa nuevas actividades de Strava sin abrir la página. La Raspberry revisa Strava cada cierto tiempo.</p>
        <div id="stravaAutoStatus" class="empty">Comprobando auto-sync...</div>
        <div class="row" style="margin-top:12px">
          <div class="field span-5"><label>Importar desde</label><input id="stravaAutoFrom" type="date" value="${from}"></div>
          <div class="field span-4"><label>Cada</label><select id="stravaAutoInterval"><option value="15">15 min</option><option value="30" selected>30 min</option><option value="60">1 hora</option><option value="180">3 horas</option></select></div>
          <div class="field span-3"><label>&nbsp;</label><button class="btn secondary" onclick="runStravaAutoNow()">Sincronizar ahora</button></div>
        </div>
        <label class="check-line"><input id="stravaAutoEnabled" type="checkbox"> Sincronizar automáticamente nuevas actividades</label>
        <div class="action-row"><button class="btn" onclick="saveStravaAutoConfig()">Guardar auto-sync</button></div>
        <p class="muted">Sincronizado correctamente a fecha aparecerá arriba cuando termine cada revisión. No sube tokens ni datos al repo.</p>
      </div>
    </div>
  `;

  loadStravaStatus();
  loadStravaAutoStatus().then(()=>{ if(autoPreview) previewStrava(); });
}


// V006_STABLE_ES_FIXES
(function(){
  // Spanish-only stable UI. Full i18n needs a key-based refactor, not DOM text replacement.
  function stableHeader(){
    document.documentElement.lang = 'es';
    document.documentElement.dataset.lang = 'es';
    document.title = 'Diet Pro Planner · v0.0.11';
    const brand = document.querySelector('.brand h1');
    if(brand) brand.textContent = 'Diet Pro Planner';
    const sub = document.querySelector('.brand p');
    if(sub) sub.textContent = 'Raspberry · local · privado';
    const eyebrow = document.querySelector('.eyebrow');
    if(eyebrow) eyebrow.textContent = 'Dieta controlada · v0.0.11';
    const lang = document.querySelector('#btnLang');
    if(lang) lang.remove();
  }

  const oldRender = window.render || render;
  window.render = function(){
    oldRender();
    stableHeader();
  };

  const oldRenderNav = window.renderNav || renderNav;
  window.renderNav = function(){
    oldRenderNav();
    stableHeader();
  };

  // Make sure numeric totals stay numeric even after older cached language state.
  const oldRenderHome = window.renderHome || renderHome;
  window.renderHome = function(){
    oldRenderHome();
    stableHeader();
    const metrics = document.querySelectorAll('.metric');
    // If an older broken translation left text like "Home,Resumen" in the activity metric, force rerender by data.
    try{
      const workouts = byDate(state.workouts);
      const sport = workoutTotals(workouts);
      const cards = [...document.querySelectorAll('.metric')];
      const activity = cards.find(c => /Actividad/.test(c.textContent));
      if(activity){
        const b = activity.querySelector('b');
        if(b) b.textContent = fmt(sport);
      }
    }catch(e){}
  };

  stableHeader();
})();

















/* DPP_UI5_FULL_REDESIGN_START */
const UI5_NAV={home:['🏠','Resumen','Panel diario'],register:['🍽️','Registrar','Comidas'],sport:['🏋️','Deporte','Strava/manual'],templates:['⚡','Plantillas','2 clics'],foods:['🥫','Alimentos','Productos/OCR'],plan:['📅','Plan','Semana'],weights:['⚖️','Peso','Historial'],integrations:['🔗','Integraciones','Strava'],history:['📚','Historial','Todo']};
function renderNav(){const nav=$('#nav'); if(!nav)return; nav.innerHTML=PAGES.map(([id,ico,label])=>{const p=UI5_NAV[id]||[ico,label,''];return `<button class="${page===id?'active':''}" data-page="${id}"><span class="nav-ico">${p[0]}</span><span class="nav-copy"><b>${p[1]}</b><small>${p[2]}</small></span></button>`}).join('');document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{page=b.dataset.page;renderNav();render()})}
function ui5OfficialWeights(){return state.weights.filter(w=>w.official).sort((a,b)=>(a.date+a.time).localeCompare(b.date+b.time))}
function ui5Trend(){const ws=ui5OfficialWeights(); if(ws.length<2)return{label:'Sin tendencia',cls:'neutral',text:'Registra 2+ pesos oficiales de mañana.'}; const f=ws[0],l=ws.at(-1),days=Math.max(1,(new Date(l.date)-new Date(f.date))/(1000*3600*24)),delta=Number(l.kg)-Number(f.kg); if(days<7||ws.length<5)return{label:delta<0?'Bajada inicial':delta>0?'Subida inicial':'Estable',cls:'info',text:`${fmt(delta)} kg desde ${f.date}. Pocos días: sin extrapolar kg/semana.`}; const weekly=delta/days*7; if(weekly<-1)return{label:'Bajada rápida',cls:'warn',text:`${fmt(delta)} kg · ${fmt(weekly)} kg/sem aprox.`}; if(weekly<-0.35)return{label:'Bajada correcta',cls:'good',text:`${fmt(delta)} kg · ${fmt(weekly)} kg/sem aprox.`}; if(delta>0)return{label:'Subiendo',cls:'bad',text:`${fmt(delta)} kg · ${fmt(weekly)} kg/sem aprox.`}; return{label:'Estable',cls:'info',text:`${fmt(delta)} kg · ${fmt(weekly)} kg/sem aprox.`}}
function weightChart(){const ws=ui5OfficialWeights().slice(-14); if(ws.length<2)return '<div class="empty">Cuando tengas 2+ pesos oficiales aparece la gráfica.</div>'; const vals=ws.map(w=>Number(w.kg)),min=Math.min(...vals)-.25,max=Math.max(...vals)+.25,W=640,H=280,L=68,R=32,T=42,B=56,pw=W-L-R,ph=H-T-B,x=i=>L+(ws.length===1?0:i*(pw/(ws.length-1))),y=v=>T+(max-v)/(max-min)*ph,pts=ws.map((w,i)=>`${x(i)},${y(Number(w.kg))}`).join(' '); const ticks=[min,(min+max)/2,max].map(v=>`<line x1="${L}" y1="${y(v)}" x2="${W-R}" y2="${y(v)}" stroke="rgba(31,60,90,.13)"/><text x="14" y="${y(v)+5}" font-size="13" font-weight="800" fill="#314964">${fmt(v)}</text>`).join(''); const dots=ws.map((w,i)=>`<g><circle cx="${x(i)}" cy="${y(Number(w.kg))}" r="7" fill="#2563eb" stroke="#fff" stroke-width="3"/><text x="${x(i)}" y="${y(Number(w.kg))-14}" text-anchor="middle" font-size="13" font-weight="900" fill="#0b1726">${fmt(w.kg)}</text><title>${w.date} ${w.time}: ${fmt(w.kg)} kg</title></g>`).join(''); const tr=ui5Trend(); return `<div class="ui5-chartbox"><svg class="chart ui5-weight-chart" viewBox="0 0 ${W} ${H}">${ticks}<polyline points="${pts}" fill="none" stroke="#2563eb" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>${dots}<text x="${L}" y="${H-18}" font-size="13" font-weight="800" fill="#54677f">${ws[0].date}</text><text x="${W-R}" y="${H-18}" text-anchor="end" font-size="13" font-weight="800" fill="#54677f">${ws.at(-1).date}</text></svg><div class="ui5-trend"><span class="ui5-chip ${tr.cls}">${tr.label}</span><b>${tr.text}</b></div></div>`}
function assistantFor(d=day()){const meals=byDate(state.meals,d),workouts=byDate(state.workouts,d),mt=mealTotals(meals),sport=workoutTotals(workouts),lw=latestWeight(),tr=ui5Trend(),names=meals.flatMap(m=>[m.name,m.notes||'',...(m.items||[]).map(i=>i.food_name)]).join(' ').toLowerCase(),tips=[]; if(!lw)tips.push('Registra peso oficial de mañana para construir tendencia real.'); else if(!lw.official)tips.push('Último peso es referencia; para tendencia usa mañana, después de baño y antes de desayunar.'); else tips.push(`Peso oficial: ${fmt(lw.kg)} kg. ${tr.text}`); if(mt.protein<80)tips.push('Proteína baja: prioriza pollo, huevos, atún, yogur proteico, jamón cocido extra o queso fresco batido.'); else if(mt.protein<120)tips.push('Proteína aceptable: intenta cerrar cerca de 130 g.'); else tips.push('Proteína bien cubierta hoy.'); if(mt.kcal<900)tips.push('Comida registrada baja: planifica comida/cena para no llegar con ansiedad.'); else if(mt.kcal>2300)tips.push('Kcal altas: siguiente comida limpia, sin dulce ni pan/arroz extra.'); else tips.push('Balance razonable: controla aceite y raciones.'); if(mt.oil>10)tips.push('Aceite alto: siguiente comida con sartén antiadherente y 0–5 g.'); if(sport>=900)tips.push('Mucho deporte: carbohidrato controlado sí, barra libre no.'); else if(sport>=300)tips.push('Buen gasto de actividad: recupera con proteína, no con picoteo.'); if(/chocolate|galleta|piruleta|dulce|tirma/.test(names))tips.push('Hubo dulce/snack: cierra con proteína + verdura.'); return [...new Set(tips)].slice(0,6)}
function ui5Progress(label,value,pct,sub,tone='good'){return `<article class="ui5-progress ${tone}"><div><span>${label}</span><b>${value}</b></div><i><em style="width:${Math.max(4,Math.min(100,pct))}%"></em></i><small>${sub}</small></article>`}
function quickActions(){return `<section class="quick-actions ui5-actions"><button class="quick primary" onclick="go('register')"><span>🍽️</span><b>Comida</b><small>alimentos + gramos</small></button><button class="quick sport" onclick="go('sport')"><span>🏋️</span><b>Entreno</b><small>Strava/manual</small></button><button class="quick weight" onclick="go('weights')"><span>⚖️</span><b>Peso</b><small>oficial/referencia</small></button><button class="quick" onclick="go('templates')"><span>⚡</span><b>Plantilla</b><small>cambia gramos</small></button><button class="quick help-tile" onclick="openHelpModal()"><span>❔</span><b>Ayuda</b><small>guía rápida</small></button></section>`}
function renderHome(){const lw=latestWeight(),meals=byDate(state.meals),workouts=byDate(state.workouts),mt=mealTotals(meals),sport=workoutTotals(workouts),protTarget=135,kcalTarget=Math.max(1500,1900+Math.min(sport,900)*.35),tr=ui5Trend(); $('#view').innerHTML=`<section class="ui5-hero"><div class="ui5-hero-copy"><span class="ui5-kicker">Diet Pro Planner · local</span><h2>Panel diario para comer, entrenar y ajustar sin perder tiempo.</h2><p>Comidas por gramos, peso oficial, OCR de etiquetas, Strava y asistente en una vista clara.</p><div class="ui5-pills"><span><small>Peso</small><b>${lw?fmt(lw.kg)+' kg':'—'}</b></span><span><small>Proteína</small><b>${fmt(mt.protein)} / ${protTarget} g</b></span><span><small>Actividad</small><b>${fmt(sport)} kcal</b></span><span><small>Tendencia</small><b>${tr.label}</b></span></div></div><div class="ui5-hero-panel">${ui5Progress('Proteína',fmt(mt.protein)+' g',mt.protein/protTarget*100,'Objetivo 130–150 g',mt.protein>=120?'good':'warn')}${ui5Progress('Comida',fmt(mt.kcal)+' kcal',mt.kcal/kcalTarget*100,'Objetivo flexible '+fmt(kcalTarget)+' kcal aprox.',mt.kcal>2300?'bad':'good')}${ui5Progress('Actividad',fmt(sport)+' kcal',Math.min(100,sport/10),sport?'Actividad registrada':'Sin entrenos hoy',sport>900?'warn':'good')}</div></section>${quickActions()}${dateBar()}<div class="grid cols-4 dashboard-metrics">${metric('⚖️','Último peso',lw?`${fmt(lw.kg)} kg`:'—',lw?`${lw.date} ${lw.time} · ${lw.official?'oficial':'referencia'}`:'sin datos')}${metric('🍽️','Comido',fmt(mt.kcal),'kcal estimadas')}${metric('💪','Proteína',`${fmt(mt.protein)} g`,'objetivo 130–150 g')}${metric('🔥','Actividad',fmt(sport),'kcal del día seleccionado')}</div><div class="grid cols-2 home-main" style="margin-top:14px"><div class="card assistant compact-assistant"><h3>🤖 Asistente</h3><ul>${assistantFor().map(x=>`<li>${x}</li>`).join('')}</ul></div><div class="card"><h3>📉 Peso oficial</h3>${weightChart()}<p class="muted">Solo pesos oficiales de mañana. Con pocos días no extrapolamos kg/semana.</p></div></div><div class="day-columns"><section class="card day-panel"><div class="section-title compact-title"><div><h3>🍽️ Comidas</h3><p>${fmt(mt.kcal)} kcal · ${fmt(mt.protein)} g prot.</p></div><button class="btn small" onclick="go('register')">+ Comida</button></div><div class="compact-list">${meals.length?meals.map(mealCardCompact).join(''):'<div class="empty">Sin comidas.</div>'}</div></section><section class="card day-panel"><div class="section-title compact-title"><div><h3>🏋️ Actividad</h3><p>${fmt(sport)} kcal</p></div><button class="btn small" onclick="go('sport')">+ Entreno</button></div><div class="compact-list">${workouts.length?workouts.map(workoutCardCompact).join(''):'<div class="empty">Sin entrenos para este día.</div>'}</div></section></div><div class="footer-space"></div>`}
function ui5ApplyShell(){document.documentElement.dataset.ui='ui5'; const e=document.querySelector('.eyebrow'); if(e)e.textContent='Dieta controlada · v0.0.11'; const r=document.querySelector('.rule-banner'); if(r&&r.dataset.ui5!=='1'){r.dataset.ui5='1';r.innerHTML=`<article class="ui5-rule protein"><span>Proteína</span><b>130–150 g/día</b><small>Prioridad antes de recortar de más.</small></article><article class="ui5-rule oil"><span>Aceite</span><b>5 g normal · 10 g máximo</b><small>Medido, no a ojo.</small></article><article class="ui5-rule carbs"><span>Pasta/arroz</span><b>Pesar en seco</b><small>Ración según deporte y hambre real.</small></article>`} const sr=document.querySelector('.sidebar .side-rule'); if(sr&&sr.dataset.ui5!=='1'){sr.dataset.ui5='1';sr.innerHTML='<span>Regla rápida</span><b>Proteína + aceite medido</b><small>Pasta/arroz en seco · dulces controlados.</small>'} if(!document.getElementById('ui5Badge')){const b=document.createElement('div');b.id='ui5Badge';b.className='ui5-badge';b.textContent='v0.0.11';document.querySelector('.topbar')?.appendChild(b)} if(!document.getElementById('floatingHelp')){const h=document.createElement('button');h.id='floatingHelp';h.className='floating-help';h.textContent='?';h.onclick=openHelpModal;h.title='Ayuda';document.body.appendChild(h)}}
function openHelpModal(){closeHelpModal(); const o=document.createElement('div');o.id='helpOverlay';o.className='help-overlay';o.innerHTML=`<div class="help-modal"><button class="help-close" onclick="closeHelpModal()">×</button><span class="ui5-kicker">Ayuda rápida</span><h2>Diet Pro Planner</h2><div class="help-grid"><div><b>🍽️ Comidas</b><p>Usa plantillas, cambia gramos y guarda. Pasta/arroz siempre en seco.</p></div><div><b>⚖️ Peso</b><p>Oficial por la mañana. Post-comida, noche o post-entreno son referencia.</p></div><div><b>📷 OCR</b><p>Sube foto de etiqueta. Tesseract intenta leerla. Revisa valores antes de guardar.</p></div><div><b>🏋️ Strava</b><p>Importa por ID y evita duplicados. Auto-sync queda igual.</p></div><div><b>🤖 Asistente</b><p>Consejos por proteína, kcal, aceite, deporte y dulces.</p></div><div><b>🔐 Privacidad</b><p>Esta prueba es local. No sube DB, tokens, .env ni fotos al repo.</p></div></div><div class="help-actions"><button class="btn" onclick="closeHelpModal();go('register')">Registrar comida</button><button class="btn secondary" onclick="closeHelpModal();go('foods')">Alimentos/OCR</button><button class="btn secondary" onclick="closeHelpModal();go('weights')">Peso</button></div></div>`;o.onclick=e=>{if(e.target.id==='helpOverlay')closeHelpModal()};document.body.appendChild(o)}
function closeHelpModal(){document.getElementById('helpOverlay')?.remove()}
if(!window.__DPP_UI5_PATCHED__){window.__DPP_UI5_PATCHED__=true; const prev=render; render=function(){prev();setTimeout(ui5ApplyShell,0)}; window.addEventListener('DOMContentLoaded',()=>setTimeout(ui5ApplyShell,0)); setTimeout(()=>{try{renderNav();render();ui5ApplyShell()}catch(e){console.error(e)}},250); setInterval(ui5ApplyShell,3000)}
/* DPP_UI5_FULL_REDESIGN_END */






/* DPP_OCR3_FRONTEND_START */
/* OCR3 frontend: faster feedback, exact known label support, concise source notes. */

function ocr3Set(id, val){
  const el=document.querySelector(id);
  if(!el || val===undefined || val===null || val==='') return;
  el.value=String(val).replace(',', '.');
}
function ocr3Badge(text, cls='info'){
  return `<span class="ocr3-badge ${cls}">${text}</span>`;
}
async function uploadFoodPhoto(){
  const file=document.querySelector('#fPhoto')?.files?.[0];
  if(!file) return;

  const preview=document.querySelector('#photoPreview');
  if(preview) preview.innerHTML=`${ocr3Badge('leyendo OCR...', 'info')}`;

  const form=new FormData();
  form.append('photo', file);

  try{
    const r=await apiForm('/api/food-photo-ocr', form);
    selectedFoodPhoto=r.photo_path;

    const n=r.nutrition||{};
    const product=r.product||{};
    const serving=r.serving||{};
    const extra=r.extra||{};
    const warnings=r.warnings||[];
    const conf=r.confidence||'baja';

    const nameEl=document.querySelector('#fName');
    const brandEl=document.querySelector('#fBrand');
    if(nameEl && product.name) nameEl.value=product.name;
    if(brandEl && product.brand) brandEl.value=product.brand;

    ocr3Set('#fKcal', n.kcal);
    ocr3Set('#fProt', n.protein);
    ocr3Set('#fCarbs', n.carbs);
    ocr3Set('#fFat', n.fat);
    ocr3Set('#fSugar', n.sugar);
    ocr3Set('#fSalt', n.salt);
    ocr3Set('#fTypical', n.typical_g || product.typical_g || serving.grams);

    const sourceParts=[];
    sourceParts.push(`OCR ${r.ocr_engine||'local'} · modo ${r.ocr_mode||'-'} · confianza ${conf}${r.cache_hit?' · cache':''}.`);
    if(product.name) sourceParts.push(`Producto: ${product.name}${product.brand?' · '+product.brand:''}.`);
    if(serving.grams){
      sourceParts.push(`Ración etiqueta ${serving.grams} g: ${serving.kcal??'-'} kcal · ${serving.protein??'-'} g prot · ${serving.fat??'-'} g grasa · ${serving.salt??'-'} g sal.`);
    }
    if(extra.saturated!==undefined || extra.calcium_mg!==undefined){
      sourceParts.push(`Extra por 100 g: saturadas ${extra.saturated??'-'} g · calcio ${extra.calcium_mg??'-'} mg.`);
    }
    if(warnings.length) sourceParts.push(`Avisos: ${warnings.slice(0,5).join(' | ')}`);
    if(r.ocr_text) sourceParts.push((r.ocr_text.length>650?r.ocr_text.slice(0,650)+'…':r.ocr_text));

    const source=document.querySelector('#fSource');
    if(source) source.value=sourceParts.join('\n\n');

    if(preview){
      const fields=Object.keys(n).join(', ') || 'sin valores seguros';
      const cls=conf==='alta'?'good':conf==='media'?'info':conf==='baja'?'warn':'bad';
      preview.innerHTML=`
        <img class="food-photo preview" src="${selectedFoodPhoto}" alt="foto etiqueta">
        <div class="ocr3-status">
          ${ocr3Badge('foto guardada','good')}
          ${ocr3Badge(r.cache_hit?'OCR desde cache':'OCR leído','good')}
          ${ocr3Badge('confianza '+conf,cls)}
          <small>Campos: ${fields}</small>
          ${warnings[0]?`<small class="ocr3-warn">${warnings[0]}</small>`:''}
        </div>
      `;
    }
    toast(r.cache_hit?'OCR desde cache: revisa y guarda':'OCR leído: revisa y guarda');
  }catch(e){
    if(preview) preview.innerHTML=ocr3Badge('error OCR','bad');
    toast(e.message || 'Error OCR');
  }
}
/* DPP_OCR3_FRONTEND_END */


/* DPP_UI5_PLAN_SPORT_START */
/* Plan and sport layout: less vertical, more dashboard-like. */

function ui5WorkoutDateLabel(w){
  return `${w.date||''} · ${w.time||''}`;
}
function ui5SportCard(w){
  const kcal = Number(w.kcal||0);
  const km = Number(w.distance_km||0);
  const min = Number(w.minutes||0);
  return `<article class="ui5-sport-card">
    <div class="ui5-sport-head">
      <div><b>${w.name||'Entreno'}</b><small>${ui5WorkoutDateLabel(w)}</small></div>
      <button class="btn small danger" onclick="deleteWorkout(${w.id})">×</button>
    </div>
    <div class="ui5-sport-metrics">
      <span><b>${fmt(min)}</b><small>min</small></span>
      <span><b>${fmt(km)}</b><small>km</small></span>
      <span><b>${fmt(kcal)}</b><small>kcal</small></span>
    </div>
    <p>${w.notes||''}</p>
  </article>`;
}

function renderSport(){
  const all=[...state.workouts].sort((a,b)=>(b.date+b.time).localeCompare(a.date+a.time));
  const last7=all.filter(w=>{
    try{return (Date.now()-new Date(w.date+'T12:00:00').getTime()) <= 7*86400000;}catch{return false}
  });
  const totalKcal=last7.reduce((a,w)=>a+Number(w.kcal||0),0);
  const totalMin=last7.reduce((a,w)=>a+Number(w.minutes||0),0);
  const totalKm=last7.reduce((a,w)=>a+Number(w.distance_km||0),0);

  $('#view').innerHTML=`
    <section class="ui5-sport-hero">
      <div><span class="ui5-kicker">Deporte</span><h3>Registrar o revisar actividad</h3><p>Strava queda como fuente principal; el manual sirve para ajustes rápidos.</p></div>
      <div class="ui5-sport-summary">
        <span><b>${fmt(totalKcal)}</b><small>kcal 7 días</small></span>
        <span><b>${fmt(totalMin)}</b><small>min 7 días</small></span>
        <span><b>${fmt(totalKm)}</b><small>km 7 días</small></span>
      </div>
    </section>

    <div class="ui5-sport-layout">
      <div class="card ui5-sport-form">
        <h3>🏋️ Nuevo entreno</h3>
        <div class="row compact-row">
          <div class="field span-3"><label>Fecha</label><input id="sDate" type="date" value="${today()}"></div>
          <div class="field span-2"><label>Hora</label><input id="sTime" type="time" value="${nowHM()}"></div>
          <div class="field span-4"><label>Ejercicio</label><select id="sName">${state.exercises.map(e=>`<option>${e.name}</option>`).join('')}</select></div>
          <div class="field span-3"><label>Minutos</label><input id="sMin" type="number" inputmode="decimal"></div>
          <div class="field span-3"><label>Distancia km</label><input id="sKm" type="number" step="0.01" inputmode="decimal"></div>
          <div class="field span-3"><label>Calorías reloj</label><input id="sKcal" type="number" placeholder="vacío = estima"></div>
          <div class="field span-6"><label>Notas</label><input id="sNotes" placeholder="Strava, reloj, sensación, etc."></div>
          <div class="field span-3"><label>&nbsp;</label><button class="btn" onclick="saveWorkout()">Guardar entreno</button></div>
        </div>
      </div>

      <div class="card ui5-exercise-form">
        <h3>➕ Tipo ejercicio</h3>
        <p class="muted">Añade solo si falta un tipo manual. Para Strava no hace falta.</p>
        <div class="row compact-row">
          <div class="field span-6"><label>Nombre</label><input id="eName" placeholder="Ej. Caminata suave"></div>
          <div class="field span-3"><label>MET</label><input id="eMet" type="number" value="5"></div>
          <div class="field span-3"><label>&nbsp;</label><button class="btn secondary" onclick="saveExercise()">Guardar</button></div>
          <div class="field span-12"><label>Notas</label><input id="eNotes"></div>
        </div>
      </div>
    </div>

    <div class="section-title ui5-section-title"><div><h3>Historial deporte</h3><p>${all.length} entrenos · últimos primero</p></div></div>
    <div class="ui5-sport-history">${all.map(ui5SportCard).join('')}</div>
  `;
}

function ui5MealLine(label, value){
  return value ? `<p><b>${label}</b><span>${value}</span></p>` : '';
}
function ui5PlanDayCard(d, idx){
  return `<article class="ui5-plan-day">
    <div class="ui5-plan-day-head"><span>${idx+1}</span><b>${d.day||'Día'}</b></div>
    ${ui5MealLine('Desayuno', d.breakfast)}
    ${ui5MealLine('Comida', d.lunch)}
    ${ui5MealLine('Merienda', d.snack)}
    ${ui5MealLine('Cena', d.dinner)}
  </article>`;
}
function renderPlanPayload(p){
  const days=p.days||[];
  return `<div class="ui5-plan-current">
    <div class="ui5-plan-intro">
      <span class="ui5-kicker">Plan actual</span>
      <h3>${p.name||'Plan semanal'}</h3>
      <p>${p.notes||'Sin notas.'}</p>
    </div>
    <div class="ui5-plan-days">${days.map(ui5PlanDayCard).join('')}</div>
  </div>`;
}
function renderPlan(){
  const p=state.plans[0]?JSON.parse(state.plans[0].payload):null;
  $('#view').innerHTML=`
    <div class="ui5-plan-layout">
      <section class="card ui5-plan-import">
        <h3>📥 Importar plan</h3>
        <p class="muted">Pega JSON semanal. El plan se muestra en tarjetas horizontales.</p>
        <textarea id="planRaw" placeholder='{"name":"Semana...","days":[...]}'></textarea>
        <button class="btn" onclick="savePlan()">Importar plan</button>
      </section>
      <section class="card ui5-plan-board">
        ${p?renderPlanPayload(p):'<div class="empty">Sin plan.</div>'}
      </section>
    </div>`;
}
/* DPP_UI5_PLAN_SPORT_END */









/* DPP_UI5_PLAN_EDITOR_START */
/* Plan editor v2 local-only.
   Fixes missing escapeHtml, broken plan parsing, and blank Plan page.
   No repo push, no DB schema change, keeps existing /api/plans endpoint. */

function ui5Esc(v){
  return String(v ?? '').replace(/[&<>"']/g, c => ({
    '&':'&amp;',
    '<':'&lt;',
    '>':'&gt;',
    '"':'&quot;',
    "'":'&#39;'
  }[c]));
}

function ui5SafePlanPayload(raw){
  if(!raw) return null;
  try{
    if(typeof raw === 'string') return JSON.parse(raw);
    if(typeof raw === 'object') return raw;
  }catch(e){
    console.warn('Plan JSON inválido', e, raw);
  }
  return null;
}

function ui5PlanDefaultWeek(){
  return {
    name: "Semana dieta controlada · editable",
    notes: "Plan local editable. Proteína 130–150 g/día, aceite medido, pasta/arroz en seco. Ajustar según deporte y hambre real.",
    days: [
      {
        day: "Viernes · hoy",
        breakfast: "Tostada 42 g + café con edulcorante + yogur proteico 120 g.",
        lunch: "80 g pasta seca + pollo 200–224 g crudo + verdura/judía verde. Aceite 5 g.",
        snack: "Si hay 12K/andaina: plátano o 2–3 tortitas + agua. Si no hay deporte: yogur proteico o fruta.",
        dinner: "Cena limpia: 2 huevos + jamón cocido extra 70–90 g + judía verde 250 g. Queso curado 10–15 g opcional.",
        target: "130–150 g proteína · aceite 5–10 g",
        status: "planificado"
      },
      {
        day: "Sábado",
        breakfast: "Tostada + café + yogur proteico.",
        lunch: "Proteína principal + verdura + arroz/pasta solo si hay actividad.",
        snack: "Fruta + yogur proteico. Gelatina 0 si hay antojo.",
        dinner: "Proteína + verdura. Evitar dulce nocturno.",
        target: "déficit controlado",
        status: "borrador"
      },
      {
        day: "Domingo",
        breakfast: "Desayuno base: tostada + café + yogur proteico.",
        lunch: "Comida flexible: prioriza proteína y mide pan/arroz/pasta.",
        snack: "Yogur proteico o fruta.",
        dinner: "Pescado/huevos/atún + verdura.",
        target: "cerrar semana limpio",
        status: "borrador"
      },
      {
        day: "Lunes",
        breakfast: "Tostada + café + yogur proteico.",
        lunch: "Tupper: carbo pesado en seco + pollo/atún + verdura + 5 g aceite.",
        snack: "Queso fresco batido o yogur proteico.",
        dinner: "Huevos/pescado + verdura.",
        target: "rutina",
        status: "borrador"
      }
    ]
  };
}

function ui5PlanNormalize(p){
  p = p || {};
  if(!Array.isArray(p.days)) p.days = [];
  return {
    name: p.name || "Plan semanal",
    notes: p.notes || "",
    days: p.days.map(d => ({
      day: d.day || "",
      breakfast: d.breakfast || "",
      lunch: d.lunch || "",
      snack: d.snack || "",
      dinner: d.dinner || "",
      target: d.target || "",
      status: d.status || "borrador"
    }))
  };
}

function ui5CurrentPlan(){
  try{
    const row = state.plans && state.plans.length ? state.plans[0] : null;
    const parsed = row ? ui5SafePlanPayload(row.payload) : null;
    return ui5PlanNormalize(parsed || ui5PlanDefaultWeek());
  }catch(e){
    console.error('Error cargando plan', e);
    return ui5PlanNormalize(ui5PlanDefaultWeek());
  }
}

function ui5PlanStats(p){
  const days = p.days || [];
  const planned = days.filter(d => [d.breakfast,d.lunch,d.snack,d.dinner].some(x => String(x||'').trim())).length;
  return {days: days.length, planned, missing: Math.max(0, 7 - days.length)};
}

function ui5PlanDayHtml(d, idx){
  const status = d.status || "borrador";
  return `<article class="ui5-edit-day" data-plan-day="${idx}">
    <header>
      <span>${idx+1}</span>
      <div>
        <input class="ui5-day-title" data-plan-field="day" value="${ui5Esc(d.day)}" placeholder="Ej. Viernes · recuperación">
        <select data-plan-field="status">
          ${["planificado","pendiente ajustar","borrador","realizado"].map(x => `<option value="${ui5Esc(x)}" ${x===status?'selected':''}>${ui5Esc(x)}</option>`).join('')}
        </select>
      </div>
      <button class="btn small danger" onclick="ui5DeletePlanDay(${idx})">×</button>
    </header>
    <label><b>Desayuno</b><textarea data-plan-field="breakfast" placeholder="Tostada + yogur...">${ui5Esc(d.breakfast)}</textarea></label>
    <label><b>Comida</b><textarea data-plan-field="lunch" placeholder="Tupper, pasta/arroz, proteína...">${ui5Esc(d.lunch)}</textarea></label>
    <label><b>Merienda</b><textarea data-plan-field="snack" placeholder="Fruta, yogur, pre-entreno...">${ui5Esc(d.snack)}</textarea></label>
    <label><b>Cena</b><textarea data-plan-field="dinner" placeholder="Proteína + verdura...">${ui5Esc(d.dinner)}</textarea></label>
    <label><b>Objetivo</b><input data-plan-field="target" value="${ui5Esc(d.target)}" placeholder="130–150 g proteína / aceite 5 g"></label>
  </article>`;
}

function ui5ReadPlanFromDom(){
  const p = {
    name: document.querySelector('#planName')?.value || "Plan semanal",
    notes: document.querySelector('#planNotes')?.value || "",
    days: []
  };
  document.querySelectorAll('[data-plan-day]').forEach(card => {
    const d = {};
    card.querySelectorAll('[data-plan-field]').forEach(el => {
      d[el.dataset.planField] = el.value || "";
    });
    p.days.push(d);
  });
  return ui5PlanNormalize(p);
}

function ui5RefreshPlanStats(p){
  p = p || ui5ReadPlanFromDom();
  const st = ui5PlanStats(p);
  const el = document.querySelector('#ui5PlanStats');
  if(el) el.innerHTML = `
    <span><b>${st.days}</b><small>días</small></span>
    <span><b>${st.planned}</b><small>con comidas</small></span>
    <span><b>${st.missing}</b><small>faltan</small></span>`;
}

function ui5RenderPlanBoard(p){
  const board = document.querySelector('#ui5PlanBoard');
  if(!board) return;
  board.innerHTML = (p.days||[]).map(ui5PlanDayHtml).join('');
  ui5RefreshPlanStats(p);
}

function ui5AddPlanDay(){
  const p = ui5ReadPlanFromDom();
  p.days.push({day:"Nuevo día", breakfast:"", lunch:"", snack:"", dinner:"", target:"130–150 g proteína", status:"borrador"});
  ui5RenderPlanBoard(p);
}

function ui5DeletePlanDay(idx){
  const p = ui5ReadPlanFromDom();
  p.days.splice(idx,1);
  ui5RenderPlanBoard(p);
}

function ui5CompletePlanWeek(){
  const p = ui5ReadPlanFromDom();
  while(p.days.length < 7){
    const n = p.days.length + 1;
    p.days.push({
      day: `Día ${n}`,
      breakfast: "Desayuno base: tostada + café + yogur proteico.",
      lunch: "Proteína + carbo pesado en seco si toca + verdura.",
      snack: "Fruta o yogur proteico.",
      dinner: "Proteína + verdura. Aceite medido.",
      target: "ajustar según actividad",
      status: "borrador"
    });
  }
  ui5RenderPlanBoard(p);
  toast("Semana completada en borrador");
}

function ui5ApplyDefaultPlan(){
  const p = ui5PlanDefaultWeek();
  const n = document.querySelector('#planName');
  const notes = document.querySelector('#planNotes');
  if(n) n.value = p.name;
  if(notes) notes.value = p.notes;
  ui5RenderPlanBoard(p);
  toast("Plan base cargado");
}

async function ui5SaveEditablePlan(){
  const p = ui5ReadPlanFromDom();
  await api('/api/plans', {method:'POST', body: JSON.stringify({raw: JSON.stringify(p, null, 2)})});
  toast("Plan guardado");
  await load();
  page='plan';
  renderNav();
  render();
}

function ui5ExportPlanJson(){
  const p = ui5ReadPlanFromDom();
  const raw = JSON.stringify(p, null, 2);
  const box = document.querySelector('#planRaw');
  if(box) box.value = raw;
  navigator.clipboard?.writeText(raw).then(()=>toast("JSON copiado")).catch(()=>toast("JSON listo abajo"));
}

function renderPlan(){
  let p;
  try{
    p = ui5CurrentPlan();
  }catch(e){
    console.error(e);
    p = ui5PlanNormalize(ui5PlanDefaultWeek());
  }
  const st = ui5PlanStats(p);
  $('#view').innerHTML = `
    <section class="ui5-plan-hero2">
      <div>
        <span class="ui5-kicker">Plan semanal editable</span>
        <h3>Planifica horizontal, corrige rápido y guarda.</h3>
        <p>Si el plan anterior venía roto, pulsa “Cargar plan base” o “Completar semana”.</p>
      </div>
      <div id="ui5PlanStats" class="ui5-plan-stats">
        <span><b>${st.days}</b><small>días</small></span>
        <span><b>${st.planned}</b><small>con comidas</small></span>
        <span><b>${st.missing}</b><small>faltan</small></span>
      </div>
    </section>

    <section class="card ui5-plan-toolbar">
      <div class="row compact-row">
        <div class="field span-5"><label>Nombre del plan</label><input id="planName" value="${ui5Esc(p.name)}" oninput="ui5RefreshPlanStats()"></div>
        <div class="field span-7"><label>Notas</label><input id="planNotes" value="${ui5Esc(p.notes)}" oninput="ui5RefreshPlanStats()"></div>
      </div>
      <div class="ui5-plan-actions">
        <button class="btn" onclick="ui5SaveEditablePlan()">Guardar cambios</button>
        <button class="btn secondary" onclick="ui5AddPlanDay()">Añadir día</button>
        <button class="btn secondary" onclick="ui5CompletePlanWeek()">Completar semana</button>
        <button class="btn secondary" onclick="ui5ApplyDefaultPlan()">Cargar plan base</button>
        <button class="btn secondary" onclick="ui5ExportPlanJson()">Copiar/mostrar JSON</button>
      </div>
    </section>

    <section id="ui5PlanBoard" class="ui5-edit-plan-board">
      ${(p.days||[]).map(ui5PlanDayHtml).join('')}
    </section>

    <section class="card ui5-plan-json">
      <h3>JSON del plan</h3>
      <p class="muted">Para importar otro plan: pega JSON y pulsa importar.</p>
      <textarea id="planRaw" placeholder='{"name":"Semana...","days":[...]}'></textarea>
      <button class="btn secondary" onclick="savePlan()">Importar JSON pegado</button>
    </section>`;
}

/* DPP_UI5_PLAN_EDITOR_END */

